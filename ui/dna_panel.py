"""
m3emz Backtester — Strategy DNA & Portfolio Combiner
Correlation matrix, portfolio combiner, and anti-correlation optimizer.
"""

import numpy as np
import pandas as pd
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSlider, QFrame, QSizePolicy, QScrollArea
)
from PyQt5.QtCore import Qt

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.colors as mcolors

from utils.theme import (
    BG_DEEP, BG_PANEL, BG_HOVER, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, ORANGE, PURPLE, FONT_MONO
)


class StrategyWeightRow(QFrame):
    """Single strategy row with checkbox and weight slider."""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: 1px solid {BORDER};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.cb = QCheckBox(name)
        self.cb.setChecked(True)
        self.cb.setStyleSheet(f"color: {TEXT_PRI}; font-size: 11px;")
        self.cb.stateChanged.connect(self._toggle)
        layout.addWidget(self.cb, 1)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(25)
        self.slider.setFixedWidth(120)
        self.slider.valueChanged.connect(self._on_value)
        layout.addWidget(self.slider)

        self.pct_label = QLabel("25%")
        self.pct_label.setFixedWidth(40)
        self.pct_label.setStyleSheet(f"color: {TEXT_PRI}; font-family: {FONT_MONO}; font-size: 11px; border: none;")
        layout.addWidget(self.pct_label)

    def _toggle(self, state):
        self.slider.setEnabled(state == Qt.Checked)

    def _on_value(self, val):
        self.pct_label.setText(f"{val}%")

    @property
    def weight(self):
        if not self.cb.isChecked():
            return 0
        return self.slider.value() / 100.0

    def set_weight(self, pct):
        self.slider.setValue(int(pct * 100))


class DNAPanel(QWidget):
    """Strategy correlation matrix and portfolio combiner."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        self._results = {}  # strategy_name -> backtester
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QLabel("Strategy DNA & Portfolio")
        header.setStyleSheet(f"color: {TEXT_PRI}; font-size: 14px; font-weight: bold; border: none;")
        layout.addWidget(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BG_DEEP}; border: none; }}")

        content = QWidget()
        content.setStyleSheet(f"background: {BG_DEEP};")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)

        # Correlation Heatmap
        self.corr_fig = Figure(figsize=(6, 5), facecolor=BG_DEEP, dpi=100)
        self.corr_canvas = FigureCanvas(self.corr_fig)
        self.corr_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_layout.addWidget(self.corr_canvas)

        # Insight text
        self.insight_label = QLabel("")
        self.insight_label.setWordWrap(True)
        self.insight_label.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 11px; border: 1px solid {BORDER}; "
            f"padding: 8px; background-color: {BG_PANEL};"
        )
        self.content_layout.addWidget(self.insight_label)

        # Portfolio Combiner
        combiner_header = QLabel("Portfolio Combiner")
        combiner_header.setStyleSheet(f"color: {TEXT_PRI}; font-size: 12px; font-weight: bold; border: none;")
        self.content_layout.addWidget(combiner_header)

        self.weight_rows_container = QVBoxLayout()
        self.weight_rows_container.setSpacing(4)
        self.content_layout.addLayout(self.weight_rows_container)

        # Buttons
        btn_row = QHBoxLayout()
        self.run_portfolio_btn = QPushButton("Run Portfolio Backtest")
        self.run_portfolio_btn.setObjectName("primary")
        self.run_portfolio_btn.clicked.connect(self._run_portfolio)
        btn_row.addWidget(self.run_portfolio_btn)

        self.optimize_btn = QPushButton("Find Optimal Mix")
        self.optimize_btn.clicked.connect(self._find_optimal)
        btn_row.addWidget(self.optimize_btn)

        btn_row.addStretch()
        self.content_layout.addLayout(btn_row)

        # Portfolio result chart
        self.portfolio_fig = Figure(figsize=(8, 3.5), facecolor=BG_DEEP, dpi=100)
        self.portfolio_canvas = FigureCanvas(self.portfolio_fig)
        self.portfolio_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_layout.addWidget(self.portfolio_canvas)

        self.portfolio_label = QLabel("")
        self.portfolio_label.setWordWrap(True)
        self.portfolio_label.setStyleSheet(f"color: {TEXT_PRI}; font-size: 11px; border: none;")
        self.content_layout.addWidget(self.portfolio_label)

        self.content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Placeholder
        self._draw_placeholder()

    def _draw_placeholder(self):
        self.corr_fig.clear()
        ax = self.corr_fig.add_subplot(111)
        ax.set_facecolor(BG_PANEL)
        ax.text(0.5, 0.5, "Run 2+ strategies to see correlation matrix",
                ha="center", va="center", color=TEXT_SEC, fontsize=12,
                transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        self.corr_canvas.draw()

    def update_with_results(self, all_results: dict):
        """
        all_results: {strategy_name: (backtester, stats, trades)}
        Called after each backtest completes.
        """
        self._results = all_results

        if len(all_results) < 2:
            self._draw_placeholder()
            return

        # Build daily returns DataFrame
        returns_dict = {}
        for name, (bt, stats, trades) in all_results.items():
            eq_df = bt.get_equity_df()
            if eq_df.empty:
                continue
            eq = eq_df["equity"]
            daily = eq.resample("D").last().pct_change().dropna()
            returns_dict[name] = daily

        if len(returns_dict) < 2:
            return

        returns_df = pd.DataFrame(returns_dict).dropna()
        if returns_df.empty or len(returns_df) < 5:
            return

        corr = returns_df.corr()
        self._draw_correlation(corr)
        self._generate_insight(corr)
        self._build_weight_rows(list(all_results.keys()))

    def _draw_correlation(self, corr):
        self.corr_fig.clear()
        ax = self.corr_fig.add_subplot(111)
        ax.set_facecolor(BG_PANEL)

        n = len(corr)
        names = list(corr.columns)

        cmap = mcolors.LinearSegmentedColormap.from_list(
            "corr", [(0.1, 0.3, 0.9), (1, 1, 1), (0.9, 0.1, 0.1)]
        )
        im = ax.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1, aspect="auto")

        ax.set_xticks(range(n))
        ax.set_xticklabels(names, fontsize=8, rotation=45, ha="right")
        ax.set_yticks(range(n))
        ax.set_yticklabels(names, fontsize=8)
        ax.set_title("Strategy Correlation Matrix", color=TEXT_PRI, fontsize=11, fontweight="bold")
        ax.tick_params(colors=TEXT_SEC, labelsize=7)

        # Annotate cells
        for i in range(n):
            for j in range(n):
                val = corr.values[i, j]
                color = "black" if abs(val) < 0.5 else "white"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=9, color=color, fontweight="bold")

        self.corr_fig.colorbar(im, ax=ax, shrink=0.8)
        for sp in ax.spines.values():
            sp.set_color(BORDER)
        self.corr_fig.tight_layout()
        self.corr_canvas.draw()

    def _generate_insight(self, corr):
        names = list(corr.columns)
        n = len(names)
        if n < 2:
            return

        # Find most correlated pair
        max_corr = -2
        max_pair = ("", "")
        for i in range(n):
            for j in range(i + 1, n):
                if corr.values[i, j] > max_corr:
                    max_corr = corr.values[i, j]
                    max_pair = (names[i], names[j])

        # Find most independent strategy
        avg_corrs = {}
        for name in names:
            others = [abs(corr.loc[name, other]) for other in names if other != name]
            avg_corrs[name] = np.mean(others)
        best_diversifier = min(avg_corrs, key=avg_corrs.get)

        text = (
            f"{max_pair[0]} and {max_pair[1]} are {max_corr*100:.0f}% correlated "
            f"— running both provides little diversification benefit. "
            f"{best_diversifier} is the most independent strategy "
            f"(avg correlation {avg_corrs[best_diversifier]:.2f}) and is your best diversifier."
        )
        self.insight_label.setText(text)

    def _build_weight_rows(self, names):
        # Clear existing
        while self.weight_rows_container.count() > 0:
            item = self.weight_rows_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._weight_rows = {}
        equal_weight = int(100 / max(len(names), 1))
        for name in names:
            row = StrategyWeightRow(name)
            row.set_weight(equal_weight / 100)
            self._weight_rows[name] = row
            self.weight_rows_container.addWidget(row)

    def _run_portfolio(self):
        if not self._results or not hasattr(self, "_weight_rows"):
            return

        weights = {}
        for name, row in self._weight_rows.items():
            w = row.weight
            if w > 0:
                weights[name] = w

        if not weights:
            return

        # Normalize weights
        total_w = sum(weights.values())
        weights = {k: v / total_w for k, v in weights.items()}

        # Build combined equity curve
        equity_curves = {}
        for name, (bt, stats, trades) in self._results.items():
            if name not in weights:
                continue
            eq_df = bt.get_equity_df()
            if eq_df.empty:
                continue
            equity_curves[name] = eq_df["equity"]

        if not equity_curves:
            return

        # Align indices
        combined_df = pd.DataFrame(equity_curves).dropna()
        if combined_df.empty:
            return

        # Calculate weighted portfolio
        init_cash = combined_df.iloc[0].mean()
        portfolio = pd.Series(0.0, index=combined_df.index)
        for name, w in weights.items():
            if name in combined_df.columns:
                # Normalize each curve to start at 1, then weight
                normalized = combined_df[name] / combined_df[name].iloc[0]
                portfolio += normalized * w * init_cash

        self._draw_portfolio(combined_df, portfolio, weights)

    def _draw_portfolio(self, curves_df, portfolio, weights):
        self.portfolio_fig.clear()
        ax = self.portfolio_fig.add_subplot(111)
        ax.set_facecolor(BG_PANEL)

        colors = [BLUE, GREEN, ORANGE, PURPLE, RED, TEXT_SEC]

        for idx, name in enumerate(curves_df.columns):
            color = colors[idx % len(colors)]
            ax.plot(curves_df.index, curves_df[name].values,
                    color=color, alpha=0.4, linewidth=0.7, label=name)

        ax.plot(portfolio.index, portfolio.values,
                color="white", linewidth=2.0, label="Portfolio", zorder=10)

        ax.set_ylabel("Equity $", color=TEXT_SEC, fontsize=9)
        ax.set_title("Portfolio vs Individual Strategies", color=TEXT_PRI,
                      fontsize=11, fontweight="bold")
        ax.legend(fontsize=7, facecolor=BG_PANEL, edgecolor=BORDER, labelcolor=TEXT_SEC)
        ax.tick_params(colors=TEXT_SEC, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color(BORDER)
        self.portfolio_fig.tight_layout()
        self.portfolio_canvas.draw()

        # Portfolio stats
        ret = (portfolio.iloc[-1] - portfolio.iloc[0]) / portfolio.iloc[0] * 100
        rets = portfolio.pct_change().dropna()
        sharpe = (rets.mean() / rets.std()) * np.sqrt(252) if rets.std() != 0 else 0

        weight_str = " + ".join(f"{w*100:.0f}% {n}" for n, w in weights.items())
        self.portfolio_label.setText(
            f"Portfolio: {weight_str} | "
            f"Return: {'+' if ret >= 0 else ''}{ret:.1f}% | Sharpe: {sharpe:.2f}"
        )

    def _find_optimal(self):
        """Greedy optimization for minimum correlation, maximum Sharpe."""
        if len(self._results) < 2:
            return

        # Build daily returns
        returns_dict = {}
        for name, (bt, stats, trades) in self._results.items():
            eq_df = bt.get_equity_df()
            if eq_df.empty:
                continue
            eq = eq_df["equity"]
            daily = eq.resample("D").last().pct_change().dropna()
            returns_dict[name] = daily

        returns_df = pd.DataFrame(returns_dict).dropna()
        if returns_df.empty or len(returns_df.columns) < 2:
            return

        names = list(returns_df.columns)
        n = len(names)

        # Try equal-weight combinations of size 2..n, pick best Sharpe
        best_sharpe = -999
        best_weights = {}

        from itertools import combinations
        for size in range(2, n + 1):
            for combo in combinations(range(n), size):
                # Equal weight
                w = 1.0 / size
                port_ret = sum(returns_df.iloc[:, i] * w for i in combo)
                sharpe = (port_ret.mean() / port_ret.std()) * np.sqrt(252) if port_ret.std() != 0 else 0
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_weights = {names[i]: w for i in combo}

        if not best_weights:
            return

        # Set sliders
        for name, row in self._weight_rows.items():
            if name in best_weights:
                row.cb.setChecked(True)
                row.set_weight(best_weights[name])
            else:
                row.cb.setChecked(False)

        # Compute avg correlation
        selected = list(best_weights.keys())
        corr = returns_df[selected].corr()
        avg_corr = 0
        count = 0
        for i in range(len(selected)):
            for j in range(i + 1, len(selected)):
                avg_corr += abs(corr.iloc[i, j])
                count += 1
        avg_corr = avg_corr / count if count > 0 else 0

        weight_str = " + ".join(f"{w*100:.0f}% {n}" for n, w in best_weights.items())
        self.portfolio_label.setText(
            f"Optimal: {weight_str} | Sharpe: {best_sharpe:.2f} | "
            f"Avg correlation: {avg_corr:.2f}"
        )

        # Auto-run portfolio
        self._run_portfolio()
