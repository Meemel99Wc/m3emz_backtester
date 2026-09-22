"""
m3emz Backtester — Live Paper Trading via Binance WebSocket
Connects to real-time kline stream, applies strategy logic, fires paper signals.
"""

import asyncio
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from core.engine import Trade


class LivePaperTrader(QObject):
    """Paper trader that processes live candles from Binance WebSocket."""

    WS_BASE = "wss://stream.binance.com:9443/ws"

    # Signals
    candle_received = pyqtSignal(dict)
    signal_fired = pyqtSignal(str, float, dict)
    paper_trade_opened = pyqtSignal(object)
    paper_trade_closed = pyqtSignal(object)
    connection_status = pyqtSignal(bool, str)
    session_update = pyqtSignal(dict)  # session stats

    def __init__(self, symbol, interval, strategy_fn, init_cash=10_000):
        super().__init__()
        self.symbol = symbol.lower()
        self.interval = interval
        self.strategy_fn = strategy_fn
        self.init_cash = init_cash
        self.cash = init_cash
        self.paper_trades = []
        self._position = None
        self._running = False

        # Rolling candle buffer
        cols = ["Open", "High", "Low", "Close", "Volume"]
        self.live_candles = pd.DataFrame(columns=cols)
        self.live_candles.index.name = "Date"

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    @property
    def is_running(self):
        return self._running

    def process_ws_message(self, msg: dict):
        """Called from WebSocket thread with raw kline message."""
        if not self._running:
            return

        k = msg.get("k", {})
        if not k:
            return

        candle_data = {
            "time": datetime.fromtimestamp(k["t"] / 1000, tz=timezone.utc),
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "is_closed": k.get("x", False),
        }
        self.candle_received.emit(candle_data)

        if candle_data["is_closed"]:
            self._on_candle_closed(candle_data)

    def _on_candle_closed(self, candle: dict):
        """Process a closed candle: update buffer, run strategy."""
        new_row = pd.DataFrame(
            [{
                "Open": candle["open"],
                "High": candle["high"],
                "Low": candle["low"],
                "Close": candle["close"],
                "Volume": candle["volume"],
            }],
            index=pd.DatetimeIndex([candle["time"]], name="Date"),
        )

        self.live_candles = pd.concat([self.live_candles, new_row])
        # Keep last 500 candles
        if len(self.live_candles) > 500:
            self.live_candles = self.live_candles.iloc[-500:]

        if len(self.live_candles) < 30:
            return

        # Run strategy indicators
        try:
            df = self.strategy_fn(self.live_candles.copy(), mode="indicators")
        except Exception:
            return

        i = len(df) - 1
        price = float(df["Close"].iloc[i])

        # Check SL/TP on current position
        if self._position:
            t = self._position
            if t.direction == "long":
                if t.stop_loss and price <= t.stop_loss:
                    self._close_paper_trade(price, candle["time"], "SL")
                elif t.take_profit and price >= t.take_profit:
                    self._close_paper_trade(price, candle["time"], "TP")
            else:
                if t.stop_loss and price >= t.stop_loss:
                    self._close_paper_trade(price, candle["time"], "SL")
                elif t.take_profit and price <= t.take_profit:
                    self._close_paper_trade(price, candle["time"], "TP")

        # Run strategy logic via a mock backtester
        mock_bt = _MockBacktester(self, df, i)
        try:
            self.strategy_fn(df, i, mock_bt)
        except Exception:
            pass

        self._emit_session_update()

    def _open_paper_trade(self, direction, price, time, stop_loss=None,
                          take_profit=None, tag=""):
        if self._position:
            return
        size = self.cash * 0.95 / price  # 95% of cash
        t = Trade(
            entry_time=time,
            entry_price=price,
            size=size,
            direction=direction,
            stop_loss=stop_loss,
            take_profit=take_profit,
            tag=tag,
        )
        self._position = t
        self.signal_fired.emit(
            f"{'LONG' if direction == 'long' else 'SHORT'} SIGNAL",
            price,
            {"sl": stop_loss, "tp": take_profit, "tag": tag},
        )
        self.paper_trade_opened.emit(t)

    def _close_paper_trade(self, price, time, reason="signal"):
        if not self._position:
            return
        t = self._position
        t.close(time, price, reason)
        self.cash += t.pnl
        self.paper_trades.append(t)
        self._position = None
        self.paper_trade_closed.emit(t)

    def _emit_session_update(self):
        wins = sum(1 for t in self.paper_trades if t.pnl > 0)
        total_pnl = sum(t.pnl for t in self.paper_trades)
        self.session_update.emit({
            "trades": len(self.paper_trades),
            "winners": wins,
            "pnl": total_pnl,
            "pnl_pct": (total_pnl / self.init_cash * 100) if self.init_cash else 0,
            "position": self._position.direction if self._position else None,
        })

    def get_session_summary(self) -> dict:
        return {
            "trades": len(self.paper_trades),
            "winners": sum(1 for t in self.paper_trades if t.pnl > 0),
            "pnl": sum(t.pnl for t in self.paper_trades),
            "cash": self.cash,
        }


class _MockBacktester:
    """Mimics the Backtester interface for live strategy execution."""

    def __init__(self, trader: LivePaperTrader, df, i):
        self._trader = trader
        self._df = df
        self._i = i

    @property
    def in_position(self):
        return self._trader._position is not None

    @property
    def position_direction(self):
        return self._trader._position.direction if self._trader._position else None

    def buy(self, i, price, size_pct=1.0, stop_loss=None, take_profit=None, tag=""):
        time = self._df.index[min(i, len(self._df) - 1)]
        self._trader._open_paper_trade("long", price, time, stop_loss, take_profit, tag)

    def sell(self, i, price, size_pct=1.0, stop_loss=None, take_profit=None, tag=""):
        time = self._df.index[min(i, len(self._df) - 1)]
        self._trader._open_paper_trade("short", price, time, stop_loss, take_profit, tag)

    def close_position(self, i, price, reason="signal"):
        time = self._df.index[min(i, len(self._df) - 1)]
        self._trader._close_paper_trade(price, time, reason)


class WebSocketThread(QThread):
    """Runs Binance WebSocket in a background thread with asyncio."""

    message_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool, str)

    def __init__(self, symbol, interval):
        super().__init__()
        self.symbol = symbol.lower()
        self.interval = interval
        self._running = False
        self._retry_delay = 1

    def run(self):
        self._running = True
        asyncio.run(self._ws_loop())

    def stop(self):
        self._running = False

    async def _ws_loop(self):
        import websockets

        url = f"wss://stream.binance.com:9443/ws/{self.symbol}@kline_{self.interval}"

        while self._running:
            try:
                self.connection_changed.emit(True, f"Connecting to {self.symbol}...")
                async with websockets.connect(url, ping_interval=20) as ws:
                    self.connection_changed.emit(True, f"Connected to {self.symbol} WebSocket")
                    self._retry_delay = 1

                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(raw)
                            self.message_received.emit(data)
                        except asyncio.TimeoutError:
                            continue
                        except Exception:
                            break

            except Exception as e:
                if not self._running:
                    break
                self.connection_changed.emit(
                    False, f"Disconnected: {e}. Retrying in {self._retry_delay}s..."
                )
                await asyncio.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, 30)

        self.connection_changed.emit(False, "WebSocket stopped")
