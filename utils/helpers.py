"""
m3emz Backtester — Thread Workers & Utility Helpers
"""

import base64
import io
import json
import os
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal, QTimer, QPropertyAnimation, QRect
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect
from PyQt5.QtGui import QFont

from utils.theme import BG_PANEL, BORDER, TEXT_PRI, GREEN, RED, BLUE


# ══════════════════════════════════════════════════════
# Settings Persistence
# ══════════════════════════════════════════════════════
CONFIG_DIR = Path.home() / ".m3emz"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_SETTINGS = {
    "api_key": "",
    "model": "claude-sonnet-4-20250514",
    "last_symbol": "BTCUSDT",
    "last_interval": "1h",
    "last_lookback": "180 days ago",
    "last_cash": 10000,
    "last_commission": 0.001,
    "window_geometry": "",
    "panel_sizes": [280, 700, 320],
    "theme": "dark",
}


def load_settings() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
            merged = {**DEFAULT_SETTINGS, **saved}
            return merged
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# ══════════════════════════════════════════════════════
# Strategy Notes
# ══════════════════════════════════════════════════════
NOTES_FILE = CONFIG_DIR / "strategy_notes.json"


def load_strategy_notes() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if NOTES_FILE.exists():
        try:
            with open(NOTES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_strategy_notes(notes: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(NOTES_FILE, "w") as f:
        json.dump(notes, f, indent=2)


# ══════════════════════════════════════════════════════
# Thread Workers
# ══════════════════════════════════════════════════════
class FetchWorker(QThread):
    """Fetches OHLCV data from Binance in a background thread."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fetcher_class, symbol, interval, lookback):
        super().__init__()
        self.fetcher_class = fetcher_class
        self.symbol = symbol
        self.interval = interval
        self.lookback = lookback

    def run(self):
        try:
            self.progress.emit(0, f"Fetching {self.symbol} {self.interval}...")
            df = self.fetcher_class.fetch(self.symbol, self.interval, self.lookback)
            self.progress.emit(100, f"Fetched {len(df)} candles")
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(str(e))


class CachedFetchWorker(QThread):
    """Fetches OHLCV data with Parquet caching."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fetcher_class, symbol, interval, lookback, force_refetch=False):
        super().__init__()
        self.fetcher_class = fetcher_class
        self.symbol = symbol
        self.interval = interval
        self.lookback = lookback
        self.force_refetch = force_refetch

    def run(self):
        try:
            from utils.cache import get_cached_df, get_cache_last_timestamp, save_to_cache
            from core.fetcher import BinanceFetcher

            if not self.force_refetch:
                cached = get_cached_df(self.symbol, self.interval)
                if cached is not None and not cached.empty:
                    last_ts = get_cache_last_timestamp(self.symbol, self.interval)
                    if last_ts:
                        # Check if cache covers the requested lookback
                        start_ms = BinanceFetcher._parse_lookback(self.lookback)
                        first_cached_ms = int(cached.index[0].timestamp() * 1000)
                        if first_cached_ms <= start_ms:
                            self.progress.emit(50, f"Loading {self.symbol} from cache...")
                            # Fetch only new candles
                            ms_per_candle = BinanceFetcher.INTERVALS.get(self.interval, 3_600_000)
                            new_start = last_ts + ms_per_candle
                            try:
                                new_df = BinanceFetcher.fetch_from_ms(
                                    self.symbol, self.interval, new_start
                                )
                                if new_df is not None and not new_df.empty:
                                    save_to_cache(self.symbol, self.interval, new_df)
                                    cached = get_cached_df(self.symbol, self.interval)
                            except Exception:
                                pass  # Use cached data even if incremental fetch fails

                            # Trim to requested lookback
                            import pandas as pd
                            start_dt = pd.Timestamp(start_ms, unit="ms", tz="UTC")
                            if cached.index.tz is None:
                                start_dt = start_dt.tz_localize(None)
                            df = cached[cached.index >= start_dt]
                            if not df.empty:
                                self.progress.emit(100, f"Loaded {len(df)} candles (cached)")
                                self.finished.emit(df)
                                return

            # Full fetch
            self.progress.emit(0, f"Fetching {self.symbol} {self.interval}...")
            df = self.fetcher_class.fetch(self.symbol, self.interval, self.lookback)
            save_to_cache(self.symbol, self.interval, df)
            self.progress.emit(100, f"Fetched {len(df)} candles")
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(str(e))


class MultiFetchWorker(QThread):
    """Fetches OHLCV data for multiple symbols sequentially."""
    progress = pyqtSignal(int, int, str)     # current_idx, total, message
    symbol_done = pyqtSignal(str, object)    # symbol, DataFrame
    all_finished = pyqtSignal(dict)          # {symbol: DataFrame}
    symbol_error = pyqtSignal(str, str)      # symbol, error message

    def __init__(self, fetcher_class, symbols, interval, lookback):
        super().__init__()
        self.fetcher_class = fetcher_class
        self.symbols = symbols
        self.interval = interval
        self.lookback = lookback

    def run(self):
        results = {}
        total = len(self.symbols)
        for idx, symbol in enumerate(self.symbols):
            try:
                self.progress.emit(idx + 1, total, f"Fetching {symbol} ({idx+1}/{total})...")
                df = self.fetcher_class.fetch(symbol, self.interval, self.lookback)

                # Cache each symbol
                try:
                    from utils.cache import save_to_cache
                    save_to_cache(symbol, self.interval, df)
                except Exception:
                    pass

                results[symbol] = df
                self.symbol_done.emit(symbol, df)
            except Exception as e:
                self.symbol_error.emit(symbol, str(e))
        self.all_finished.emit(results)


class BacktestWorker(QThread):
    """Runs a single backtest in a background thread."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict, list, object, str)  # stats, trades, backtester, strategy_name
    error = pyqtSignal(str)

    def __init__(self, df, strategy_fn, strategy_name, cash, commission, interval):
        super().__init__()
        self.df = df.copy()
        self.strategy_fn = strategy_fn
        self.strategy_name = strategy_name
        self.cash = cash
        self.commission = commission
        self.interval = interval

    def run(self):
        try:
            from core.engine import Backtester
            self.progress.emit(f"Running {self.strategy_name}...")
            bt = Backtester(self.df, cash=self.cash, commission=self.commission,
                            interval=self.interval)
            bt.run(self.strategy_fn)
            stats = bt.stats()
            self.finished.emit(stats, bt.trades, bt, self.strategy_name)
        except Exception as e:
            self.error.emit(f"{self.strategy_name}: {str(e)}")


class ClaudeWorker(QThread):
    """Calls Claude API in a background thread with streaming."""
    chunk = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    token_usage = pyqtSignal(int, int, float)  # input, output, cost

    def __init__(self, api_key, model, messages, system_prompt):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.messages = messages
        self.system_prompt = system_prompt

    def run(self):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            full_text = ""
            with client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                messages=self.messages,
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    self.chunk.emit(text)

            # Try to get usage from the final message
            try:
                msg = stream.get_final_message()
                if msg and hasattr(msg, "usage"):
                    inp = msg.usage.input_tokens
                    out = msg.usage.output_tokens
                    cost = (inp * 3 + out * 15) / 1_000_000
                    self.token_usage.emit(inp, out, cost)
            except Exception:
                pass

            self.finished.emit(full_text)
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════
# Toast Notification
# ══════════════════════════════════════════════════════
class ToastNotification(QWidget):
    """Pop-up notification in the bottom-right corner."""

    COLORS = {
        "success": GREEN,
        "error": RED,
        "info": BLUE,
    }

    def __init__(self, parent, message, toast_type="success", duration=3000):
        super().__init__(parent)
        self._duration = duration

        self.setFixedHeight(42)
        self.setMinimumWidth(280)
        self.setMaximumWidth(450)

        color = self.COLORS.get(toast_type, BLUE)
        self.setStyleSheet(f"""
            background-color: {BG_PANEL};
            border: 1px solid {color};
            border-left: 4px solid {color};
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)

        icon_map = {"success": "\u2705", "error": "\u274c", "info": "\u2139\ufe0f"}
        icon = QLabel(icon_map.get(toast_type, "\u2139\ufe0f"))
        icon.setStyleSheet("border: none;")
        layout.addWidget(icon)

        label = QLabel(message)
        label.setStyleSheet(f"color: {TEXT_PRI}; border: none; font-size: 12px;")
        label.setWordWrap(True)
        layout.addWidget(label, 1)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.show()
        self.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_toast()
        QTimer.singleShot(self._duration, self._fade_out)

    def _position_toast(self):
        if self.parent():
            parent_rect = self.parent().rect()
            x = parent_rect.width() - self.width() - 16
            y = parent_rect.height() - self.height() - 16
            self.move(max(0, x), max(0, y))

    def _fade_out(self):
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.deleteLater)
        self.anim.start()


# ══════════════════════════════════════════════════════
# Formatting Helpers
# ══════════════════════════════════════════════════════
def format_number(value, prefix="", suffix="", decimals=2):
    if isinstance(value, float):
        return f"{prefix}{value:,.{decimals}f}{suffix}"
    return f"{prefix}{value:,}{suffix}"


def export_results(stats, strategy_name, symbol, filepath=None):
    if filepath is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"results_{symbol}_{ts}.json"
    data = {
        "strategy": strategy_name,
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "stats": stats,
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return filepath


def export_chat(messages, filepath=None):
    if filepath is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"chat_history_{ts}.json"
    with open(filepath, "w") as f:
        json.dump(messages, f, indent=2)
    return filepath


# ══════════════════════════════════════════════════════
# HTML Report Exporter
# ══════════════════════════════════════════════════════
def export_html_report(strategy_name, symbol, interval, stats, trades,
                       equity_fig=None, regime_stats=None, filepath=None):
    """
    Generate a professional HTML report with embedded charts and stats.
    equity_fig: matplotlib Figure to embed as base64 PNG.
    """
    if filepath is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"report_{symbol}_{strategy_name}_{ts}.html"

    # Embed chart as base64
    chart_html = ""
    if equity_fig:
        buf = io.BytesIO()
        equity_fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                           facecolor="#0d1117")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        chart_html = f'<img src="data:image/png;base64,{b64}" style="width:100%; max-width:1200px;">'

    # Stats table
    stats_rows = ""
    for k, v in stats.items():
        color = "#00ff88" if isinstance(v, (int, float)) and v > 0 else "#ff4444" if isinstance(v, (int, float)) and v < 0 else "#e6edf3"
        stats_rows += f'<tr><td>{k}</td><td style="color:{color}; font-weight:bold;">{v}</td></tr>\n'

    # Trade journal table
    trade_rows = ""
    for i, t in enumerate(trades[:200]):  # Limit to 200
        pnl_color = "#00ff88" if t.pnl > 0 else "#ff4444"
        sign = "+" if t.pnl > 0 else ""
        entry_str = t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else ""
        exit_str = t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else ""
        dur = ""
        if t.exit_time and t.entry_time:
            dur = f"{(t.exit_time - t.entry_time).total_seconds() / 3600:.1f}h"
        trade_rows += f"""<tr>
            <td>{i+1}</td><td>{entry_str}</td><td>{exit_str}</td>
            <td>{'LONG' if t.direction == 'long' else 'SHORT'}</td>
            <td>${t.entry_price:,.2f}</td><td>${t.exit_price or 0:,.2f}</td>
            <td style="color:{pnl_color}">{sign}${t.pnl:,.2f}</td>
            <td>{t.exit_reason or ''}</td><td>{dur}</td>
        </tr>\n"""

    # Regime stats
    regime_html = ""
    if regime_stats:
        regime_html = '<h2>Regime Analysis</h2><div class="regime-grid">'
        for name, data in regime_stats.items():
            color = data.get("color", "#888")
            regime_html += f"""
            <div class="regime-card" style="border-left: 3px solid {color};">
                <div class="regime-name">{data.get('icon', '')} {name}</div>
                <div>Trades: {data.get('trades', 0)}</div>
                <div>Win Rate: {data.get('win_rate', 0):.1f}%</div>
                <div>Avg PnL: ${data.get('avg_pnl', 0):,.2f}</div>
            </div>"""
        regime_html += '</div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Backtest Report — {strategy_name}</title>
<style>
body {{ background: #0d1117; color: #e6edf3; font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; }}
h1 {{ color: #e6edf3; border-bottom: 2px solid #1B74E4; padding-bottom: 10px; }}
h2 {{ color: #8b949e; margin-top: 30px; }}
.header {{ display: flex; justify-content: space-between; align-items: center; }}
.meta {{ color: #8b949e; font-size: 14px; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th {{ background: #161b22; color: #8b949e; text-align: left; padding: 8px 12px; border: 1px solid #30363d; font-size: 12px; }}
td {{ padding: 6px 12px; border: 1px solid #30363d; font-size: 12px; font-family: 'JetBrains Mono', monospace; }}
tr:hover {{ background: #1f2937; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 15px 0; }}
.stat-card {{ background: #161b22; border: 1px solid #30363d; padding: 12px; }}
.stat-card .label {{ color: #8b949e; font-size: 10px; text-transform: uppercase; }}
.stat-card .value {{ font-size: 18px; font-weight: bold; font-family: 'JetBrains Mono', monospace; }}
.regime-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 15px 0; }}
.regime-card {{ background: #161b22; border: 1px solid #30363d; padding: 10px; font-size: 12px; }}
.regime-name {{ font-weight: bold; margin-bottom: 6px; }}
.footer {{ color: #8b949e; font-size: 11px; margin-top: 30px; border-top: 1px solid #30363d; padding-top: 10px; }}
</style>
</head>
<body>
<div class="header">
    <h1>Backtest Report</h1>
    <div class="meta">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
<p class="meta">Strategy: <strong>{strategy_name}</strong> | Symbol: {symbol} | Interval: {interval}</p>

{chart_html}

<h2>Performance Statistics</h2>
<table>{stats_rows}</table>

{regime_html}

<h2>Trade Journal ({len(trades)} trades)</h2>
<table>
<tr><th>#</th><th>Entry</th><th>Exit</th><th>Dir</th><th>Entry $</th><th>Exit $</th><th>PnL</th><th>Reason</th><th>Duration</th></tr>
{trade_rows}
</table>

<div class="footer">
    Generated by m3emz Backtester | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</div>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath
