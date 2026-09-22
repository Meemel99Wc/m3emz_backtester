"""
m3emz Backtester — Seasonality Heatmaps
Hour-of-day and month-of-year PnL heatmaps.
"""

import numpy as np
import pandas as pd
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.colors as mcolors

from utils.theme import BG_DEEP, BG_PANEL, BORDER, TEXT_PRI, TEXT_SEC, GREEN, RED


class SeasonalityPanel(QWidget):
    """Hour-of-day and month-of-year PnL heatmaps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Seasonality Analysis")
        header.setStyleSheet(f"color: {TEXT_PRI}; font-size: 14px; font-weight: bold; border: none;")
        layout.addWidget(header)

        # Two heatmaps side by side
        charts_row = QHBoxLayout()

        self.hour_fig = Figure(figsize=(6, 3.5), facecolor=BG_DEEP, dpi=100)
        self.hour_canvas = FigureCanvas(self.hour_fig)
        self.hour_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        charts_row.addWidget(self.hour_canvas, 1)

        self.month_fig = Figure(figsize=(6, 3.5), facecolor=BG_DEEP, dpi=100)
        self.month_canvas = FigureCanvas(self.month_fig)
        self.month_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        charts_row.addWidget(self.month_canvas, 1)

        layout.addLayout(charts_row, 1)

        # Placeholder
        self.placeholder = QLabel("Run a backtest to see seasonality patterns")
        self.placeholder.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px; border: none;")
        self.placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.placeholder)

    def update_with_results(self, trades):
        """Generate heatmaps from trade list."""
        if not trades:
            self.placeholder.setText("No trades in this backtest — nothing to show in seasonality.")
            self.placeholder.setVisible(True)
            return

        self.placeholder.setVisible(False)
        self._draw_hour_heatmap(trades)
        self._draw_month_heatmap(trades)

    def _draw_hour_heatmap(self, trades):
        self.hour_fig.clear()
        ax = self.hour_fig.add_subplot(111)
        ax.set_facecolor(BG_PANEL)

        # Build 24 hours x 7 days grid
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        grid = np.full((7, 24), np.nan)
        counts = np.zeros((7, 24), dtype=int)

        for t in trades:
            if t.entry_time is None:
                continue
            dow = t.entry_time.weekday()
            hour = t.entry_time.hour
            if np.isnan(grid[dow, hour]):
                grid[dow, hour] = 0
            grid[dow, hour] += t.pnl
            counts[dow, hour] += 1

        # Convert to average
        with np.errstate(divide="ignore", invalid="ignore"):
            avg_grid = np.where(counts > 0, grid / counts, np.nan)

        # Custom colormap: red -> white -> green
        cmap = mcolors.LinearSegmentedColormap.from_list(
            "pnl", [(0.8, 0.1, 0.1), (1, 1, 1), (0.1, 0.8, 0.3)]
        )

        vmax = np.nanmax(np.abs(avg_grid)) if not np.all(np.isnan(avg_grid)) else 1
        im = ax.imshow(
            avg_grid, cmap=cmap, aspect="auto",
            vmin=-vmax, vmax=vmax, interpolation="nearest"
        )

        ax.set_xticks(range(24))
        ax.set_xticklabels([str(h) for h in range(24)], fontsize=6)
        ax.set_yticks(range(7))
        ax.set_yticklabels(days, fontsize=8)
        ax.set_xlabel("Hour (UTC)", color=TEXT_SEC, fontsize=9)
        ax.set_title("Avg PnL by Hour & Day", color=TEXT_PRI, fontsize=11, fontweight="bold")
        ax.tick_params(colors=TEXT_SEC, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color(BORDER)

        # Add text annotations for cells with data
        for i in range(7):
            for j in range(24):
                if not np.isnan(avg_grid[i, j]) and counts[i, j] > 0:
                    val = avg_grid[i, j]
                    color = "black" if abs(val) < vmax * 0.5 else "white"
                    if abs(val) >= 10:
                        txt = f"{val:.0f}"
                    else:
                        txt = f"{val:.1f}"
                    ax.text(j, i, txt, ha="center", va="center", fontsize=5, color=color)

        self.hour_fig.colorbar(im, ax=ax, shrink=0.8, label="Avg PnL $")
        self.hour_fig.tight_layout()
        self.hour_canvas.draw()

    def _draw_month_heatmap(self, trades):
        self.month_fig.clear()
        ax = self.month_fig.add_subplot(111)
        ax.set_facecolor(BG_PANEL)

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        # Collect year/month data
        year_months = {}
        for t in trades:
            if t.entry_time is None:
                continue
            year = t.entry_time.year
            month = t.entry_time.month - 1
            if year not in year_months:
                year_months[year] = {"pnl": np.zeros(12), "count": np.zeros(12, dtype=int)}
            year_months[year]["pnl"][month] += t.pnl
            year_months[year]["count"][month] += 1

        if not year_months:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    color=TEXT_SEC, transform=ax.transAxes)
            self.month_canvas.draw()
            return

        years = sorted(year_months.keys())
        grid = np.full((len(years), 12), np.nan)
        for i, year in enumerate(years):
            data = year_months[year]
            for m in range(12):
                if data["count"][m] > 0:
                    grid[i, m] = data["pnl"][m] / data["count"][m]

        cmap = mcolors.LinearSegmentedColormap.from_list(
            "pnl", [(0.8, 0.1, 0.1), (1, 1, 1), (0.1, 0.8, 0.3)]
        )
        vmax = np.nanmax(np.abs(grid)) if not np.all(np.isnan(grid)) else 1
        im = ax.imshow(
            grid, cmap=cmap, aspect="auto",
            vmin=-vmax, vmax=vmax, interpolation="nearest"
        )

        ax.set_xticks(range(12))
        ax.set_xticklabels(months, fontsize=8)
        ax.set_yticks(range(len(years)))
        ax.set_yticklabels([str(y) for y in years], fontsize=8)
        ax.set_title("Avg PnL by Month & Year", color=TEXT_PRI, fontsize=11, fontweight="bold")
        ax.tick_params(colors=TEXT_SEC, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color(BORDER)

        # Text annotations
        for i in range(len(years)):
            for j in range(12):
                if not np.isnan(grid[i, j]):
                    val = grid[i, j]
                    color = "black" if abs(val) < vmax * 0.5 else "white"
                    ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7, color=color)

        self.month_fig.colorbar(im, ax=ax, shrink=0.8, label="Avg PnL $")
        self.month_fig.tight_layout()
        self.month_canvas.draw()