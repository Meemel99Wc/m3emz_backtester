"""
m3emz Backtester — Robustness Panel (Walk-Forward + Monte Carlo)
"""

import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from utils.theme import (
    BG_DEEP, BG_PANEL, BG_HOVER, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, ORANGE, PURPLE, FONT_MONO
)


class RobustnessWorker(QThread):
    """Run walk-forward and Monte Carlo in background."""
    finished = pyqtSignal(dict, dict)  # wf_results, mc_results
    error = pyqtSignal(str)

    def __init__(self, df, strategy_fn, trades, init_cash, commission, interval):
        super().__init__()
        self.df = df
        self.strategy_fn = strategy_fn
        self.trades = trades
        self.init_cash = init_cash
        self.commission = commission
        self.interval = interval

    def run(self):
        try:
            from core.walk_forward import WalkForwardTester
            from core.monte_carlo import MonteCarloSimulator

            wf = WalkForwardTester(
                self.df, self.strategy_fn,
                n_splits=5, train_pct=0.7,
                cash=self.init_cash, commission=self.commission,
                interval=self.interval,
            )
            wf_results = wf.run()

            mc = MonteCarloSimulator(self.trades, self.init_cash, n_simulations=2000)
            mc_results = mc.run()

            self.finished.emit(wf_results, mc_results)
        except Exception as e:
            self.error.emit(str(e))


class MiniStatCard(QFrame):
    def __init__(self, label, value, color=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER};
                padding: 6px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 9px; font-weight: bold; border: none;")
        layout.addWidget(lbl)

        val_color = color or TEXT_PRI
        val = QLabel(str(value))
        val.setStyleSheet(
            f"color: {val_color}; font-size: 14px; font-weight: bold; "
            f"font-family: {FONT_MONO}; border: none;"
        )
        layout.addWidget(val)


class RobustnessPanel(QWidget):
    """Walk-Forward and Monte Carlo robustness testing panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        self._worker = None
        self._df = None
        self._strategy_fn = None
        self._trades = []
        self._init_cash = 10_000
        self._commission = 0.001
        self._interval = "1h"

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header row
        header_row = QHBoxLayout()
        header = QLabel("Robustness Analysis")
        header.setStyleSheet(f"color: {TEXT_PRI}; font-size: 14px; font-weight: bold; border: none;")
        header_row.addWidget(header)
        header_row.addStretch()

        self.run_btn = QPushButton("Run Robustness Tests")
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self._run_tests)
        header_row.addWidget(self.run_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; border: none;")
        header_row.addWidget(self.status_label)

        layout.addLayout(header_row)

        # Scroll area for results
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BG_DEEP}; border: none; }}")

        self.results_widget = QWidget()
        self.results_widget.setStyleSheet(f"background: {BG_DEEP};")
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(8)
        self.results_layout.addStretch()

        # Placeholder
        placeholder = QLabel("Run a backtest first, then click 'Run Robustness Tests'")
        placeholder.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px; border: none;")
        placeholder.setAlignment(Qt.AlignCenter)
        self.results_layout.insertWidget(0, placeholder)

        scroll.setWidget(self.results_widget)
        layout.addWidget(scroll, 1)

    def update_with_results(self, df, strategy_fn, trades, init_cash, commission, interval):
        """Store data for robustness testing."""
        self._df = df
        self._strategy_fn = strategy_fn
        self._trades = trades
        self._init_cash = init_cash
        self._commission = commission
        self._interval = interval
        # Give the user a clear signal that data is loaded and the button works
        n_trades = len(trades) if trades else 0
        self.status_label.setText(
            f"✓ Ready — {n_trades} trades loaded. Click 'Run Robustness Tests' to analyse."
        )

    def _run_tests(self):
        if self._df is None or self._strategy_fn is None:
            self.status_label.setText("No backtest data available")
            return
        if not self._trades:
            self.status_label.setText("No trades to analyse")
            return

        self.run_btn.setEnabled(False)
        self.status_label.setText("Running robustness tests...")

        self._worker = RobustnessWorker(
            self._df, self._strategy_fn, self._trades,
            self._init_cash, self._commission, self._interval,
        )
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_error(self, msg):
        self.run_btn.setEnabled(True)
        self.status_label.setText(f"Error: {msg}")

    def _on_finished(self, wf_results, mc_results):
        self.run_btn.setEnabled(True)
        self.status_label.setText("Complete")

        # Clear old results
        while self.results_layout.count() > 0:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # ── Stats Cards Row ──
        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)

        eff = wf_results.get("efficiency_ratio", 0)
        eff_color = GREEN if eff > 0.5 else ORANGE if eff > 0.3 else RED
        cards_row.addWidget(MiniStatCard("Efficiency Ratio", f"{eff:.2f}", eff_color))

        n_folds = len(wf_results.get("folds", []))
        consistent = wf_results.get("consistent_folds", 0)
        cards_row.addWidget(MiniStatCard("Profitable Folds", f"{consistent}/{n_folds}",
                                         GREEN if consistent > n_folds / 2 else RED))

        prob = mc_results.get("probability_of_profit", 0) * 100
        prob_color = GREEN if prob > 60 else ORANGE if prob > 40 else RED
        cards_row.addWidget(MiniStatCard("Prob. of Profit", f"{prob:.0f}%", prob_color))

        var = mc_results.get("var_95", 0)
        cards_row.addWidget(MiniStatCard("VaR (95%)", f"${var:,.0f}", RED))

        verdict_wf = wf_results.get("verdict", "?")
        verdict_mc = mc_results.get("verdict", "?")
        v_color = GREEN if "Robust" in verdict_wf else ORANGE if "Marginal" in verdict_wf else RED
        cards_row.addWidget(MiniStatCard("WF Verdict", verdict_wf, v_color))
        v_color2 = GREEN if "Robust" in verdict_mc else ORANGE if "Lucky" in verdict_mc else RED
        cards_row.addWidget(MiniStatCard("MC Verdict", verdict_mc, v_color2))

        cards_container = QWidget()
        cards_container.setLayout(cards_row)
        self.results_layout.addWidget(cards_container)

        # ── Charts ──
        charts_row = QHBoxLayout()
        charts_row.setSpacing(6)

        # Walk-Forward Bar Chart
        wf_fig = Figure(figsize=(6, 3.5), facecolor=BG_DEEP, dpi=100)
        wf_ax = wf_fig.add_subplot(111)
        self._draw_wf_chart(wf_ax, wf_results)
        wf_canvas = FigureCanvas(wf_fig)
        wf_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        charts_row.addWidget(wf_canvas, 1)

        # Monte Carlo Fan Chart
        mc_fig = Figure(figsize=(6, 3.5), facecolor=BG_DEEP, dpi=100)
        mc_ax = mc_fig.add_subplot(111)
        self._draw_mc_chart(mc_ax, mc_results)
        mc_canvas = FigureCanvas(mc_fig)
        mc_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        charts_row.addWidget(mc_canvas, 1)

        charts_container = QWidget()
        charts_container.setLayout(charts_row)
        self.results_layout.addWidget(charts_container)

        self.results_layout.addStretch()

    def _draw_wf_chart(self, ax, wf):
        ax.set_facecolor(BG_PANEL)
        folds = wf.get("folds", [])
        if not folds:
            ax.text(0.5, 0.5, "No folds", ha="center", va="center",
                    color=TEXT_SEC, transform=ax.transAxes)
            return

        x = list(range(len(folds)))
        in_rets = [f["in_sample_return"] for f in folds]
        out_rets = [f["out_sample_return"] for f in folds]
        width = 0.35

        bars_in = ax.bar([xi - width / 2 for xi in x], in_rets, width,
                         color=BLUE, alpha=0.8, label="In-Sample")
        bars_out = ax.bar([xi + width / 2 for xi in x], out_rets, width,
                          color=[GREEN if r > 0 else RED for r in out_rets],
                          alpha=0.8, label="Out-of-Sample")

        ax.axhline(0, color=TEXT_SEC, linewidth=0.5, linestyle="--")
        ax.set_xticks(x)
        ax.set_xticklabels([f"Fold {f['fold']}" for f in folds], fontsize=8)
        ax.set_ylabel("Return %", color=TEXT_SEC, fontsize=9)
        ax.set_title("Walk-Forward Analysis", color=TEXT_PRI, fontsize=11, fontweight="bold")
        ax.legend(fontsize=8, facecolor=BG_PANEL, edgecolor=BORDER, labelcolor=TEXT_SEC)
        ax.tick_params(colors=TEXT_SEC, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color(BORDER)

    def _draw_mc_chart(self, ax, mc):
        ax.set_facecolor(BG_PANEL)
        curves = mc.get("equity_curves", [])
        if not curves:
            ax.text(0.5, 0.5, "No simulations", ha="center", va="center",
                    color=TEXT_SEC, transform=ax.transAxes)
            return

        n_steps = len(curves[0])
        x = list(range(n_steps))

        # Plot 200 sim curves (thin, grey, transparent)
        for curve in curves[:200]:
            ax.plot(x, curve, color=TEXT_SEC, alpha=0.05, linewidth=0.5)

        # Compute percentile bands
        all_curves = np.array(curves[:200])
        p5 = np.percentile(all_curves, 5, axis=0)
        p95 = np.percentile(all_curves, 95, axis=0)
        median = np.percentile(all_curves, 50, axis=0)

        ax.fill_between(x, p5, p95, alpha=0.15, color=BLUE, label="5th-95th pct")
        ax.plot(x, median, color=ORANGE, linewidth=1.0, alpha=0.8, label="Median")

        # Actual equity curve (first curve = original order, but we shuffled;
        # plot the median as proxy or use initial cash line)
        init_cash = curves[0][0] if curves else 10_000
        ax.axhline(init_cash, color=TEXT_SEC, linewidth=0.5, linestyle="--", alpha=0.5)

        ax.set_ylabel("Equity $", color=TEXT_SEC, fontsize=9)
        ax.set_title("Monte Carlo Simulation (2000 runs)", color=TEXT_PRI, fontsize=11, fontweight="bold")
        ax.legend(fontsize=8, facecolor=BG_PANEL, edgecolor=BORDER, labelcolor=TEXT_SEC)
        ax.tick_params(colors=TEXT_SEC, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color(BORDER)