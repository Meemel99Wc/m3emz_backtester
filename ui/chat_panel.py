"""
m3emz Backtester — Claude AI Chat Panel + Claude Code CLI (Tabbed)
Tab 1: Claude AI Chat with Error-Fix Mode, Auto-Optimize, token counter.
Tab 2: Claude Code CLI — runs `claude -p` via QProcess, streaming output.
"""

import re
import os
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QComboBox, QScrollArea, QFrame,
    QSizePolicy, QDialog, QDialogButtonBox, QFileDialog,
    QProgressBar, QTabWidget
)
from PyQt5.QtCore import Qt, QTimer, QProcess, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QColor

from utils.theme import (
    BG_DEEP, BG_PANEL, BG_HOVER, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, PURPLE, ORANGE, FONT_MONO
)
from utils.helpers import ClaudeWorker, load_settings, save_settings, export_chat

# ── System prompt ────────────────────────────────────────
SYSTEM_PROMPT = """You are m3emz's AI trading assistant integrated into a professional Python backtesting application. You have deep expertise in:
- Quantitative trading strategies (momentum, mean reversion, trend following, volatility)
- Python backtesting with pandas/numpy
- Technical analysis (RSI, MACD, Bollinger Bands, VWAP, ADX, Stochastic, ATR)
- Risk management (position sizing, stop losses, Kelly criterion)
- Statistical analysis of backtest results

CONTEXT — Current backtest state:
{BACKTEST_CONTEXT}

When writing strategy code, ALWAYS follow this exact template (the app imports it dynamically):

def strategy_NAME(df, i=None, bt=None, mode=None):
    \"\"\"One-line description\"\"\"
    if mode == "indicators":
        # Compute indicators here, add as df columns, return df
        df["RSI"] = Indicators.rsi(df["Close"], 14)
        return df
    # Trading logic — called on every candle
    if i < 20: return  # warmup guard
    row = df.iloc[i]
    close = row["Close"]
    if not bt.in_position:
        bt.buy(i, close, stop_loss=..., take_profit=..., tag="NAME")
    elif bt.position_direction == "long":
        if ...:
            bt.close_position(i, close)

Available classes (already imported in user strategy files):
- Indicators.rsi(series, period) -> Series
- Indicators.ema(series, period) -> Series
- Indicators.sma(series, period) -> Series
- Indicators.macd(series, fast, slow, signal) -> (macd, signal, hist)
- Indicators.bollinger_bands(series, period, std) -> (upper, mid, lower)
- Indicators.atr(high, low, close, period) -> Series
- Indicators.vwap(high, low, close, volume, period) -> Series
- Indicators.adx(high, low, close, period) -> Series
- Indicators.stoch_rsi(series) -> (k, d)
- bt.buy(i, price, size_pct=1.0, stop_loss=None, take_profit=None, tag="")
- bt.sell(i, price, ...) [short selling]
- bt.close_position(i, price)
- bt.in_position -> bool
- bt.position_direction -> "long" | "short" | None

Be concise. When writing code, output ONLY the function, properly formatted, inside a markdown python block.
When you write a strategy, end your response with a line: [STRATEGY_READY] so the app knows to offer an import button."""

# ── Error-fix addendum ──
ERROR_FIX_ADDENDUM = """
IMPORTANT — ERROR FIX MODE:
The user has pasted backtest errors. Your job is to:

For "Long orders require: SL (X) < LIMIT (Y) < TP (Z)" errors:
- This means stop_loss >= entry_price OR take_profit <= entry_price
- Root cause: ATR calculation returned NaN, 0, or negative value at that candle
- Or: the SL/TP formula is inverted (e.g. added instead of subtracted)
- Fix: always validate before calling bt.buy():
    atr = row.get("ATR", 0)
    if pd.isna(atr) or atr <= 0:
        return  # skip candle if ATR is invalid
    sl = close - ATR_SL * atr
    tp = close + ATR_TP * atr
    if sl >= close or tp <= close:
        return  # extra safety guard

For "Short orders require: SL (X) > LIMIT (Y) > TP (Z)" errors:
- Mirror of above but for short trades
- SL must be ABOVE entry, TP must be BELOW entry

For Traceback errors:
- Read the full stack trace and identify the line number and file
- Provide the exact fix for that line

Always output the COMPLETE fixed strategy function, not just the changed lines.
Include import pandas as pd, import numpy as np, from core.indicators import Indicators at the top.
End your response with [STRATEGY_READY] if you've provided a fixed strategy.
"""

# ── Error detection patterns ─────────────────────────────
ERROR_PATTERNS = [
    re.compile(r"Long orders require:\s*SL", re.IGNORECASE),
    re.compile(r"Short orders require:\s*SL", re.IGNORECASE),
    re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"Error:.*\d", re.IGNORECASE),
    re.compile(r"require:.*\(.*\d", re.IGNORECASE),
    re.compile(r"KeyError:", re.IGNORECASE),
    re.compile(r"IndexError:", re.IGNORECASE),
    re.compile(r"ValueError:", re.IGNORECASE),
]

# ── Suggested prompt chips ───────────────────────────────
SUGGESTED_PROMPTS = [
    "Fix errors from last backtest",
    "Why is my win rate below 50%?",
    "Write a new strategy",
    "How to reduce max drawdown?",
    "Optimize ATR SL/TP multipliers",
    "Compare strategies",
    "Write a breakout strategy",
    "Explain why so many SL hits",
]


def _detect_errors(text: str) -> bool:
    return any(pat.search(text) for pat in ERROR_PATTERNS)


# ═══════════════════════════════════════════════════════════════
#  Chat Bubble
# ═══════════════════════════════════════════════════════════════

class ChatBubble(QFrame):
    """A single chat message bubble."""

    def __init__(self, text, is_user=False, parent=None):
        super().__init__(parent)
        self.is_user = is_user

        if is_user:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {BG_HOVER};
                    border: none;
                    border-radius: 8px;
                    padding: 8px 12px;
                    margin-left: 40px;
                    margin-right: 4px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {BG_PANEL};
                    border: none;
                    border-left: 3px solid {PURPLE};
                    border-radius: 0px;
                    padding: 8px 12px;
                    margin-right: 40px;
                    margin-left: 4px;
                }}
            """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        role_lbl = QLabel("You" if is_user else "Claude")
        role_lbl.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 10px; font-weight: bold; border: none; padding: 0; margin: 0;"
        )
        layout.addWidget(role_lbl)

        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text_label.setStyleSheet(f"""
            color: {TEXT_PRI};
            font-size: 12px;
            border: none;
            padding: 0;
            margin: 0;
            line-height: 1.4;
        """)
        layout.addWidget(self.text_label)

    def set_text(self, text):
        formatted = self._format_text(text)
        self.text_label.setText(formatted)

    def _format_text(self, text):
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(
            r'```python\n?(.*?)```',
            lambda m: (
                f'<pre style="background-color:{BG_DEEP}; padding:6px; '
                f'font-family:{FONT_MONO}; font-size:11px; color:{GREEN};">'
                f'{m.group(1)}</pre>'
            ),
            text, flags=re.DOTALL
        )
        text = re.sub(
            r'```\n?(.*?)```',
            lambda m: (
                f'<pre style="background-color:{BG_DEEP}; padding:6px; '
                f'font-family:{FONT_MONO}; font-size:11px;">'
                f'{m.group(1)}</pre>'
            ),
            text, flags=re.DOTALL
        )
        text = re.sub(
            r'`(.+?)`',
            lambda m: (
                f'<code style="background-color:{BG_DEEP}; padding:1px 4px; '
                f'font-family:{FONT_MONO}; font-size:11px;">'
                f'{m.group(1)}</code>'
            ),
            text
        )
        text = text.replace("\n", "<br>")
        return text


# ═══════════════════════════════════════════════════════════════
#  Claude Code CLI Panel  (Tab 2)
# ═══════════════════════════════════════════════════════════════

class ClaudeCodePanel(QWidget):
    """Terminal emulator that runs `claude -p <prompt>` via QProcess."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        self._process = None
        self._build_ui()
        self._check_claude_installed()

    # ── Build UI ────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Header row ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 16px; border: none;"
        )
        header_row.addWidget(self.status_dot)

        title = QLabel("Claude Code CLI")
        title.setStyleSheet(
            f"color: {ORANGE}; font-size: 14px; font-weight: bold; border: none;"
        )
        header_row.addWidget(title)

        header_row.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setFixedWidth(55)
        self.clear_btn.clicked.connect(self._clear_output)
        header_row.addWidget(self.clear_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedWidth(50)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {RED};
                color: white;
                border: none;
                font-weight: bold;
            }}
            QPushButton:disabled {{
                background-color: {BG_PANEL};
                color: {TEXT_SEC};
            }}
        """)
        self.stop_btn.clicked.connect(self._stop_process)
        header_row.addWidget(self.stop_btn)

        layout.addLayout(header_row)

        # ── Output terminal ──
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_PANEL};
                color: {TEXT_PRI};
                border: 1px solid {BORDER};
                font-family: {FONT_MONO};
                font-size: 12px;
                selection-background-color: {BLUE};
            }}
        """)
        self.output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.output, 1)

        # ── Input row ──
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        prompt_label = QLabel("claude -p")
        prompt_label.setStyleSheet(
            f"color: {ORANGE}; font-family: {FONT_MONO}; font-size: 12px; "
            f"font-weight: bold; border: none;"
        )
        input_row.addWidget(prompt_label)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a prompt for Claude Code and press Send…")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_PANEL};
                color: {TEXT_PRI};
                border: 1px solid {BORDER};
                padding: 10px 12px;
                font-family: {FONT_MONO};
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ORANGE};
            }}
        """)
        self.input_field.returnPressed.connect(self._send_prompt)
        input_row.addWidget(self.input_field, 1)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedWidth(60)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ORANGE};
                color: #000;
                border: none;
                font-weight: bold;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: #d97706;
            }}
            QPushButton:disabled {{
                background-color: {BG_PANEL};
                color: {TEXT_SEC};
            }}
        """)
        self.send_btn.clicked.connect(self._send_prompt)
        input_row.addWidget(self.send_btn)

        layout.addLayout(input_row)

    # ── Claude installation check ────────────────────────────

    def _check_claude_installed(self):
        self._append_line(
            "Claude Code CLI ready. Type a prompt and press Send.\n",
            color=TEXT_SEC,
        )
        if shutil.which("claude") is None:
            self._append_line(
                "⚠  Warning: 'claude' not found on PATH.\n"
                "   Install Claude Code:  npm install -g @anthropic-ai/claude-code\n"
                "   Then restart this application.\n",
                color=ORANGE,
            )
        else:
            self._append_line(
                f"✓  claude found at: {shutil.which('claude')}\n",
                color=GREEN,
            )

    # ── Process management ───────────────────────────────────

    def _send_prompt(self):
        prompt = self.input_field.text().strip()
        if not prompt:
            return
        if self._process and self._process.state() == QProcess.Running:
            self._append_line("⚠  A process is already running. Stop it first.\n", color=ORANGE)
            return

        self.input_field.clear()

        # Echo the command
        self._append_line(f"\n$ claude -p \"{prompt}\"\n", color=BLUE)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyRead.connect(self._on_ready_read)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_process_error)

        # Set status to running
        self._set_running(True)

        # Build args — split claude binary + flags so QProcess handles escaping
        claude_path = shutil.which("claude") or "claude"
        self._process.start(claude_path, ["-p", prompt])

        if not self._process.waitForStarted(3000):
            self._append_line(
                "✗  Failed to start 'claude'. Is it installed and on PATH?\n",
                color=RED,
            )
            self._set_running(False)

    def _on_ready_read(self):
        if self._process is None:
            return
        data = self._process.readAll()
        text = bytes(data).decode("utf-8", errors="replace")
        # Append without extra newline (text already contains newlines)
        self.output.moveCursor(QTextCursor.End)
        self.output.insertPlainText(text)
        self.output.moveCursor(QTextCursor.End)

    def _on_finished(self, exit_code, exit_status):
        self._set_running(False)
        status_str = "✓ Done" if exit_code == 0 else f"✗ Exited with code {exit_code}"
        color = GREEN if exit_code == 0 else RED
        self._append_line(f"\n{status_str}\n", color=color)

    def _on_process_error(self, error):
        self._set_running(False)
        error_map = {
            QProcess.FailedToStart: "Failed to start — check that 'claude' is on PATH",
            QProcess.Crashed: "Process crashed unexpectedly",
            QProcess.Timedout: "Process timed out",
            QProcess.WriteError: "Write error",
            QProcess.ReadError: "Read error",
            QProcess.UnknownError: "Unknown error",
        }
        msg = error_map.get(error, f"Process error: {error}")
        self._append_line(f"✗  {msg}\n", color=RED)

    def _stop_process(self):
        if self._process and self._process.state() == QProcess.Running:
            self._process.kill()
            self._append_line("\n⚡ Process killed by user.\n", color=ORANGE)
            self._set_running(False)

    # ── Helpers ──────────────────────────────────────────────

    def _set_running(self, running: bool):
        self.send_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.input_field.setEnabled(not running)
        if running:
            self.status_dot.setStyleSheet(
                f"color: {GREEN}; font-size: 16px; border: none;"
            )
            self.status_dot.setToolTip("Process running…")
        else:
            self.status_dot.setStyleSheet(
                f"color: {TEXT_SEC}; font-size: 16px; border: none;"
            )
            self.status_dot.setToolTip("Idle")

    def _append_line(self, text: str, color: str = None):
        """Append styled text to the output terminal."""
        self.output.moveCursor(QTextCursor.End)
        if color:
            fmt = self.output.currentCharFormat()
            fmt.setForeground(QColor(color))
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(text, fmt)
        else:
            self.output.insertPlainText(text)
        self.output.moveCursor(QTextCursor.End)

    def _clear_output(self):
        self.output.clear()
        self._append_line("Terminal cleared.\n", color=TEXT_SEC)


# ═══════════════════════════════════════════════════════════════
#  Inner AI Chat Panel  (moved to private class, unchanged logic)
# ═══════════════════════════════════════════════════════════════

class _AIChatPanel(QWidget):
    """Claude AI Chat — internal widget for Tab 1."""

    optimize_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")

        self._messages = []
        self._bubbles = []
        self._worker = None
        self._streaming_bubble = None
        self._streaming_text = ""
        self._pending_full_prompt = None

        self._backtest_context = "No backtest has been run yet."
        self._strategy_import_callback = None
        self._strategy_replace_callback = None

        self._strategies_dir = ""
        self._current_strategy_name = ""

        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Header Row ──
        header_row = QHBoxLayout()
        header = QLabel("Claude AI")
        header.setStyleSheet(
            f"color: {PURPLE}; font-size: 14px; font-weight: bold; border: none;"
        )
        header_row.addWidget(header)
        header_row.addStretch()

        self.api_key_btn = QPushButton("API Key")
        self.api_key_btn.setFixedWidth(70)
        self.api_key_btn.clicked.connect(self._show_api_key_dialog)
        header_row.addWidget(self.api_key_btn)
        layout.addLayout(header_row)

        # ── Model selector ──
        model_row = QHBoxLayout()
        model_lbl = QLabel("Model:")
        model_lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 10px; border: none;")
        model_row.addWidget(model_lbl)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "claude-sonnet-4-20250514",
            "claude-haiku-4-5-20241022",
        ])
        self.model_combo.setCurrentText("claude-sonnet-4-20250514")
        model_row.addWidget(self.model_combo, 1)
        layout.addLayout(model_row)

        # ── Token Usage ──
        self.token_label = QLabel("Tokens: 0 | Cost: $0.00")
        self.token_label.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 9px; border: none;"
        )
        layout.addWidget(self.token_label)

        # ── Chat Scroll Area ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {BG_DEEP};
                border: 1px solid {BORDER};
            }}
        """)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet(f"background-color: {BG_DEEP};")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(4, 4, 4, 4)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()

        self.scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.scroll_area, 1)

        self._add_welcome_message()

        # ── Suggested Prompts ──
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(4)
        for s in SUGGESTED_PROMPTS[:3]:
            chip = QPushButton(s)
            chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {BG_PANEL};
                    color: {TEXT_SEC};
                    border: 1px solid {BORDER};
                    padding: 4px 8px;
                    font-size: 10px;
                    border-radius: 10px;
                }}
                QPushButton:hover {{
                    color: {TEXT_PRI};
                    border-color: {PURPLE};
                }}
            """)
            chip.setFixedHeight(26)
            chip.clicked.connect(lambda checked, txt=s: self._send_suggested(txt))
            chips_layout.addWidget(chip)
        chips_layout.addStretch()
        layout.addLayout(chips_layout)

        # ── Action Buttons Row ──
        btn_row = QHBoxLayout()

        paste_err_btn = QPushButton("Paste Errors")
        paste_err_btn.setFixedWidth(90)
        paste_err_btn.clicked.connect(self._show_paste_errors_dialog)
        btn_row.addWidget(paste_err_btn)

        self.optimize_btn = QPushButton("Auto-Optimize")
        self.optimize_btn.setFixedWidth(100)
        self.optimize_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ORANGE}; color: #000;
                border: none; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #d97706; }}
        """)
        self.optimize_btn.clicked.connect(self.optimize_requested.emit)
        btn_row.addWidget(self.optimize_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(50)
        clear_btn.clicked.connect(self._clear_chat)
        btn_row.addWidget(clear_btn)

        export_btn = QPushButton("Export")
        export_btn.setFixedWidth(55)
        export_btn.clicked.connect(self._export_chat)
        btn_row.addWidget(export_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Input Area ──
        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask Claude about your backtest...")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_PANEL};
                color: {TEXT_PRI};
                border: 1px solid {BORDER};
                padding: 10px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {PURPLE};
            }}
        """)
        self.input_field.returnPressed.connect(self._send_message)
        input_row.addWidget(self.input_field, 1)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primary")
        self.send_btn.setFixedWidth(60)
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        # Load saved settings
        settings = load_settings()
        if settings.get("api_key"):
            self._api_key = settings["api_key"]
            self.api_key_btn.setText("Key Set")
        else:
            self._api_key = ""
        if settings.get("model"):
            self.model_combo.setCurrentText(settings["model"])

    # ── Welcome ──────────────────────────────────────────────

    def _add_welcome_message(self):
        welcome = ChatBubble(
            "Hi! I'm Claude, your AI trading assistant. I can see your "
            "backtest results and help you:\n"
            "- Analyse what's working and failing\n"
            "- Write new strategy code\n"
            "- Diagnose and fix backtest errors\n"
            "- Auto-optimize strategies with AI\n\n"
            "Run a backtest and ask me anything!",
            is_user=False
        )
        idx = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(idx, welcome)

    # ── API Key ──────────────────────────────────────────────

    def _show_api_key_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Anthropic API Key")
        dialog.setFixedSize(400, 150)
        dialog.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRI};")

        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.addWidget(QLabel("Enter your Anthropic API key:"))

        key_input = QLineEdit()
        key_input.setEchoMode(QLineEdit.Password)
        key_input.setPlaceholderText("sk-ant-...")
        if self._api_key:
            key_input.setText(self._api_key)
        dlg_layout.addWidget(key_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)

        if dialog.exec_() == QDialog.Accepted:
            self._api_key = key_input.text().strip()
            settings = load_settings()
            settings["api_key"] = self._api_key
            save_settings(settings)
            self.api_key_btn.setText("Key Set" if self._api_key else "API Key")

    # ── Paste Errors Dialog ──────────────────────────────────

    def _show_paste_errors_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Paste Backtest Errors")
        dialog.setMinimumSize(500, 300)
        dialog.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRI};")

        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.addWidget(QLabel("Paste your raw error text below:"))

        error_edit = QTextEdit()
        error_edit.setPlaceholderText("e.g.: Traceback ...")
        error_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_DEEP};
                color: {TEXT_PRI};
                font-family: {FONT_MONO};
                font-size: 11px;
                border: 1px solid {BORDER};
            }}
        """)
        dlg_layout.addWidget(error_edit, 1)

        attach_btn = QPushButton("Attach to Next Message")
        attach_btn.setObjectName("primary")
        attach_btn.clicked.connect(
            lambda: self._attach_errors(error_edit.toPlainText(), dialog)
        )
        dlg_layout.addWidget(attach_btn)

        dialog.exec_()

    def _attach_errors(self, raw_text, dialog):
        if not raw_text.strip():
            return
        prompt = self.build_error_fix_prompt(raw_text)
        self.input_field.setText(prompt[:500])
        self._pending_full_prompt = prompt
        dialog.accept()

    # ── Error-Fix Prompt Builder ─────────────────────────────

    def build_error_fix_prompt(self, raw_error_text: str) -> str:
        strategy_code = self._get_active_strategy_code()
        prompt_parts = [
            "I'm getting the following errors from my backtest. "
            "Please diagnose what's wrong and provide a fixed version of the strategy code.\n",
            "## Errors:\n```\n" + raw_error_text.strip() + "\n```\n",
        ]
        if strategy_code:
            prompt_parts.append(
                "## Current Strategy Code:\n```python\n" + strategy_code + "\n```\n"
            )
        prompt_parts.append(
            "## What I need:\n"
            "1. Explain what is causing each error in plain English\n"
            "2. Identify the exact lines in the strategy that need to change\n"
            "3. Provide the complete fixed strategy function\n"
            "4. Explain what you changed and why it prevents the error\n"
        )
        return "\n".join(prompt_parts)

    def _get_active_strategy_code(self) -> str:
        if not self._strategies_dir or not self._current_strategy_name:
            return ""
        name = self._current_strategy_name
        candidates = [
            name.lower().replace(" ", "_").replace("-", "_") + ".py",
            name.lower().replace("_", "") + ".py",
        ]
        clean_name = name.lstrip("\u26a1").strip()
        candidates.append(
            clean_name.lower().replace(" ", "_").replace("-", "_") + ".py"
        )
        for filename in candidates:
            filepath = os.path.join(self._strategies_dir, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath) as f:
                        return f.read()
                except Exception:
                    pass
        return ""

    # ── Context / Callbacks ──────────────────────────────────

    def set_backtest_context(self, context_str: str):
        self._backtest_context = context_str

    def set_strategy_import_callback(self, callback):
        self._strategy_import_callback = callback

    def set_strategy_replace_callback(self, callback):
        self._strategy_replace_callback = callback

    def set_strategies_dir(self, path: str):
        self._strategies_dir = path

    def set_current_strategy_name(self, name: str):
        self._current_strategy_name = name

    def get_api_key(self):
        return self._api_key

    # ── Send Messages ────────────────────────────────────────

    def _send_suggested(self, text):
        self.input_field.setText(text)
        self._send_message()

    def _send_message(self):
        if hasattr(self, "_pending_full_prompt") and self._pending_full_prompt:
            text = self._pending_full_prompt
            self._pending_full_prompt = None
        else:
            text = self.input_field.text().strip()

        if not text:
            return
        if not self._api_key:
            self._show_api_key_dialog()
            if not self._api_key:
                return

        self.input_field.clear()

        is_error_mode = _detect_errors(text)

        display_text = text if len(text) <= 500 else text[:500] + "..."
        user_bubble = ChatBubble(display_text, is_user=True)
        idx = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(idx, user_bubble)
        self._bubbles.append(user_bubble)

        self._messages.append({"role": "user", "content": text})

        self._streaming_bubble = ChatBubble("...", is_user=False)
        idx = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(idx, self._streaming_bubble)
        self._bubbles.append(self._streaming_bubble)
        self._streaming_text = ""

        self._scroll_to_bottom()

        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)

        system = SYSTEM_PROMPT.replace("{BACKTEST_CONTEXT}", self._backtest_context)
        if is_error_mode:
            system += "\n\n" + ERROR_FIX_ADDENDUM

        self._worker = ClaudeWorker(
            api_key=self._api_key,
            model=self.model_combo.currentText(),
            messages=list(self._messages),
            system_prompt=system,
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.token_usage.connect(self._on_token_usage)
        self._worker.start()

    def _on_chunk(self, text):
        self._streaming_text += text
        if self._streaming_bubble:
            self._streaming_bubble.set_text(self._streaming_text)
        self._scroll_to_bottom()

    def _on_finished(self, full_text):
        self._messages.append({"role": "assistant", "content": full_text})
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_field.setFocus()

        if "[STRATEGY_READY]" in full_text:
            self._add_import_button(full_text)

    def _on_error(self, error_msg):
        if self._streaming_bubble:
            self._streaming_bubble.set_text(f"Error: {error_msg}")
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_field.setFocus()

    def _on_token_usage(self, inp, out, cost):
        self._total_input_tokens += inp
        self._total_output_tokens += out
        self._total_cost += cost
        self.token_label.setText(
            f"Tokens: {self._total_input_tokens + self._total_output_tokens:,} | "
            f"Cost: ${self._total_cost:.4f}"
        )

    # ── Optimizer status ─────────────────────────────────────

    def add_optimizer_message(self, text):
        bubble = ChatBubble(text, is_user=False)
        idx = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(idx, bubble)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()

    # ── Strategy Import / Replace ────────────────────────────

    def _add_import_button(self, full_text):
        has_active = bool(self._current_strategy_name)

        if has_active and self._strategy_replace_callback:
            btn_text = (
                f"Import Fixed Strategy \u2014 replaces {self._current_strategy_name}"
            )
            btn = QPushButton(btn_text)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ORANGE};
                    color: #000;
                    border: none;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{ background-color: #d97706; }}
            """)
            btn.clicked.connect(lambda: self._replace_strategy(full_text))
        else:
            btn = QPushButton("Import This Strategy")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {GREEN};
                    color: #000;
                    border: none;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{ background-color: #00cc6a; }}
            """)
            btn.clicked.connect(lambda: self._import_strategy(full_text))

        idx = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(idx, btn)

    def _import_strategy(self, full_text):
        if self._strategy_import_callback:
            from core.strategy_loader import extract_strategy_code
            code = extract_strategy_code(full_text)
            if code:
                self._strategy_import_callback(code)

    def _replace_strategy(self, full_text):
        if self._strategy_replace_callback:
            from core.strategy_loader import extract_strategy_code
            code = extract_strategy_code(full_text)
            if code:
                self._strategy_replace_callback(self._current_strategy_name, code)

    # ── Scroll / Clear / Export ───────────────────────────────

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _clear_chat(self):
        self._messages.clear()
        self._pending_full_prompt = None
        for bubble in self._bubbles:
            bubble.deleteLater()
        self._bubbles.clear()
        for i in reversed(range(self.chat_layout.count())):
            widget = self.chat_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton) and "Import" in (widget.text() or ""):
                widget.deleteLater()
        self._add_welcome_message()

    def _export_chat(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Chat History",
            f"chat_history_{datetime.now().strftime('%Y%m%d')}.json",
            "JSON Files (*.json)"
        )
        if filepath:
            export_chat(self._messages, filepath)

    def save_model_setting(self):
        settings = load_settings()
        settings["model"] = self.model_combo.currentText()
        save_settings(settings)


# ═══════════════════════════════════════════════════════════════
#  Public ChatPanel  — tabbed wrapper (drop-in replacement)
# ═══════════════════════════════════════════════════════════════

class ChatPanel(QWidget):
    """
    Drop-in replacement for the original ChatPanel.

    Presents a QTabWidget with:
      Tab 0 — "Claude AI Chat"   (_AIChatPanel, full original functionality)
      Tab 1 — "Claude Code CLI"  (ClaudeCodePanel, QProcess terminal)

    All public methods and signals from the original ChatPanel are
    forwarded to the inner _AIChatPanel so the rest of the app needs
    zero changes.
    """

    # Forward the signal so external connects still work
    optimize_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setStyleSheet(
            f"background-color: {BG_DEEP}; border-left: 1px solid {BORDER};"
        )
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background-color: {BG_DEEP};
                border: none;
                border-top: 1px solid {BORDER};
            }}
            QTabBar::tab {{
                background-color: {BG_PANEL};
                color: {TEXT_SEC};
                border: 1px solid {BORDER};
                border-bottom: none;
                padding: 7px 18px;
                font-size: 11px;
                font-weight: bold;
                min-width: 120px;
            }}
            QTabBar::tab:selected {{
                background-color: {BG_DEEP};
                color: {TEXT_PRI};
                border-bottom: 2px solid {PURPLE};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {BG_HOVER};
                color: {TEXT_PRI};
            }}
            /* Tab 1 accent — orange for Claude Code */
            QTabBar::tab:last {{
                border-bottom: none;
            }}
            QTabBar::tab:last:selected {{
                border-bottom: 2px solid {ORANGE};
            }}
        """)

        # ── Tab 0: Claude AI Chat ──
        self._ai_chat = _AIChatPanel()
        self._ai_chat.optimize_requested.connect(self.optimize_requested.emit)
        self.tabs.addTab(self._ai_chat, "🤖  Claude AI Chat")

        # ── Tab 1: Claude Code CLI ──
        self._code_cli = ClaudeCodePanel()
        self.tabs.addTab(self._code_cli, "⚡  Claude Code CLI")

        layout.addWidget(self.tabs)

    # ── Forwarded attributes (main_window.py accesses these directly) ──

    @property
    def model_combo(self):
        return self._ai_chat.model_combo

    @property
    def api_key_btn(self):
        return self._ai_chat.api_key_btn

    @property
    def token_label(self):
        return self._ai_chat.token_label

    @property
    def input_field(self):
        return self._ai_chat.input_field

    @property
    def send_btn(self):
        return self._ai_chat.send_btn

    @property
    def optimize_btn(self):
        return self._ai_chat.optimize_btn

    @property
    def scroll_area(self):
        return self._ai_chat.scroll_area

    @property
    def chat_layout(self):
        return self._ai_chat.chat_layout

    @property
    def _api_key(self):
        return self._ai_chat._api_key

    @property
    def _messages(self):
        return self._ai_chat._messages

    @property
    def _backtest_context(self):
        return self._ai_chat._backtest_context

    # ── Public API — all forwarded to _AIChatPanel ───────────

    def set_backtest_context(self, context_str: str):
        self._ai_chat.set_backtest_context(context_str)

    def set_strategy_import_callback(self, callback):
        self._ai_chat.set_strategy_import_callback(callback)

    def set_strategy_replace_callback(self, callback):
        self._ai_chat.set_strategy_replace_callback(callback)

    def set_strategies_dir(self, path: str):
        self._ai_chat.set_strategies_dir(path)

    def set_current_strategy_name(self, name: str):
        self._ai_chat.set_current_strategy_name(name)

    def get_api_key(self):
        return self._ai_chat.get_api_key()

    def add_optimizer_message(self, text: str):
        self._ai_chat.add_optimizer_message(text)
        # Switch to the AI tab so the message is visible
        self.tabs.setCurrentIndex(0)

    def build_error_fix_prompt(self, raw_error_text: str) -> str:
        return self._ai_chat.build_error_fix_prompt(raw_error_text)

    def save_model_setting(self):
        self._ai_chat.save_model_setting()

    # ── Convenience: switch to CLI tab programmatically ──────

    def show_cli_tab(self):
        self.tabs.setCurrentIndex(1)

    def show_chat_tab(self):
        self.tabs.setCurrentIndex(0)