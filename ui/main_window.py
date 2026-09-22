"""
m3emz Backtester — Main Window
Integrates all panels: chart, stats, chat, trade journal, robustness,
live trading, DNA/portfolio, seasonality. Keyboard shortcuts & theme toggle.
"""

import os
import sys
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QStatusBar, QLabel, QProgressBar, QMessageBox, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton, QTabWidget, QShortcut, QFileDialog, QApplication
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QKeySequence

from utils.theme import (
    BG_DEEP, BG_PANEL, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, ORANGE, STYLESHEET, apply_theme
)
from utils.helpers import (
    FetchWorker, CachedFetchWorker, MultiFetchWorker, BacktestWorker,
    ToastNotification, load_settings, save_settings, export_results,
    export_html_report
)
from core.fetcher import BinanceFetcher
from core.strategy_loader import (
    load_all_strategies, load_strategy_from_file,
    save_strategy_code, extract_strategy_code
)
from ui.config_panel import ConfigPanel
from ui.chart_panel import ChartPanel
from ui.stats_panel import StatsPanel
from ui.chat_panel import ChatPanel
from ui.trade_journal import TradeJournal
from ui.robustness_panel import RobustnessPanel
from ui.seasonality import SeasonalityPanel
from ui.live_panel import LivePanel
from ui.dna_panel import DNAPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Backtester")
        self.setMinimumSize(1400, 800)

        self._df = None
        self._multi_dfs = {}
        self._strategies = {}
        self._all_results = {}
        self._all_bt_results = {}  # name -> (backtester, stats, trades) for DNA panel
        self._last_stats = None
        self._last_strategy_name = None
        self._last_strategy_fn = None
        self._last_trades = []
        self._fetch_worker = None
        self._multi_fetch_worker = None
        self._backtest_workers = []
        self._run_queue = []
        self._multi_run_queue = []
        self._pending_strategy_fns = {}  # name -> fn, populated just before worker starts
        self._is_dark_theme = True
        self._optimizer_thread = None
        self._regimes = None

        self._build_ui()
        self._setup_shortcuts()
        self._load_strategies()
        self._restore_settings()

    def _build_ui(self):
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top Bar ──
        topbar = QWidget()
        topbar.setFixedHeight(44)
        topbar.setStyleSheet(f"background-color: {BG_PANEL}; border-bottom: 1px solid {BORDER};")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("Backtester")
        title.setStyleSheet(f"color: {TEXT_PRI}; font-size: 16px; font-weight: bold; border: none;")
        topbar_layout.addWidget(title)
        topbar_layout.addStretch()

        # Theme toggle
        self.theme_btn = QPushButton("Light")
        self.theme_btn.setFixedWidth(55)
        self.theme_btn.clicked.connect(self._toggle_theme)
        topbar_layout.addWidget(self.theme_btn)

        # Export Report button
        report_btn = QPushButton("Export Report")
        report_btn.setFixedWidth(100)
        report_btn.clicked.connect(self._export_report)
        topbar_layout.addWidget(report_btn)

        version_lbl = QLabel("v3.0")
        version_lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 10px; border: none;")
        topbar_layout.addWidget(version_lbl)

        main_layout.addWidget(topbar)

        # ── Three-Column Splitter ──
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(2)

        # Left: Config Panel
        self.config_panel = ConfigPanel()
        self.config_panel.run_clicked.connect(self._on_run)
        self.config_panel.compare_clicked.connect(self._on_compare_all)
        self.config_panel.save_clicked.connect(self._on_save)
        self.config_panel.import_clicked.connect(self._on_import_strategy)
        self.config_panel.force_refetch.connect(self._on_force_refetch)
        self.splitter.addWidget(self.config_panel)

        # Center: Tabbed panels
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.center_tabs = QTabWidget()
        self.center_tabs.setTabPosition(QTabWidget.North)

        # Tab 1: Chart + Stats
        chart_stats_widget = QWidget()
        cs_layout = QVBoxLayout(chart_stats_widget)
        cs_layout.setContentsMargins(0, 0, 0, 0)
        cs_layout.setSpacing(0)
        self.chart_panel = ChartPanel()
        cs_layout.addWidget(self.chart_panel, 1)
        self.stats_panel = StatsPanel()
        cs_layout.addWidget(self.stats_panel)
        self.center_tabs.addTab(chart_stats_widget, "Chart")

        # Tab 2: Trade Journal
        self.trade_journal = TradeJournal()
        self.trade_journal.jump_to_trade.connect(self._on_jump_to_trade)
        self.center_tabs.addTab(self.trade_journal, "Journal")

        # Tab 3: Robustness
        self.robustness_panel = RobustnessPanel()
        self.center_tabs.addTab(self.robustness_panel, "Robustness")

        # Tab 4: Seasonality
        self.seasonality_panel = SeasonalityPanel()
        self.center_tabs.addTab(self.seasonality_panel, "Seasonality")

        # Tab 5: Live Paper Trading
        self.live_panel = LivePanel()
        self.center_tabs.addTab(self.live_panel, "Live")

        # Tab 6: Strategy DNA & Portfolio
        self.dna_panel = DNAPanel()
        self.center_tabs.addTab(self.dna_panel, "DNA")

        center_layout.addWidget(self.center_tabs, 1)
        self.splitter.addWidget(center_widget)

        # Right: Chat Panel
        self.chat_panel = ChatPanel()
        self.chat_panel.set_strategy_import_callback(self._import_strategy_code)
        self.chat_panel.set_strategy_replace_callback(self._replace_strategy_code)
        self.chat_panel.optimize_requested.connect(self._on_auto_optimize)
        self.splitter.addWidget(self.chat_panel)

        self.splitter.setSizes([280, 700, 320])
        main_layout.addWidget(self.splitter, 1)

        # ── Status Bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {TEXT_SEC};")
        self.status_bar.addWidget(self.status_label, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

    # ══════════════════════════════════════════════════════
    # Keyboard Shortcuts
    # ══════════════════════════════════════════════════════

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+R"), self, self._on_run)
        QShortcut(QKeySequence("Ctrl+L"), self, lambda: self.config_panel.symbol_input.setFocus())
        QShortcut(QKeySequence("Ctrl+T"), self, lambda: self.center_tabs.setCurrentWidget(self.trade_journal))
        QShortcut(QKeySequence("Ctrl+P"), self, lambda: self.center_tabs.setCurrentWidget(self.live_panel))
        QShortcut(QKeySequence("Ctrl+K"), self, lambda: self.chat_panel.input_field.setFocus())
        QShortcut(QKeySequence("F5"), self, self._on_force_refetch_and_run)
        QShortcut(QKeySequence("Escape"), self, self._cancel_backtest)

    def _on_force_refetch_and_run(self):
        self._force_refetch = True
        self._on_run()

    def _cancel_backtest(self):
        self._run_queue.clear()
        self._multi_run_queue.clear()
        for w in self._backtest_workers:
            if w.isRunning():
                w.terminate()
        self._backtest_workers.clear()
        self.config_panel.set_running(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Cancelled")

    # ══════════════════════════════════════════════════════
    # Theme Toggle
    # ══════════════════════════════════════════════════════

    def _toggle_theme(self):
        self._is_dark_theme = not self._is_dark_theme
        apply_theme(QApplication.instance(), self._is_dark_theme)
        self.theme_btn.setText("Light" if self._is_dark_theme else "Dark")

    # ══════════════════════════════════════════════════════
    # Strategy Loading
    # ══════════════════════════════════════════════════════

    def _load_strategies(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        strategies_dir = os.path.join(base_dir, "strategies")

        self._strategies_dir = strategies_dir
        self._strategies = load_all_strategies(strategies_dir)

        self.chat_panel.set_strategies_dir(strategies_dir)

        for name in self._strategies:
            self.config_panel.add_strategy(name)

        # Pass strategies to live panel
        self.live_panel.set_strategies(self._strategies)

    def reload_strategy(self, name: str):
        candidates = [
            name.lower().replace(" ", "_").replace("-", "_") + ".py",
            name.lstrip("\u26a1").strip().lower().replace(" ", "_").replace("-", "_") + ".py",
        ]
        for filename in candidates:
            filepath = os.path.join(self._strategies_dir, filename)
            if os.path.exists(filepath):
                try:
                    strats = load_strategy_from_file(filepath)
                    for func_name, func in strats.items():
                        display = func_name.replace("strategy_", "").replace("_", " ").title().replace(" ", "_")
                        self._strategies[display] = func
                        self._strategies[name] = func
                    self.live_panel.set_strategies(self._strategies)
                    return True
                except Exception as e:
                    ToastNotification(self, f"Reload error: {e}", "error")
                    return False
        self._strategies = load_all_strategies(self._strategies_dir)
        self.live_panel.set_strategies(self._strategies)
        return True

    # ══════════════════════════════════════════════════════
    # Settings
    # ══════════════════════════════════════════════════════

    def _restore_settings(self):
        settings = load_settings()
        self.config_panel.set_config(settings)
        if settings.get("model"):
            self.chat_panel.model_combo.setCurrentText(settings["model"])
        if settings.get("window_geometry"):
            try:
                from PyQt5.QtCore import QByteArray
                geom = QByteArray.fromHex(settings["window_geometry"].encode())
                self.restoreGeometry(geom)
            except Exception:
                pass
        if settings.get("panel_sizes"):
            try:
                self.splitter.setSizes(settings["panel_sizes"])
            except Exception:
                pass
        if settings.get("theme") == "light":
            self._is_dark_theme = False
            apply_theme(QApplication.instance(), False)
            self.theme_btn.setText("Dark")

    def _save_current_settings(self):
        config = self.config_panel.get_config()
        settings = load_settings()
        settings["last_symbol"] = config["symbol"]
        settings["last_interval"] = config["interval"]
        settings["last_lookback"] = config["lookback"]
        settings["last_cash"] = config["cash"]
        settings["last_commission"] = config["commission"]
        settings["model"] = self.chat_panel.model_combo.currentText()
        settings["window_geometry"] = bytes(self.saveGeometry().toHex()).decode()
        settings["panel_sizes"] = self.splitter.sizes()
        settings["theme"] = "dark" if self._is_dark_theme else "light"
        save_settings(settings)

    # ══════════════════════════════════════════════════════
    # Run — dispatches to single or multi mode
    # ══════════════════════════════════════════════════════

    def _on_run(self):
        config = self.config_panel.get_config()
        self._force_refetch = getattr(self, "_force_refetch", False)

        checked = self.config_panel.get_checked_strategies()
        if not checked:
            ToastNotification(self, "Please check at least one strategy", "error")
            return

        if "symbols" in config and len(config["symbols"]) > 0:
            self._run_multi(config, checked)
        else:
            self._run_single(config, checked)

    def _on_force_refetch(self):
        self._force_refetch = True
        self._on_run()

    # ── Single Symbol Run ────────────────────────────────

    def _run_single(self, config, checked):
        if not config.get("symbol"):
            ToastNotification(self, "Please enter a symbol", "error")
            return

        self.config_panel.set_running(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f"Fetching {config['symbol']} {config['interval']}...")

        self._run_queue = list(checked)
        self._current_config = config

        force = getattr(self, "_force_refetch", False)
        self._force_refetch = False

        self._fetch_worker = CachedFetchWorker(
            BinanceFetcher, config["symbol"], config["interval"],
            config["lookback"], force_refetch=force
        )
        self._fetch_worker.progress.connect(self._on_fetch_progress)
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def _on_fetch_progress(self, pct, msg):
        self.status_label.setText(msg)

    def _on_fetch_done(self, df):
        self._df = df
        self.status_label.setText(
            f"Fetched {len(df)} candles | "
            f"{df.index[0].strftime('%Y-%m-%d')} \u2192 {df.index[-1].strftime('%Y-%m-%d')}"
        )
        self.progress_bar.setRange(0, 100)
        ToastNotification(self, f"Fetched {len(df)} candles", "success")

        # Compute regimes
        try:
            from core.regime import RegimeDetector
            self._regimes = RegimeDetector.classify(df)
            self.chart_panel.set_regimes(self._regimes)
        except Exception:
            self._regimes = None

        # Update cache status
        self.config_panel._update_cache_status()

        self._run_next_strategy()

    def _on_fetch_error(self, error_msg):
        self.status_label.setText(f"Fetch error: {error_msg}")
        self.progress_bar.setVisible(False)
        self.config_panel.set_running(False)
        ToastNotification(self, f"Fetch error: {error_msg}", "error")

    def _run_next_strategy(self):
        if not self._run_queue:
            self.config_panel.set_running(False)
            self.progress_bar.setVisible(False)
            self.status_label.setText("All backtests complete")
            self._update_chat_context()
            self._update_dna_panel()
            return

        name = self._run_queue.pop(0)
        fn = self._strategies.get(name)
        if not fn:
            self._run_next_strategy()
            return

        # Cache fn by name so _on_backtest_done can reliably retrieve it
        # even if self._strategies is mutated mid-run (e.g. chat imports a new strategy)
        self._pending_strategy_fns[name] = fn

        config = self._current_config
        self.status_label.setText(f"Running {name}...")
        self.progress_bar.setRange(0, 0)

        worker = BacktestWorker(
            df=self._df, strategy_fn=fn, strategy_name=name,
            cash=config["cash"], commission=config["commission"],
            interval=config["interval"],
        )
        worker.progress.connect(lambda msg: self.status_label.setText(msg))
        worker.finished.connect(self._on_backtest_done)
        worker.error.connect(self._on_backtest_error)
        worker.start()
        self._backtest_workers.append(worker)

    def _on_backtest_done(self, stats, trades, backtester, strategy_name):
        self._all_results[strategy_name] = stats
        self._all_bt_results[strategy_name] = (backtester, stats, trades)
        self._last_stats = stats
        self._last_strategy_name = strategy_name

        # Use the fn we stored at dispatch time — more reliable than re-looking up
        # by name since strategies dict may have changed (dynamic imports, chat, etc.)
        strategy_fn = self._pending_strategy_fns.pop(
            strategy_name, self._strategies.get(strategy_name)
        )
        self._last_strategy_fn = strategy_fn
        self._last_trades = trades

        self.chat_panel.set_current_strategy_name(strategy_name)

        self.config_panel.update_strategy_result(
            strategy_name, stats["Total Return %"], stats["Total Trades"]
        )
        self.chart_panel.add_result(strategy_name, backtester, stats, trades)
        self.stats_panel.update_stats(stats)

        # Update sub-panels
        config = self._current_config
        self.trade_journal.update_with_results(trades, config.get("symbol", "BTCUSDT"))
        self.seasonality_panel.update_with_results(trades)

        # Always pass data to robustness panel; strategy_fn may be None only if
        # it was never registered, in which case warn instead of silently skipping
        if self._df is not None and strategy_fn:
            self.robustness_panel.update_with_results(
                self._df, strategy_fn, trades,
                config["cash"], config["commission"], config["interval"]
            )
        elif self._df is not None and not strategy_fn:
            self.robustness_panel.status_label.setText(
                "⚠ Could not locate strategy function — robustness unavailable"
            )

        # Regime stats
        regime_stats = None
        if self._regimes is not None:
            try:
                from core.regime import RegimeDetector
                regime_stats = RegimeDetector.get_regime_stats(trades, self._regimes)
            except Exception:
                pass

        total_ret = stats["Total Return %"]
        trade_count = stats["Total Trades"]
        self.status_label.setText(
            f"{strategy_name}: {'+' if total_ret >= 0 else ''}{total_ret}% | "
            f"{trade_count} trades"
        )
        ToastNotification(self,
            f"{strategy_name}: {'+' if total_ret >= 0 else ''}{total_ret}%",
            "success" if total_ret >= 0 else "error"
        )
        self._run_next_strategy()

    def _on_backtest_error(self, error_msg):
        self.status_label.setText(f"Backtest error: {error_msg}")
        ToastNotification(self, f"Error: {error_msg}", "error")
        self._run_next_strategy()

    # ── Multi-Symbol Run ─────────────────────────────────

    def _run_multi(self, config, checked_strategies):
        symbols = config["symbols"]
        if not symbols:
            ToastNotification(self, "Please check at least one symbol", "error")
            return

        self.config_panel.set_running(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self._current_config = config
        self._multi_dfs = {}
        self._all_results = {}

        self._multi_run_queue = [
            (sym, strat) for sym in symbols for strat in checked_strategies
        ]
        self._multi_total = len(self._multi_run_queue)
        self._multi_done = 0

        self.status_label.setText(f"Fetching {len(symbols)} symbols...")
        self._multi_fetch_worker = MultiFetchWorker(
            BinanceFetcher, symbols, config["interval"], config["lookback"]
        )
        self._multi_fetch_worker.progress.connect(self._on_multi_fetch_progress)
        self._multi_fetch_worker.symbol_done.connect(self._on_multi_symbol_fetched)
        self._multi_fetch_worker.all_finished.connect(self._on_multi_fetch_complete)
        self._multi_fetch_worker.symbol_error.connect(self._on_multi_symbol_error)
        self._multi_fetch_worker.start()

    def _on_multi_fetch_progress(self, idx, total, msg):
        self.status_label.setText(msg)

    def _on_multi_symbol_fetched(self, symbol, df):
        self._multi_dfs[symbol] = df

    def _on_multi_symbol_error(self, symbol, error_msg):
        ToastNotification(self, f"Fetch error {symbol}: {error_msg}", "error")

    def _on_multi_fetch_complete(self, all_dfs):
        self._multi_dfs = all_dfs
        if not self._multi_dfs:
            self.config_panel.set_running(False)
            self.progress_bar.setVisible(False)
            self.status_label.setText("No data fetched")
            return
        total_candles = sum(len(df) for df in self._multi_dfs.values())
        ToastNotification(self, f"Fetched {total_candles} candles across {len(self._multi_dfs)} symbols", "success")
        self._run_next_multi()

    def _run_next_multi(self):
        if not self._multi_run_queue:
            self.config_panel.set_running(False)
            self.progress_bar.setVisible(False)
            self.status_label.setText(f"Multi-symbol run complete \u2014 {self._multi_done} backtests")
            self._update_chat_context()
            self._update_dna_panel()
            if len(self._all_results) > 1:
                self._show_comparison_dialog()
            return

        symbol, strat_name = self._multi_run_queue.pop(0)
        fn = self._strategies.get(strat_name)
        df = self._multi_dfs.get(symbol)

        if not fn or df is None:
            self._run_next_multi()
            return

        config = self._current_config
        result_key = f"{strat_name} \u2014 {symbol}"
        self._multi_done += 1
        self.status_label.setText(
            f"Running {symbol} ({self._multi_done}/{self._multi_total})... {strat_name}"
        )

        worker = BacktestWorker(
            df=df, strategy_fn=fn, strategy_name=result_key,
            cash=config["cash"], commission=config["commission"],
            interval=config["interval"],
        )
        worker.progress.connect(lambda msg: self.status_label.setText(msg))
        worker.finished.connect(self._on_multi_backtest_done)
        worker.error.connect(self._on_multi_backtest_error)
        worker.start()
        self._backtest_workers.append(worker)

    def _on_multi_backtest_done(self, stats, trades, backtester, result_key):
        self._all_results[result_key] = stats
        self._all_bt_results[result_key] = (backtester, stats, trades)
        self._last_stats = stats
        self._last_strategy_name = result_key
        self._last_trades = trades

        self.chart_panel.add_result(result_key, backtester, stats, trades)
        self.stats_panel.update_stats(stats)

        total_ret = stats["Total Return %"]
        self.status_label.setText(f"{result_key}: {'+' if total_ret >= 0 else ''}{total_ret}%")
        self._run_next_multi()

    def _on_multi_backtest_error(self, error_msg):
        ToastNotification(self, f"Error: {error_msg}", "error")
        self._run_next_multi()

    # ══════════════════════════════════════════════════════
    # DNA Panel Update
    # ══════════════════════════════════════════════════════

    def _update_dna_panel(self):
        if len(self._all_bt_results) >= 2:
            self.dna_panel.update_with_results(self._all_bt_results)

    # ══════════════════════════════════════════════════════
    # Compare All
    # ══════════════════════════════════════════════════════

    def _on_compare_all(self):
        for idx in range(self.config_panel.strategy_list.count()):
            self.config_panel.strategy_list.item(idx).setCheckState(Qt.Checked)
        self._on_run()

    def _show_comparison_dialog(self):
        if not self._all_results:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Strategy Comparison")
        dialog.setMinimumSize(800, 450)
        dialog.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRI};")

        layout = QVBoxLayout(dialog)

        table = QTableWidget()
        headers = ["Strategy", "Return %", "Sharpe", "Win Rate %", "Max DD %",
                    "Trades", "Profit Factor"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(self._all_results))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSortingEnabled(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {BG_DEEP};
                color: {TEXT_PRI};
                gridline-color: {BORDER};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background-color: {BG_PANEL};
                color: {TEXT_SEC};
                border: 1px solid {BORDER};
                padding: 6px;
                font-weight: bold;
                font-size: 11px;
            }}
            QTableWidget::item:selected {{
                background-color: {BLUE};
            }}
        """)

        best_key = max(self._all_results, key=lambda k: self._all_results[k].get("Sharpe Ratio", 0))

        for row, (name, stats) in enumerate(self._all_results.items()):
            display = f"* {name}" if name == best_key else name
            table.setItem(row, 0, QTableWidgetItem(display))

            ret = stats.get("Total Return %", 0)
            ret_item = QTableWidgetItem(f"{ret:+.2f}%")
            ret_item.setForeground(QColor(GREEN if ret >= 0 else RED))
            table.setItem(row, 1, ret_item)

            table.setItem(row, 2, QTableWidgetItem(f"{stats.get('Sharpe Ratio', 0):.3f}"))
            table.setItem(row, 3, QTableWidgetItem(f"{stats.get('Win Rate %', 0):.1f}%"))
            table.setItem(row, 4, QTableWidgetItem(f"{stats.get('Max Drawdown %', 0):.2f}%"))
            table.setItem(row, 5, QTableWidgetItem(str(stats.get("Total Trades", 0))))
            table.setItem(row, 6, QTableWidgetItem(f"{stats.get('Profit Factor', 0):.3f}"))

        layout.addWidget(table)
        dialog.exec_()

    # ══════════════════════════════════════════════════════
    # Jump to Trade
    # ══════════════════════════════════════════════════════

    def _on_jump_to_trade(self, trade):
        self.center_tabs.setCurrentIndex(0)  # Switch to chart tab
        self.chart_panel.zoom_to_trade(trade)

    # ══════════════════════════════════════════════════════
    # Strategy Import / Replace
    # ══════════════════════════════════════════════════════

    def _on_import_strategy(self, filepath):
        try:
            strats = load_strategy_from_file(filepath)
            dest = os.path.join(self._strategies_dir, os.path.basename(filepath))
            if filepath != dest:
                shutil.copy2(filepath, dest)
            for func_name, func in strats.items():
                display_name = func_name.replace("strategy_", "").replace("_", " ").title().replace(" ", "_")
                self._strategies[display_name] = func
                self.config_panel.add_strategy(display_name)
            self.live_panel.set_strategies(self._strategies)
            ToastNotification(self, f"Imported {len(strats)} strategy(s)", "success")
        except Exception as e:
            ToastNotification(self, f"Import error: {str(e)}", "error")

    def _import_strategy_code(self, code: str):
        try:
            filepath = save_strategy_code(code, self._strategies_dir)
            strats = load_strategy_from_file(filepath)
            for func_name, func in strats.items():
                display_name = f"\u26a1{func_name.replace('strategy_', '').replace('_', ' ').title().replace(' ', '_')}"
                self._strategies[display_name] = func
                self.config_panel.add_strategy(display_name)
            self.live_panel.set_strategies(self._strategies)
            ToastNotification(self, "Strategy imported from Claude!", "success")
        except Exception as e:
            ToastNotification(self, f"Import error: {str(e)}", "error")

    def _replace_strategy_code(self, strategy_name: str, code: str):
        try:
            clean = strategy_name.lstrip("\u26a1").strip()
            filename = clean.lower().replace(" ", "_").replace("-", "_") + ".py"
            filepath = os.path.join(self._strategies_dir, filename)

            header = "import pandas as pd\nimport numpy as np\nfrom core.indicators import Indicators\n\n"
            if "import pandas" not in code:
                code = header + code

            with open(filepath, "w") as f:
                f.write(code)

            self.reload_strategy(strategy_name)
            ToastNotification(self, "Strategy fixed and reloaded!", "success")
        except Exception as e:
            ToastNotification(self, f"Replace error: {str(e)}", "error")

    # ══════════════════════════════════════════════════════
    # Auto-Optimizer
    # ══════════════════════════════════════════════════════

    def _on_auto_optimize(self):
        api_key = self.chat_panel.get_api_key()
        if not api_key:
            ToastNotification(self, "Set API key first", "error")
            return
        if not self._last_stats or not self._last_strategy_name:
            ToastNotification(self, "Run a backtest first", "error")
            return
        if self._df is None:
            ToastNotification(self, "No data loaded", "error")
            return

        strategy_code = self.chat_panel._get_active_strategy_code()
        if not strategy_code:
            ToastNotification(self, "Could not read strategy code", "error")
            return

        config = self.config_panel.get_config()

        from core.optimizer import AIOptimizer, OptimizerThread

        optimizer = AIOptimizer(
            api_key=api_key,
            model=self.chat_panel.model_combo.currentText(),
            strategy_name=self._last_strategy_name,
            strategy_code=strategy_code,
            backtest_stats=self._last_stats,
            trades=self._last_trades,
            df=self._df,
            config=config,
        )

        optimizer.step_started.connect(self._on_opt_step)
        optimizer.log.connect(self._on_opt_log)
        optimizer.variant_result.connect(self._on_opt_variant_result)
        optimizer.optimization_complete.connect(self._on_opt_complete)
        optimizer.token_usage.connect(self._on_opt_tokens)
        optimizer.error.connect(self._on_opt_error)

        self._optimizer = optimizer
        self._optimizer_thread = OptimizerThread(optimizer, max_iterations=5)
        self._optimizer_thread.start()

        self.chat_panel.optimize_btn.setEnabled(False)
        self.chat_panel.optimize_btn.setText("Optimizing...")
        self.chat_panel.add_optimizer_message("Starting AI optimization loop...")
        ToastNotification(self, "AI optimization started", "info")

    def _on_opt_step(self, step, desc):
        self.status_label.setText(f"Optimizer: Step {step} \u2014 {desc}")

    def _on_opt_log(self, msg):
        self.chat_panel.add_optimizer_message(msg)

    def _on_opt_variant_result(self, name, stats):
        ret = stats.get("Total Return %", 0)
        sharpe = stats.get("Sharpe Ratio", 0)
        self.chat_panel.add_optimizer_message(
            f"Variant '{name}': Return={ret:+.1f}% Sharpe={sharpe:.2f}"
        )

    def _on_opt_complete(self, best, summary):
        self.chat_panel.optimize_btn.setEnabled(True)
        self.chat_panel.optimize_btn.setText("Auto-Optimize")
        self.chat_panel.add_optimizer_message(f"\nBest variant: {best}\n\n{summary}")
        self.status_label.setText(f"Optimization complete \u2014 best: {best}")

        # Add adopt button
        if hasattr(self, '_optimizer') and self._optimizer.get_best_variant_code():
            adopt_btn = QPushButton(f"Adopt Best Variant as New Strategy")
            adopt_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {GREEN}; color: #000;
                    border: none; padding: 8px 16px;
                    font-weight: bold; font-size: 12px;
                }}
                QPushButton:hover {{ background-color: #00cc6a; }}
            """)
            adopt_btn.clicked.connect(lambda: self._adopt_variant(self._optimizer.get_best_variant_code()))
            idx = self.chat_panel.chat_layout.count() - 1
            self.chat_panel.chat_layout.insertWidget(idx, adopt_btn)

    def _on_opt_tokens(self, inp, out, cost):
        self.chat_panel.token_label.setText(
            f"Tokens: {inp + out:,} | Cost: ${cost:.4f}"
        )

    def _on_opt_error(self, msg):
        self.chat_panel.optimize_btn.setEnabled(True)
        self.chat_panel.optimize_btn.setText("Auto-Optimize")
        self.chat_panel.add_optimizer_message(f"Optimizer error: {msg}")
        ToastNotification(self, f"Optimizer error: {msg}", "error")

    def _adopt_variant(self, code):
        if self._last_strategy_name:
            self._replace_strategy_code(self._last_strategy_name, code)
            ToastNotification(self, "Best variant adopted as new strategy!", "success")

    # ══════════════════════════════════════════════════════
    # Export Report
    # ══════════════════════════════════════════════════════

    def _export_report(self):
        if not self._last_stats:
            ToastNotification(self, "No results to export", "info")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export HTML Report", "backtest_report.html", "HTML Files (*.html)"
        )
        if not filepath:
            return

        config = self.config_panel.get_config()
        regime_stats = None
        if self._regimes is not None:
            try:
                from core.regime import RegimeDetector
                regime_stats = RegimeDetector.get_regime_stats(self._last_trades, self._regimes)
            except Exception:
                pass

        export_html_report(
            strategy_name=self._last_strategy_name or "Unknown",
            symbol=config.get("symbol", "BTCUSDT"),
            interval=config.get("interval", "1h"),
            stats=self._last_stats,
            trades=self._last_trades,
            equity_fig=self.chart_panel.figure,
            regime_stats=regime_stats,
            filepath=filepath,
        )
        ToastNotification(self, f"Report saved to {filepath}", "success")

    # ══════════════════════════════════════════════════════
    # Save / Chat Context
    # ══════════════════════════════════════════════════════

    def _on_save(self):
        if not self._last_stats:
            ToastNotification(self, "No results to save", "info")
            return
        config = self.config_panel.get_config()
        filepath = export_results(
            self._last_stats,
            self._last_strategy_name or "unknown",
            config["symbol"]
        )
        ToastNotification(self, f"Results saved to {filepath}", "success")

    def _update_chat_context(self):
        config = self.config_panel.get_config()
        ctx = []

        if self.config_panel.is_multi_mode and "symbols" in config:
            ctx.append(f"Symbols: {', '.join(config['symbols'])}  Interval: {config['interval']}  Lookback: {config['lookback']}")
        else:
            ctx.append(f"Symbol: {config['symbol']}  Interval: {config['interval']}  Lookback: {config['lookback']}")
        ctx.append(f"Starting Cash: ${config['cash']:,.0f}  Commission: {config['commission']*100:.2f}%")

        if self._df is not None:
            ctx.append(f"Data: {len(self._df)} candles from {self._df.index[0]} to {self._df.index[-1]}")

        if self._last_stats and self._last_strategy_name:
            ctx.append(f"\nLAST BACKTEST RESULTS ({self._last_strategy_name}):")
            for k, v in self._last_stats.items():
                ctx.append(f"  {k}: {v}")

        if len(self._all_results) > 1:
            ctx.append(f"\nALL STRATEGY COMPARISON:")
            for name, stats in self._all_results.items():
                ctx.append(
                    f"  {name}: Return={stats.get('Total Return %', 0)}%  "
                    f"Sharpe={stats.get('Sharpe Ratio', 0)}  "
                    f"WinRate={stats.get('Win Rate %', 0)}%"
                )

        if self._last_trades:
            wins = [t for t in self._last_trades if t.pnl > 0]
            losses = [t for t in self._last_trades if t.pnl <= 0]
            ctx.append(f"\nTRADE BREAKDOWN: {len(wins)} wins / {len(losses)} losses")
            sl_exits = len([t for t in self._last_trades if t.exit_reason == 'SL'])
            tp_exits = len([t for t in self._last_trades if t.exit_reason == 'TP'])
            ctx.append(
                f"Exit reasons: {sl_exits} SL hits / {tp_exits} TP hits / "
                f"{len(self._last_trades) - sl_exits - tp_exits} signals"
            )

        # Regime stats in context
        if self._regimes is not None and self._last_trades:
            try:
                from core.regime import RegimeDetector
                regime_stats = RegimeDetector.get_regime_stats(self._last_trades, self._regimes)
                ctx.append("\nREGIME ANALYSIS:")
                for name, data in regime_stats.items():
                    if data["trades"] > 0:
                        ctx.append(
                            f"  {name}: {data['trades']} trades, "
                            f"Win Rate={data['win_rate']}%, "
                            f"Avg PnL=${data['avg_pnl']:.2f}"
                        )
            except Exception:
                pass

        self.chat_panel.set_backtest_context("\n".join(ctx))

    def closeEvent(self, event):
        self._save_current_settings()
        self.chat_panel.save_model_setting()
        # Stop live trading if running
        self.live_panel._stop_trading()
        event.accept()