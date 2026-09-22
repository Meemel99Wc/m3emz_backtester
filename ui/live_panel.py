"""
m3emz Backtester — Live Paper Trading Panel
Real-time WebSocket candle feed with paper trade execution.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QFrame, QSizePolicy, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QTextCursor

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from utils.theme import (
    BG_DEEP, BG_PANEL, BG_HOVER, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, ORANGE, PURPLE, FONT_MONO
)


class LivePanel(QWidget):
    """Live paper trading panel with WebSocket feed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")

        self._strategies = {}
        self._trader = None
        self._ws_thread = None
        self._chart_timer = None
        self._seed_worker = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Disclaimer ──
        disclaimer = QLabel(
            "PAPER TRADING ONLY — No real orders are placed. "
            "This simulates strategy signals on live market data."
        )
        disclaimer.setStyleSheet(
            f"background-color: #332200; color: {ORANGE}; "
            f"padding: 6px; font-size: 11px; border: 1px solid {ORANGE}; border: none;"
        )
        disclaimer.setAlignment(Qt.AlignCenter)
        layout.addWidget(disclaimer)

        # ── Top Control Bar ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.live_dot = QLabel("\u25cf")
        self.live_dot.setStyleSheet(f"color: {TEXT_SEC}; font-size: 18px; border: none;")
        top_bar.addWidget(self.live_dot)

        top_bar.addWidget(self._make_label("Symbol:"))
        self.symbol_input = QComboBox()
        self.symbol_input.setEditable(True)
        self.symbol_input.addItems(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"])
        self.symbol_input.setFixedWidth(120)
        top_bar.addWidget(self.symbol_input)

        top_bar.addWidget(self._make_label("Interval:"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["1m", "5m", "15m", "1h", "4h"])
        self.interval_combo.setCurrentText("1m")
        self.interval_combo.setFixedWidth(70)
        top_bar.addWidget(self.interval_combo)

        top_bar.addWidget(self._make_label("Strategy:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.setMinimumWidth(150)
        top_bar.addWidget(self.strategy_combo)

        self.start_btn = QPushButton("Start Paper Trading")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._start_trading)
        top_bar.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_trading)
        top_bar.addWidget(self.stop_btn)

        top_bar.addStretch()

        layout.addLayout(top_bar)

        # ── Status Bar ──
        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; border: none; padding: 2px;")
        layout.addWidget(self.status_label)

        # ── Chart ──
        self.figure = Figure(figsize=(10, 4), facecolor=BG_DEEP, dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.canvas, 2)

        self._draw_placeholder()

        # ── Bottom: Signal Log + Stats ──
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        # Signal Log
        log_container = QVBoxLayout()
        log_label = QLabel("Signal Log")
        log_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: bold; border: none;")
        log_container.addWidget(log_label)

        self.signal_log = QTextEdit()
        self.signal_log.setReadOnly(True)
        self.signal_log.setMaximumHeight(200)
        self.signal_log.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_PANEL};
                color: {TEXT_PRI};
                font-family: {FONT_MONO};
                font-size: 11px;
                border: 1px solid {BORDER};
            }}
        """)
        log_container.addWidget(self.signal_log)
        bottom.addLayout(log_container, 2)

        # Session Stats
        stats_container = QVBoxLayout()
        stats_label = QLabel("Session Stats")
        stats_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: bold; border: none;")
        stats_container.addWidget(stats_label)

        self.stats_frame = QFrame()
        self.stats_frame.setStyleSheet(f"background-color: {BG_PANEL}; border: 1px solid {BORDER};")
        stats_inner = QVBoxLayout(self.stats_frame)
        stats_inner.setContentsMargins(8, 8, 8, 8)
        stats_inner.setSpacing(4)

        self.stat_trades = QLabel("Paper Trades: 0")
        self.stat_winners = QLabel("Winners: 0")
        self.stat_pnl = QLabel("Session P&L: $0.00")
        self.stat_position = QLabel("Position: None")

        for lbl in [self.stat_trades, self.stat_winners, self.stat_pnl, self.stat_position]:
            lbl.setStyleSheet(f"color: {TEXT_PRI}; font-size: 12px; font-family: {FONT_MONO}; border: none;")
            stats_inner.addWidget(lbl)

        stats_inner.addStretch()
        stats_container.addWidget(self.stats_frame)
        bottom.addLayout(stats_container, 1)

        layout.addLayout(bottom, 1)

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; border: none;")
        return lbl

    def _draw_placeholder(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(BG_PANEL)
        ax.text(0.5, 0.5, "Start paper trading to see live chart",
                ha="center", va="center", color=TEXT_SEC, fontsize=14,
                transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        self.canvas.draw()

    def set_strategies(self, strategies: dict):
        """Set available strategies from main window."""
        self._strategies = strategies
        self.strategy_combo.clear()
        for name in strategies:
            self.strategy_combo.addItem(name)

    def _start_trading(self):
        strategy_name = self.strategy_combo.currentText()
        if not strategy_name or strategy_name not in self._strategies:
            self._log("No strategy selected")
            return

        symbol = self.symbol_input.currentText().strip().upper()
        interval = self.interval_combo.currentText()
        strategy_fn = self._strategies[strategy_name]

        try:
            from core.live_trader import LivePaperTrader, WebSocketThread
        except ImportError as e:
            self._log(f"Import error: {e}. Install websockets: pip install websockets")
            return

        self._trader = LivePaperTrader(symbol, interval, strategy_fn)
        self._trader.candle_received.connect(self._on_candle)
        self._trader.signal_fired.connect(self._on_signal)
        self._trader.paper_trade_opened.connect(self._on_trade_opened)
        self._trader.paper_trade_closed.connect(self._on_trade_closed)
        self._trader.session_update.connect(self._on_session_update)
        self._trader.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.live_dot.setStyleSheet(f"color: {ORANGE}; font-size: 18px; border: none;")
        self.status_label.setText("Seeding historical data…")
        self._log(f"Fetching historical seed data for {symbol} {interval}…")

        # ── Seed the candle buffer with historical data before going live ──
        # Without this, indicators (SMA, EMA, RSI…) return NaN for the first
        # 200+ candles and no signals ever fire.
        from utils.helpers import FetchWorker
        from core.fetcher import BinanceFetcher

        # Request 500 candles worth of lookback
        lookback_map = {
            "1m": "9 hours ago", "3m": "25 hours ago", "5m": "42 hours ago",
            "15m": "5 days ago", "30m": "11 days ago",
            "1h": "21 days ago", "4h": "84 days ago",
            "1d": "500 days ago", "1w": "9 years ago",
        }
        lookback = lookback_map.get(interval, "30 days ago")

        self._seed_worker = FetchWorker(BinanceFetcher, symbol, interval, lookback)
        self._seed_worker.finished.connect(self._on_seed_done)
        self._seed_worker.error.connect(self._on_seed_error)
        self._seed_worker.start()

    def _on_seed_done(self, df):
        """Historical seed data received — load into trader buffer then start WS."""
        if self._trader:
            self._trader.live_candles = df.tail(500).copy()
            self._log(f"Seeded buffer with {min(len(df), 500)} historical candles")
        self._start_websocket()

    def _on_seed_error(self, err):
        """If seed fetch fails, start WebSocket anyway — just warn the user."""
        self._log(f"⚠ Seed fetch failed ({err}) — starting without historical data, "
                  "signals may be delayed until enough live candles accumulate")
        self._start_websocket()

    def _start_websocket(self):
        """Start the WebSocket thread and chart timer after seeding."""
        if not self._trader:
            return

        symbol = self._trader.symbol.upper()
        interval = self._trader.interval

        from core.live_trader import WebSocketThread
        self._ws_thread = WebSocketThread(symbol, interval)
        self._ws_thread.message_received.connect(self._trader.process_ws_message)
        self._ws_thread.connection_changed.connect(self._on_connection_changed)
        self._ws_thread.start()

        # Chart refresh timer
        self._chart_timer = QTimer()
        self._chart_timer.timeout.connect(self._refresh_chart)
        self._chart_timer.start(5000)  # 5s refresh

        self.live_dot.setStyleSheet(f"color: {GREEN}; font-size: 18px; border: none;")
        strategy_name = self.strategy_combo.currentText()
        self._log(f"Started paper trading {symbol} {interval} with {strategy_name}")

    def _stop_trading(self):
        if self._seed_worker and self._seed_worker.isRunning():
            self._seed_worker.terminate()
            self._seed_worker = None
        if self._trader:
            self._trader.stop()
        if self._ws_thread:
            self._ws_thread.stop()
            self._ws_thread.quit()
            self._ws_thread.wait(3000)
            self._ws_thread = None
        if self._chart_timer:
            self._chart_timer.stop()
            self._chart_timer = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.live_dot.setStyleSheet(f"color: {TEXT_SEC}; font-size: 18px; border: none;")
        self.status_label.setText("Stopped")
        self._log("Paper trading stopped")

    def _on_connection_changed(self, connected, msg):
        self.status_label.setText(msg)
        color = GREEN if connected else RED
        self.live_dot.setStyleSheet(f"color: {color}; font-size: 18px; border: none;")

    def _on_candle(self, data):
        pass  # chart refreshed by timer

    def _on_signal(self, signal_type, price, details):
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")
        tag = details.get("tag", "")
        sl = details.get("sl")
        tp = details.get("tp")
        self._log(f"[{now}] {signal_type} @ ${price:,.2f} | {tag}")

    def _on_trade_opened(self, trade):
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")
        direction = "LONG" if trade.direction == "long" else "SHORT"
        sl_str = f"SL: ${trade.stop_loss:,.2f}" if trade.stop_loss else "No SL"
        tp_str = f"TP: ${trade.take_profit:,.2f}" if trade.take_profit else "No TP"
        self._log(f"[{now}] Paper trade OPENED: {direction} @ ${trade.entry_price:,.2f} | {sl_str} | {tp_str}")

    def _on_trade_closed(self, trade):
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")
        sign = "+" if trade.pnl > 0 else ""
        self._log(
            f"[{now}] Paper trade CLOSED: {trade.exit_reason} @ ${trade.exit_price:,.2f} | "
            f"PnL: {sign}${trade.pnl:,.2f} ({sign}{trade.pnl_pct:.2f}%)"
        )

    def _on_session_update(self, data):
        self.stat_trades.setText(f"Paper Trades: {data['trades']}")
        self.stat_winners.setText(f"Winners: {data['winners']}")
        sign = "+" if data["pnl"] >= 0 else ""
        pnl_color = GREEN if data["pnl"] >= 0 else RED
        self.stat_pnl.setText(f"Session P&L: {sign}${data['pnl']:,.2f} ({sign}{data['pnl_pct']:.1f}%)")
        self.stat_pnl.setStyleSheet(f"color: {pnl_color}; font-size: 12px; font-family: {FONT_MONO}; border: none;")
        pos = data.get("position")
        if pos:
            self.stat_position.setText(f"Position: {'LONG' if pos == 'long' else 'SHORT'}")
        else:
            self.stat_position.setText("Position: None")

    def _refresh_chart(self):
        if not self._trader or self._trader.live_candles.empty:
            return

        df = self._trader.live_candles.tail(100)
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(BG_PANEL)

        ax.plot(df.index, df["Close"].values, color=TEXT_SEC, linewidth=0.8)

        # Current price line
        last_price = df["Close"].iloc[-1]
        ax.axhline(last_price, color=ORANGE, linewidth=0.5, linestyle="--", alpha=0.8)
        ax.text(1.01, last_price, f"${last_price:,.2f}",
                transform=ax.get_yaxis_transform(), color=ORANGE, fontsize=8,
                va="center")

        ax.set_ylabel("Price", color=TEXT_SEC, fontsize=9)
        ax.set_title("Live Price", color=TEXT_PRI, fontsize=11, fontweight="bold", loc="left")
        ax.tick_params(colors=TEXT_SEC, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color(BORDER)

        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _log(self, msg):
        self.signal_log.append(msg)
        self.signal_log.moveCursor(QTextCursor.End)