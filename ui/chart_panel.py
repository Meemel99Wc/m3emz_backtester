"""
m3emz Backtester — Chart Panel (Center)
With regime overlay, drawdown event table, and persistent zoom state.
"""

import numpy as np
import pandas as pd
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox,
    QPushButton, QSizePolicy, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.gridspec as gridspec

from utils.theme import (
    BG_DEEP, BG_PANEL, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, ORANGE, FONT_MONO
)


class ChartPanel(QWidget):
    """Center panel with Matplotlib price chart, equity curve, and drawdown."""

    drawdown_selected = pyqtSignal(object, object)  # start, end dates

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")

        self._results = {}  # strategy_name -> (backtester, stats, trades)
        self._current_strategy = None
        self._regimes = None
        self._zoom_states = {}  # strategy_name -> (xlim, ylim) per axis

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # ── Controls Row ──
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.cb_trades = QCheckBox("Trades")
        self.cb_trades.setChecked(True)
        self.cb_trades.stateChanged.connect(self._redraw)
        controls.addWidget(self.cb_trades)

        self.cb_vwap = QCheckBox("VWAP")
        self.cb_vwap.setChecked(False)
        self.cb_vwap.stateChanged.connect(self._redraw)
        controls.addWidget(self.cb_vwap)

        self.cb_ema = QCheckBox("EMA")
        self.cb_ema.setChecked(False)
        self.cb_ema.stateChanged.connect(self._redraw)
        controls.addWidget(self.cb_ema)

        self.cb_bb = QCheckBox("BB")
        self.cb_bb.setChecked(False)
        self.cb_bb.stateChanged.connect(self._redraw)
        controls.addWidget(self.cb_bb)

        self.cb_regimes = QCheckBox("Regimes")
        self.cb_regimes.setChecked(False)
        self.cb_regimes.stateChanged.connect(self._redraw)
        controls.addWidget(self.cb_regimes)

        controls.addStretch()

        self.strategy_combo = QComboBox()
        self.strategy_combo.setMinimumWidth(200)
        self.strategy_combo.currentTextChanged.connect(self._on_strategy_changed)
        controls.addWidget(self.strategy_combo)

        save_png_btn = QPushButton("Save PNG")
        save_png_btn.clicked.connect(self._save_png)
        controls.addWidget(save_png_btn)

        layout.addLayout(controls)

        # ── Matplotlib Canvas ──
        self.figure = Figure(figsize=(12, 8), facecolor=BG_DEEP, dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet(f"""
            background-color: {BG_PANEL};
            border: 1px solid {BORDER};
            color: {TEXT_PRI};
        """)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)

        # ── Drawdown Events Table (collapsible) ──
        self.dd_table_toggle = QPushButton("Drawdown Events (click to expand)")
        self.dd_table_toggle.setCheckable(True)
        self.dd_table_toggle.setChecked(False)
        self.dd_table_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_PANEL}; color: {TEXT_SEC};
                border: 1px solid {BORDER}; padding: 4px 8px;
                font-size: 10px; text-align: left;
            }}
        """)
        self.dd_table_toggle.toggled.connect(self._toggle_dd_table)
        layout.addWidget(self.dd_table_toggle)

        self.dd_table = QTableWidget()
        self.dd_table.setColumnCount(6)
        self.dd_table.setHorizontalHeaderLabels([
            "Start Date", "Lowest Date", "Recovery Date",
            "Depth %", "Duration", "Recovery Time"
        ])
        self.dd_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.dd_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dd_table.setMaximumHeight(200)
        self.dd_table.setVisible(False)
        self.dd_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {BG_PANEL}; color: {TEXT_PRI};
                gridline-color: {BORDER}; font-size: 10px;
                font-family: {FONT_MONO};
            }}
            QHeaderView::section {{
                background-color: {BG_DEEP}; color: {TEXT_SEC};
                border: 1px solid {BORDER}; padding: 4px; font-size: 9px;
            }}
        """)
        layout.addWidget(self.dd_table)

        # Show placeholder
        self._draw_placeholder()

    def _toggle_dd_table(self, checked):
        self.dd_table.setVisible(checked)
        self.dd_table_toggle.setText(
            "Drawdown Events (click to collapse)" if checked
            else "Drawdown Events (click to expand)"
        )

    def _draw_placeholder(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(BG_DEEP)
        ax.text(0.5, 0.5, "Select strategies and click Run to see results",
                ha="center", va="center", color=TEXT_SEC, fontsize=14,
                transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        self.canvas.draw()

    def set_regimes(self, regimes):
        """Set regime classification series for chart overlay."""
        self._regimes = regimes

    def add_result(self, strategy_name, backtester, stats, trades):
        """Store a backtest result and update the dropdown."""
        self._results[strategy_name] = (backtester, stats, trades)
        if self.strategy_combo.findText(strategy_name) == -1:
            self.strategy_combo.addItem(strategy_name)
        self.strategy_combo.setCurrentText(strategy_name)
        self._current_strategy = strategy_name
        self._redraw()

    def _on_strategy_changed(self, name):
        if name and name in self._results:
            # Save current zoom state before switching
            self._save_zoom_state()
            self._current_strategy = name
            self._redraw()

    def _save_zoom_state(self):
        """Remember current axis limits for the active strategy."""
        if not self._current_strategy:
            return
        try:
            axes = self.figure.get_axes()
            if axes:
                state = []
                for ax in axes:
                    state.append((ax.get_xlim(), ax.get_ylim()))
                self._zoom_states[self._current_strategy] = state
        except Exception:
            pass

    def _restore_zoom_state(self):
        """Restore saved zoom state if available."""
        if not self._current_strategy or self._current_strategy not in self._zoom_states:
            return False
        try:
            state = self._zoom_states[self._current_strategy]
            axes = self.figure.get_axes()
            if len(axes) == len(state):
                for ax, (xlim, ylim) in zip(axes, state):
                    ax.set_xlim(xlim)
                    ax.set_ylim(ylim)
                return True
        except Exception:
            pass
        return False

    def _redraw(self, *_):
        if not self._current_strategy or self._current_strategy not in self._results:
            return

        # Save zoom state before redraw
        self._save_zoom_state()

        bt, stats, trades = self._results[self._current_strategy]
        self._plot(bt, trades, self._current_strategy)

        # Restore zoom if we had saved state
        if self._restore_zoom_state():
            self.canvas.draw_idle()

    def _plot(self, bt, trades, strategy_name):
        self.figure.clear()

        eq_df = bt.get_equity_df()
        price_df = bt.df["Close"]
        df = bt.df

        grey = TEXT_SEC
        panel = BG_PANEL

        gs = gridspec.GridSpec(3, 1, figure=self.figure, height_ratios=[3, 1.2, 0.8],
                               hspace=0.08)

        # ── Price Chart ──
        ax1 = self.figure.add_subplot(gs[0])
        ax1.set_facecolor(panel)

        # Regime shading (background layer)
        if self.cb_regimes.isChecked() and self._regimes is not None:
            from core.regime import RegimeDetector
            for i in range(len(df) - 1):
                idx = df.index[i]
                # Find regime value for this candle
                if idx in self._regimes.index:
                    regime_val = self._regimes.loc[idx]
                elif len(self._regimes) > 0:
                    pos = self._regimes.index.searchsorted(idx, side="right") - 1
                    if 0 <= pos < len(self._regimes):
                        regime_val = self._regimes.iloc[pos]
                    else:
                        continue
                else:
                    continue
                color = RegimeDetector.REGIMES.get(regime_val, ("", "#888", ""))[1]
                ax1.axvspan(df.index[i], df.index[i + 1], alpha=0.06, color=color,
                            linewidth=0)

            # Regime strip at bottom of price panel
            strip_y = ax1.get_ylim()[0] if ax1.get_ylim()[0] != 0 else price_df.min() * 0.998
            for i in range(len(df)):
                idx = df.index[i]
                if idx in self._regimes.index:
                    regime_val = self._regimes.loc[idx]
                elif len(self._regimes) > 0:
                    pos = self._regimes.index.searchsorted(idx, side="right") - 1
                    if 0 <= pos < len(self._regimes):
                        regime_val = self._regimes.iloc[pos]
                    else:
                        continue
                else:
                    continue
                color = RegimeDetector.REGIMES.get(regime_val, ("", "#888", ""))[1]
                ax1.plot(idx, price_df.min() * 0.998, marker="|", color=color,
                         markersize=3, alpha=0.7)

        ax1.plot(price_df.index, price_df.values, color=grey, linewidth=0.8, zorder=1)

        # Overlay indicators
        if self.cb_vwap.isChecked() and "VWAP" in df.columns:
            vwap_vals = df["VWAP"].values
            if not np.all(np.isnan(vwap_vals)):
                ax1.plot(df.index, vwap_vals, color=ORANGE, linewidth=0.7, alpha=0.8, label="VWAP")

        if self.cb_ema.isChecked():
            for col, color, lbl in [("EMA9", BLUE, "EMA9"), ("EMA21", "#e879f9", "EMA21")]:
                if col in df.columns:
                    vals = df[col].values
                    if not np.all(np.isnan(vals)):
                        ax1.plot(df.index, vals, color=color, linewidth=0.6, alpha=0.7, label=lbl)

        if self.cb_bb.isChecked():
            if "BB_Upper" in df.columns and "BB_Lower" in df.columns:
                ax1.plot(df.index, df["BB_Upper"].values, color="#60a5fa", linewidth=0.5, alpha=0.5)
                ax1.plot(df.index, df["BB_Lower"].values, color="#60a5fa", linewidth=0.5, alpha=0.5)
                ax1.fill_between(df.index, df["BB_Upper"].values, df["BB_Lower"].values,
                                 alpha=0.05, color="#60a5fa")

        # Trade markers
        if self.cb_trades.isChecked():
            for t in trades:
                ec = GREEN if t.pnl > 0 else RED
                ax1.axvspan(t.entry_time, t.exit_time or t.entry_time, alpha=0.06, color=ec)
                marker = "^" if t.direction == "long" else "v"
                mc = GREEN if t.direction == "long" else RED
                ax1.scatter(t.entry_time, t.entry_price, marker=marker,
                            color=mc, s=30, zorder=5, edgecolors="none")
                if t.exit_time:
                    ax1.scatter(t.exit_time, t.exit_price, marker="x",
                                color=ec, s=30, zorder=5)
                if t.stop_loss:
                    ax1.plot([t.entry_time, t.exit_time or t.entry_time],
                             [t.stop_loss, t.stop_loss], "--", color=RED,
                             linewidth=0.4, alpha=0.4)
                if t.take_profit:
                    ax1.plot([t.entry_time, t.exit_time or t.entry_time],
                             [t.take_profit, t.take_profit], "--", color=GREEN,
                             linewidth=0.4, alpha=0.4)

        ax1.set_ylabel("Price", color=grey, fontsize=9)
        ax1.tick_params(colors=grey, labelsize=7)
        for sp in ax1.spines.values():
            sp.set_color(BORDER)
        ax1.xaxis.set_ticklabels([])
        ax1.set_title(f"{strategy_name}", color=TEXT_PRI, fontsize=11,
                       fontweight="bold", loc="left", pad=8)

        if ax1.get_legend_handles_labels()[1]:
            ax1.legend(loc="upper left", fontsize=7, framealpha=0.5,
                       facecolor=panel, edgecolor=BORDER, labelcolor=grey)

        # ── Equity Curve ──
        ax2 = self.figure.add_subplot(gs[1], sharex=ax1)
        ax2.set_facecolor(panel)
        eq_series = eq_df["equity"]
        init_cash = bt.init_cash
        ax2.plot(eq_series.index, eq_series.values, color=BLUE, linewidth=1.0)
        ax2.axhline(init_cash, color=grey, linewidth=0.5, linestyle="--", alpha=0.5)
        ax2.fill_between(eq_series.index, init_cash, eq_series.values,
                         where=eq_series >= init_cash, alpha=0.12, color=GREEN)
        ax2.fill_between(eq_series.index, init_cash, eq_series.values,
                         where=eq_series < init_cash, alpha=0.12, color=RED)
        ax2.set_ylabel("Equity $", color=grey, fontsize=9)
        ax2.tick_params(colors=grey, labelsize=7)
        for sp in ax2.spines.values():
            sp.set_color(BORDER)
        ax2.xaxis.set_ticklabels([])

        # ── Drawdown ──
        ax3 = self.figure.add_subplot(gs[2], sharex=ax1)
        ax3.set_facecolor(panel)
        roll_max = eq_series.cummax()
        dd = (eq_series - roll_max) / roll_max * 100
        ax3.fill_between(dd.index, 0, dd.values, color=RED, alpha=0.4)
        max_dd = dd.min()
        ax3.axhline(max_dd, color=RED, linewidth=0.5, linestyle="--", alpha=0.6)
        ax3.set_ylabel("DD %", color=grey, fontsize=9)
        ax3.tick_params(colors=grey, labelsize=7)
        for sp in ax3.spines.values():
            sp.set_color(BORDER)
        plt.setp(ax3.get_xticklabels(), rotation=15, ha="right", fontsize=7)

        self.figure.tight_layout(rect=[0, 0, 1, 1])
        self.canvas.draw()

        # Update drawdown events table
        self._update_dd_table(eq_series)

    def _update_dd_table(self, eq_series):
        """Find and display top 10 worst drawdown events."""
        roll_max = eq_series.cummax()
        dd_pct = (eq_series - roll_max) / roll_max * 100

        events = []
        in_dd = False
        dd_start = None
        dd_low = None
        dd_low_date = None

        for i in range(len(dd_pct)):
            if dd_pct.iloc[i] < -0.5:  # threshold
                if not in_dd:
                    in_dd = True
                    dd_start = dd_pct.index[i]
                    dd_low = dd_pct.iloc[i]
                    dd_low_date = dd_pct.index[i]
                else:
                    if dd_pct.iloc[i] < dd_low:
                        dd_low = dd_pct.iloc[i]
                        dd_low_date = dd_pct.index[i]
            else:
                if in_dd:
                    recovery_date = dd_pct.index[i]
                    duration = (dd_low_date - dd_start).days
                    recovery_time = (recovery_date - dd_low_date).days
                    events.append({
                        "start": dd_start,
                        "lowest": dd_low_date,
                        "recovery": recovery_date,
                        "depth": dd_low,
                        "duration": duration,
                        "recovery_time": recovery_time,
                    })
                    in_dd = False

        # If still in drawdown at end
        if in_dd:
            events.append({
                "start": dd_start,
                "lowest": dd_low_date,
                "recovery": None,
                "depth": dd_low,
                "duration": (dd_low_date - dd_start).days if dd_start else 0,
                "recovery_time": None,
            })

        # Sort by depth, take top 10
        events.sort(key=lambda e: e["depth"])
        events = events[:10]

        self.dd_table.setRowCount(len(events))
        for row, ev in enumerate(events):
            self.dd_table.setItem(row, 0, QTableWidgetItem(
                ev["start"].strftime("%Y-%m-%d") if ev["start"] else ""))
            self.dd_table.setItem(row, 1, QTableWidgetItem(
                ev["lowest"].strftime("%Y-%m-%d") if ev["lowest"] else ""))
            self.dd_table.setItem(row, 2, QTableWidgetItem(
                ev["recovery"].strftime("%Y-%m-%d") if ev["recovery"] else "Ongoing"))

            depth_item = QTableWidgetItem(f"{ev['depth']:.1f}%")
            depth_item.setForeground(QColor(RED))
            self.dd_table.setItem(row, 3, depth_item)

            self.dd_table.setItem(row, 4, QTableWidgetItem(
                f"{ev['duration']}d" if ev['duration'] is not None else "—"))
            self.dd_table.setItem(row, 5, QTableWidgetItem(
                f"{ev['recovery_time']}d" if ev['recovery_time'] is not None else "—"))

    def zoom_to_trade(self, trade):
        """Zoom chart to show a specific trade's time range."""
        if not self._current_strategy or self._current_strategy not in self._results:
            return
        axes = self.figure.get_axes()
        if not axes:
            return
        # Pad the view by 10% on each side
        if trade.entry_time and trade.exit_time:
            import matplotlib.dates as mdates
            duration = (trade.exit_time - trade.entry_time)
            pad = duration * 0.3
            start = mdates.date2num(trade.entry_time - pad)
            end = mdates.date2num(trade.exit_time + pad)
            for ax in axes:
                ax.set_xlim(start, end)
            self.canvas.draw_idle()

    def _save_png(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Chart", "backtest_chart.png", "PNG Files (*.png)"
        )
        if filepath:
            self.figure.savefig(filepath, dpi=150, bbox_inches="tight", facecolor=BG_DEEP)

    def clear(self):
        self._results.clear()
        self._current_strategy = None
        self._regimes = None
        self._zoom_states.clear()
        self.strategy_combo.clear()
        self._draw_placeholder()
