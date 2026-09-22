"""
m3emz Backtester — Config Panel (Left Sidebar)
With strategy notes, cache status indicator, and force re-fetch.
"""

import os
from datetime import datetime, timezone
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QDoubleSpinBox, QListWidget, QListWidgetItem,
    QPushButton, QFileDialog, QAbstractItemView, QSizePolicy,
    QCheckBox, QMenu, QAction, QDialog, QTextEdit, QDialogButtonBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from utils.theme import (
    BG_PANEL, BG_DEEP, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, ORANGE, FONT_MONO
)
from utils.helpers import load_strategy_notes, save_strategy_notes

# Default watchlist for multi-symbol mode
DEFAULT_WATCHLIST = [
    ("BTCUSDT",   True,  "Bitcoin"),
    ("ETHUSDT",   True,  "Ethereum"),
    ("SOLUSDT",   True,  "Solana"),
    ("BNBUSDT",   False, "BNB"),
    ("XRPUSDT",   False, "XRP"),
    ("DOGEUSDT",  False, "Dogecoin"),
    ("ADAUSDT",   False, "Cardano"),
    ("AVAXUSDT",  False, "Avalanche"),
    ("LINKUSDT",  False, "Chainlink"),
    ("MATICUSDT", False, "Polygon"),
]


class ConfigPanel(QWidget):
    """Left sidebar with all backtest configuration controls."""

    run_clicked = pyqtSignal()
    run_all_clicked = pyqtSignal()
    compare_clicked = pyqtSignal()
    save_clicked = pyqtSignal()
    import_clicked = pyqtSignal(str)  # filepath
    force_refetch = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self.setStyleSheet(f"background-color: {BG_PANEL}; border-right: 1px solid {BORDER};")

        self._strategy_results = {}  # name -> {return_pct, trades}
        self._strategy_notes = load_strategy_notes()

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # ── Header ──
        header = QLabel("CONFIGURATION")
        header.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: bold; border: none; padding-bottom: 4px;")
        layout.addWidget(header)

        # ── Symbol (single mode) ──
        self._symbol_label = self._make_label("Symbol")
        layout.addWidget(self._symbol_label)
        self.symbol_input = QLineEdit("BTCUSDT")
        self.symbol_input.setPlaceholderText("e.g. ETHUSDT")
        self.symbol_input.textChanged.connect(
            lambda t: self.symbol_input.setText(t.upper()) if t != t.upper() else None
        )
        self.symbol_input.textChanged.connect(self._update_cache_status)
        layout.addWidget(self.symbol_input)

        # ── Cache Status ──
        cache_row = QHBoxLayout()
        cache_row.setSpacing(4)
        self.cache_dot = QLabel("\u25cf")
        self.cache_dot.setStyleSheet(f"color: {TEXT_SEC}; font-size: 10px; border: none;")
        cache_row.addWidget(self.cache_dot)
        self.cache_label = QLabel("No cache")
        self.cache_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 9px; border: none;")
        cache_row.addWidget(self.cache_label, 1)
        self.refetch_btn = QPushButton("Refresh")
        self.refetch_btn.setFixedHeight(22)
        self.refetch_btn.setFixedWidth(55)
        self.refetch_btn.setStyleSheet(f"font-size: 9px; padding: 2px 6px;")
        self.refetch_btn.clicked.connect(self.force_refetch.emit)
        cache_row.addWidget(self.refetch_btn)
        layout.addLayout(cache_row)

        # ── Multi-Symbol Toggle ──
        self.multi_mode_cb = QCheckBox("Multi-Symbol Mode")
        self.multi_mode_cb.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px;")
        self.multi_mode_cb.stateChanged.connect(self._toggle_multi_mode)
        layout.addWidget(self.multi_mode_cb)

        # ── Watchlist (hidden by default) ──
        self.watchlist_widget = QWidget()
        self.watchlist_widget.setVisible(False)
        wl_layout = QVBoxLayout(self.watchlist_widget)
        wl_layout.setContentsMargins(0, 0, 0, 0)
        wl_layout.setSpacing(2)

        wl_header = self._make_label("Watchlist")
        wl_layout.addWidget(wl_header)

        self.watchlist = QListWidget()
        self.watchlist.setSelectionMode(QAbstractItemView.NoSelection)
        self.watchlist.setMaximumHeight(180)
        for symbol, checked, label in DEFAULT_WATCHLIST:
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            item.setData(Qt.UserRole, symbol)
            item.setText(f"  {symbol:<12} {label}")
            self.watchlist.addItem(item)
        wl_layout.addWidget(self.watchlist)

        # Custom symbol add row
        add_row = QHBoxLayout()
        self.custom_symbol_input = QLineEdit()
        self.custom_symbol_input.setPlaceholderText("DOTUSDT")
        self.custom_symbol_input.setFixedHeight(28)
        self.custom_symbol_input.textChanged.connect(
            lambda t: self.custom_symbol_input.setText(t.upper()) if t != t.upper() else None
        )
        add_row.addWidget(self.custom_symbol_input, 1)
        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(28)
        add_btn.setFixedWidth(50)
        add_btn.clicked.connect(self._add_custom_symbol)
        add_row.addWidget(add_btn)
        wl_layout.addLayout(add_row)

        layout.addWidget(self.watchlist_widget)

        # ── Interval ──
        layout.addWidget(self._make_label("Interval"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"])
        self.interval_combo.setCurrentText("1h")
        self.interval_combo.currentTextChanged.connect(self._update_cache_status)
        layout.addWidget(self.interval_combo)

        # ── Lookback ──
        layout.addWidget(self._make_label("Lookback"))
        self.lookback_input = QLineEdit("180 days ago")
        self.lookback_input.setPlaceholderText("e.g. 90 days ago / 6 months ago")
        layout.addWidget(self.lookback_input)
        hint = QLabel("e.g. 90 days ago / 6 months ago")
        hint.setStyleSheet(f"color: {TEXT_SEC}; font-size: 10px; border: none; padding: 0;")
        layout.addWidget(hint)

        # ── Starting Cash ──
        layout.addWidget(self._make_label("Starting Cash"))
        self.cash_spin = QDoubleSpinBox()
        self.cash_spin.setRange(100, 10_000_000)
        self.cash_spin.setValue(10000)
        self.cash_spin.setSingleStep(1000)
        self.cash_spin.setPrefix("$ ")
        self.cash_spin.setDecimals(0)
        layout.addWidget(self.cash_spin)

        # ── Commission ──
        layout.addWidget(self._make_label("Commission"))
        self.commission_spin = QDoubleSpinBox()
        self.commission_spin.setRange(0, 1)
        self.commission_spin.setValue(0.1)
        self.commission_spin.setSingleStep(0.05)
        self.commission_spin.setDecimals(3)
        self.commission_spin.setSuffix(" %")
        layout.addWidget(self.commission_spin)

        # ── Strategy Section ──
        layout.addSpacing(8)
        strat_header = QLabel("STRATEGIES")
        strat_header.setAlignment(Qt.AlignCenter)
        strat_header.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(strat_header)

        # ── Strategy List ──
        self.strategy_list = QListWidget()
        self.strategy_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.strategy_list.setMinimumHeight(120)
        self.strategy_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.strategy_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.strategy_list.customContextMenuRequested.connect(self._show_strategy_context_menu)
        layout.addWidget(self.strategy_list, 1)

        # ── Import Button ──
        import_btn = QPushButton("Import Strategy .py")
        import_btn.clicked.connect(self._on_import)
        layout.addWidget(import_btn)

        # ── Action Buttons ──
        self.run_btn = QPushButton("Run Selected")
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self.run_clicked.emit)
        layout.addWidget(self.run_btn)

        btn_row = QHBoxLayout()
        compare_btn = QPushButton("Compare All")
        compare_btn.clicked.connect(self.compare_clicked.emit)
        btn_row.addWidget(compare_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_clicked.emit)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        # Initial cache status
        self._update_cache_status()

    # ── Cache Status ────────────────────────────────────
    def _update_cache_status(self, *_):
        try:
            from utils.cache import get_cache_info
            symbol = self.symbol_input.text().strip().upper()
            interval = self.interval_combo.currentText()
            info = get_cache_info(symbol, interval)
            if info:
                candles = info.get("candles", 0)
                updated = info.get("last_updated", "")
                # Parse age
                try:
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                    if age_hours < 24:
                        self.cache_dot.setStyleSheet(f"color: {GREEN}; font-size: 10px; border: none;")
                        age_str = f"{age_hours:.0f}h ago"
                    else:
                        self.cache_dot.setStyleSheet(f"color: {ORANGE}; font-size: 10px; border: none;")
                        age_str = f"{age_hours/24:.0f}d ago"
                except Exception:
                    self.cache_dot.setStyleSheet(f"color: {ORANGE}; font-size: 10px; border: none;")
                    age_str = "?"
                self.cache_label.setText(f"{candles:,} candles | {age_str}")
            else:
                self.cache_dot.setStyleSheet(f"color: {TEXT_SEC}; font-size: 10px; border: none;")
                self.cache_label.setText("No cache")
        except Exception:
            self.cache_dot.setStyleSheet(f"color: {TEXT_SEC}; font-size: 10px; border: none;")
            self.cache_label.setText("No cache")

    # ── Strategy Notes (right-click) ────────────────────
    def _show_strategy_context_menu(self, pos):
        item = self.strategy_list.itemAt(pos)
        if not item:
            return

        name = item.data(Qt.UserRole)
        if not name:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {BG_PANEL}; color: {TEXT_PRI}; border: 1px solid {BORDER}; }}
            QMenu::item:selected {{ background: {BLUE}; }}
        """)

        notes_action = QAction("Edit Notes...", self)
        notes_action.triggered.connect(lambda: self._edit_strategy_notes(name))
        menu.addAction(notes_action)

        menu.exec_(self.strategy_list.mapToGlobal(pos))

    def _edit_strategy_notes(self, strategy_name):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Notes: {strategy_name}")
        dialog.setMinimumSize(350, 200)
        dialog.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRI};")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Strategy notes for {strategy_name}:"))

        editor = QTextEdit()
        editor.setPlaceholderText("Write your notes about this strategy...")
        current_notes = self._strategy_notes.get(strategy_name, "")
        editor.setText(current_notes)
        layout.addWidget(editor)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() == QDialog.Accepted:
            self._strategy_notes[strategy_name] = editor.toPlainText()
            save_strategy_notes(self._strategy_notes)

    # ── Multi-symbol helpers ─────────────────────────────

    def _toggle_multi_mode(self, state):
        multi = state == Qt.Checked
        self.symbol_input.setVisible(not multi)
        self._symbol_label.setVisible(not multi)
        self.watchlist_widget.setVisible(multi)

    def _add_custom_symbol(self):
        text = self.custom_symbol_input.text().strip().upper()
        if not text:
            return
        for idx in range(self.watchlist.count()):
            if self.watchlist.item(idx).data(Qt.UserRole) == text:
                return
        item = QListWidgetItem()
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setData(Qt.UserRole, text)
        item.setText(f"  {text:<12} Custom")
        self.watchlist.addItem(item)
        self.custom_symbol_input.clear()

    def get_checked_watchlist(self) -> list:
        checked = []
        for idx in range(self.watchlist.count()):
            item = self.watchlist.item(idx)
            if item.checkState() == Qt.Checked:
                checked.append(item.data(Qt.UserRole))
        return checked

    @property
    def is_multi_mode(self) -> bool:
        return self.multi_mode_cb.isChecked()

    # ── General helpers ──────────────────────────────────

    def _make_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: bold; border: none; padding-top: 4px;")
        return label

    def _on_import(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Strategy File", "", "Python Files (*.py)"
        )
        if filepath:
            self.import_clicked.emit(filepath)

    def add_strategy(self, name: str):
        for idx in range(self.strategy_list.count()):
            if self.strategy_list.item(idx).data(Qt.UserRole) == name:
                return
        item = QListWidgetItem()
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setData(Qt.UserRole, name)
        # Show note indicator if notes exist
        has_note = "\u270e" if self._strategy_notes.get(name) else ""
        item.setText(f"  {name:<22}  \u2014      \u2014   \u25cb {has_note}")
        self.strategy_list.addItem(item)

    def update_strategy_result(self, name: str, return_pct: float, trade_count: int):
        self._strategy_results[name] = {"return": return_pct, "trades": trade_count}
        for idx in range(self.strategy_list.count()):
            item = self.strategy_list.item(idx)
            if item.data(Qt.UserRole) == name:
                sign = "+" if return_pct >= 0 else ""
                has_note = "\u270e" if self._strategy_notes.get(name) else ""
                item.setText(f"  {name:<22} {sign}{return_pct:.1f}%  {trade_count}T  \u25cf {has_note}")
                item.setForeground(QColor(GREEN if return_pct >= 0 else RED))
                break

    def get_checked_strategies(self) -> list:
        checked = []
        for idx in range(self.strategy_list.count()):
            item = self.strategy_list.item(idx)
            if item.checkState() == Qt.Checked:
                checked.append(item.data(Qt.UserRole))
        return checked

    def get_config(self) -> dict:
        cfg = {
            "interval": self.interval_combo.currentText(),
            "lookback": self.lookback_input.text().strip(),
            "cash": self.cash_spin.value(),
            "commission": self.commission_spin.value() / 100.0,
        }
        if self.is_multi_mode:
            cfg["symbols"] = self.get_checked_watchlist()
            cfg["symbol"] = cfg["symbols"][0] if cfg["symbols"] else "BTCUSDT"
        else:
            cfg["symbol"] = self.symbol_input.text().strip().upper()
        return cfg

    def set_config(self, settings: dict):
        if settings.get("last_symbol"):
            self.symbol_input.setText(settings["last_symbol"])
        if settings.get("last_interval"):
            self.interval_combo.setCurrentText(settings["last_interval"])
        if settings.get("last_lookback"):
            self.lookback_input.setText(settings["last_lookback"])
        if settings.get("last_cash"):
            self.cash_spin.setValue(settings["last_cash"])
        if settings.get("last_commission"):
            self.commission_spin.setValue(settings["last_commission"] * 100)

    def set_running(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.run_btn.setText("Running..." if running else "Run Selected")
