"""
m3emz Backtester — Stats Panel (Below Chart)
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from utils.theme import (
    BG_DEEP, BG_PANEL, BG_HOVER, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, ORANGE, FONT_MONO
)


class StatCard(QFrame):
    """Single stat card widget with flexible sizing."""

    def __init__(self, label, value, detail="", alt_bg=False, parent=None):
        super().__init__(parent)
        self.label_text = label
        self.value_raw = value

        # Flexible sizing — no fixed height, width constrained
        self.setMinimumWidth(130)
        self.setMaximumWidth(180)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        bg = BG_HOVER if alt_bg else BG_PANEL
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {BORDER};
            }}
            QFrame:hover {{
                background-color: {BG_HOVER};
                border: 1px solid {BLUE};
            }}
        """)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(2)

        # Label — secondary colour, small, bold
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 10px; font-weight: bold; "
            f"border: none; letter-spacing: 0.5px;"
        )
        lbl.setAlignment(Qt.AlignLeft)
        layout.addWidget(lbl)

        # Value — monospace, colour-coded, 13px to avoid overflow
        val_color = self._get_value_color(label, value)
        val_text = self._format_value(label, value)

        val_lbl = QLabel(val_text)
        val_lbl.setWordWrap(False)
        val_lbl.setStyleSheet(
            f"color: {val_color}; font-size: 13px; font-weight: bold; "
            f"border: none; font-family: {FONT_MONO};"
        )
        val_lbl.setAlignment(Qt.AlignLeft)
        layout.addWidget(val_lbl)

        # Detail line
        if detail:
            det_lbl = QLabel(detail)
            det_lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 9px; border: none;")
            layout.addWidget(det_lbl)

    def _get_value_color(self, label, value):
        if not isinstance(value, (int, float)):
            return TEXT_PRI
        if "Return" in label:
            return GREEN if value >= 0 else RED
        if "Win Rate" in label:
            return GREEN if value >= 50 else ORANGE if value >= 40 else RED
        if "Drawdown" in label:
            return RED
        if "Sharpe" in label:
            return GREEN if value > 1 else ORANGE if value > 0 else RED
        if "Profit Factor" in label:
            return GREEN if value > 1.5 else ORANGE if value > 1 else RED
        if "Loss" in label:
            return RED
        if "Win" in label and "$" in label:
            return GREEN
        if "Equity" in label:
            return TEXT_PRI
        return TEXT_PRI

    def _format_value(self, label, value):
        """Smart formatting with K/M abbreviation for large dollar amounts."""
        if not isinstance(value, (int, float)):
            return str(value)
        # Percentage fields
        if "%" in label:
            sign = "+" if value > 0 else ""
            return f"{sign}{value:.1f}%"
        # Dollar / Equity / Commission fields — abbreviate large numbers
        if "$" in label or "Equity" in label or "Commission" in label:
            if abs(value) >= 1_000_000:
                return f"${value / 1_000_000:.2f}M"
            if abs(value) >= 10_000:
                return f"${value / 1_000:.1f}K"
            return f"${value:,.2f}"
        # Ratio / Factor fields
        if "Ratio" in label or "Factor" in label:
            return f"{value:.3f}"
        # Duration
        if "Duration" in label:
            return f"{value:.1f}h"
        # Integer-like values
        if isinstance(value, int) or (isinstance(value, float) and value == int(value)):
            return f"{int(value):,}"
        return f"{value:.2f}"


class StatsPanel(QWidget):
    """Horizontal scrollable strip of stat cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Flexible height — breathe between 90 and 130
        self.setMinimumHeight(90)
        self.setMaximumHeight(130)
        self.setStyleSheet(f"background-color: {BG_DEEP}; border-top: 1px solid {BORDER};")

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 2, 0, 2)
        main_layout.setSpacing(0)

        # Scroll area fills available height
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {BG_DEEP};
                border: none;
            }}
        """)

        self.cards_widget = QWidget()
        self.cards_widget.setStyleSheet(f"background-color: {BG_DEEP};")
        self.cards_layout = QHBoxLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch()

        self.scroll.setWidget(self.cards_widget)
        main_layout.addWidget(self.scroll, 1)

        # Placeholder
        self.placeholder = QLabel("Run a backtest to see statistics")
        self.placeholder.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px;")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.cards_layout.insertWidget(0, self.placeholder)

    def update_stats(self, stats: dict, trade_count: int = 0):
        """Display stats as a row of cards."""
        # Clear existing cards
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not stats:
            self.placeholder = QLabel("No stats available")
            self.placeholder.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px;")
            self.placeholder.setAlignment(Qt.AlignCenter)
            self.cards_layout.addWidget(self.placeholder)
            return

        # Ordered stats to display
        stat_order = [
            "Total Return %", "B&H Return %", "Sharpe Ratio", "Profit Factor",
            "Win Rate %", "Max Drawdown %", "Total Trades", "Avg Win $",
            "Avg Loss $", "Largest Win $", "Largest Loss $", "SL Exits",
            "TP Exits", "Avg Duration h", "Final Equity $", "Commission Paid $"
        ]

        for idx, key in enumerate(stat_order):
            if key in stats:
                detail = ""
                if key == "Total Trades":
                    detail = f"{stats.get('Win Rate %', 0):.0f}% win rate"
                # Alternating subtle background for readability
                alt_bg = (idx % 2 == 1)
                card = StatCard(key, stats[key], detail, alt_bg=alt_bg)
                self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def clear(self):
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.placeholder = QLabel("Run a backtest to see statistics")
        self.placeholder.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px;")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.cards_layout.addWidget(self.placeholder)
