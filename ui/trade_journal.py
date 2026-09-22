"""
m3emz Backtester — Trade Journal & Deep Analysis Tab
Full trade log with filtering, sorting, and jump-to-chart.
"""

import csv
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QComboBox,
    QLineEdit, QAbstractItemView, QFileDialog, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from utils.theme import (
    BG_DEEP, BG_PANEL, BORDER, TEXT_PRI, TEXT_SEC,
    GREEN, RED, BLUE, ORANGE, FONT_MONO
)


class TradeJournal(QWidget):
    """Trade journal with full trade log, filtering, and export."""

    jump_to_trade = pyqtSignal(object)  # emits Trade object

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        self._all_trades = []
        self._symbol = "BTCUSDT"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Header ──
        header = QLabel("Trade Journal")
        header.setStyleSheet(f"color: {TEXT_PRI}; font-size: 14px; font-weight: bold; border: none;")
        layout.addWidget(header)

        # ── Filter Bar ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        filter_row.addWidget(self._make_label("Direction:"))
        self.dir_filter = QComboBox()
        self.dir_filter.addItems(["All", "Long", "Short"])
        self.dir_filter.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.dir_filter)

        filter_row.addWidget(self._make_label("Exit:"))
        self.exit_filter = QComboBox()
        self.exit_filter.addItems(["All", "SL", "TP", "Signal", "EOD"])
        self.exit_filter.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.exit_filter)

        filter_row.addWidget(self._make_label("PnL Min $:"))
        self.pnl_min = QLineEdit()
        self.pnl_min.setFixedWidth(70)
        self.pnl_min.setPlaceholderText("-999")
        self.pnl_min.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.pnl_min)

        filter_row.addWidget(self._make_label("Max $:"))
        self.pnl_max = QLineEdit()
        self.pnl_max.setFixedWidth(70)
        self.pnl_max.setPlaceholderText("999")
        self.pnl_max.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.pnl_max)

        filter_row.addStretch()

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        filter_row.addWidget(export_btn)

        layout.addLayout(filter_row)

        # ── Table ──
        self.table = QTableWidget()
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels([
            "#", "Symbol", "Entry Time", "Exit Time", "Direction",
            "Entry $", "Exit $", "SL $", "TP $", "PnL $",
            "PnL %", "Duration", "Exit Reason"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {BG_PANEL};
                color: {TEXT_PRI};
                gridline-color: {BORDER};
                font-family: {FONT_MONO};
                font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {BG_DEEP};
                color: {TEXT_SEC};
                border: 1px solid {BORDER};
                padding: 4px;
                font-weight: bold;
                font-size: 10px;
            }}
            QTableWidget::item:selected {{
                background-color: {BLUE};
            }}
        """)
        self.table.doubleClicked.connect(self._on_row_double_click)
        layout.addWidget(self.table, 1)

        # ── Summary Footer ──
        self.footer = QLabel("")
        self.footer.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; border: none; padding: 4px;")
        layout.addWidget(self.footer)

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 10px; border: none;")
        return lbl

    def update_with_results(self, trades, symbol="BTCUSDT"):
        """Populate journal with trade list."""
        self._all_trades = trades
        self._symbol = symbol
        self._apply_filters()

    def _apply_filters(self, *_):
        dir_filter = self.dir_filter.currentText()
        exit_filter = self.exit_filter.currentText()

        try:
            pnl_min = float(self.pnl_min.text()) if self.pnl_min.text().strip() else -1e9
        except ValueError:
            pnl_min = -1e9
        try:
            pnl_max = float(self.pnl_max.text()) if self.pnl_max.text().strip() else 1e9
        except ValueError:
            pnl_max = 1e9

        filtered = []
        for t in self._all_trades:
            if dir_filter == "Long" and t.direction != "long":
                continue
            if dir_filter == "Short" and t.direction != "short":
                continue
            if exit_filter != "All" and (t.exit_reason or "").upper() != exit_filter.upper():
                continue
            if not (pnl_min <= t.pnl <= pnl_max):
                continue
            filtered.append(t)

        self._populate_table(filtered)

        # Summary
        total_pnl = sum(t.pnl for t in filtered)
        durations = []
        for t in filtered:
            if t.exit_time and t.entry_time:
                durations.append((t.exit_time - t.entry_time).total_seconds() / 3600)
        avg_dur = sum(durations) / len(durations) if durations else 0
        sign = "+" if total_pnl >= 0 else ""
        self.footer.setText(
            f"Showing {len(filtered)}/{len(self._all_trades)} trades | "
            f"Filtered PnL: {sign}${total_pnl:,.2f} | "
            f"Avg duration: {avg_dur:.1f}h"
        )

    def _populate_table(self, trades):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(trades))

        for row, t in enumerate(trades):
            pnl_positive = t.pnl > 0
            row_color = QColor(GREEN if pnl_positive else RED)
            row_color.setAlpha(25)

            def make_item(text, align=Qt.AlignRight):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align | Qt.AlignVCenter)
                item.setBackground(row_color)
                return item

            self.table.setItem(row, 0, make_item(row + 1))
            self.table.setItem(row, 1, make_item(self._symbol, Qt.AlignLeft))

            entry_str = t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else ""
            exit_str = t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else ""
            self.table.setItem(row, 2, make_item(entry_str, Qt.AlignLeft))
            self.table.setItem(row, 3, make_item(exit_str, Qt.AlignLeft))

            dir_text = f"{'LONG' if t.direction == 'long' else 'SHORT'}"
            self.table.setItem(row, 4, make_item(dir_text, Qt.AlignCenter))

            self.table.setItem(row, 5, make_item(f"${t.entry_price:,.2f}"))
            self.table.setItem(row, 6, make_item(f"${t.exit_price:,.2f}" if t.exit_price else "—"))
            self.table.setItem(row, 7, make_item(f"${t.stop_loss:,.2f}" if t.stop_loss else "—"))
            self.table.setItem(row, 8, make_item(f"${t.take_profit:,.2f}" if t.take_profit else "—"))

            sign = "+" if t.pnl > 0 else ""
            pnl_item = make_item(f"{sign}${t.pnl:,.2f}")
            pnl_item.setForeground(QColor(GREEN if pnl_positive else RED))
            self.table.setItem(row, 9, pnl_item)

            pnl_pct_item = make_item(f"{sign}{t.pnl_pct:.1f}%")
            pnl_pct_item.setForeground(QColor(GREEN if pnl_positive else RED))
            self.table.setItem(row, 10, pnl_pct_item)

            if t.exit_time and t.entry_time:
                hours = (t.exit_time - t.entry_time).total_seconds() / 3600
                self.table.setItem(row, 11, make_item(f"{hours:.1f}h"))
            else:
                self.table.setItem(row, 11, make_item("—"))

            reason_icons = {"SL": "SL \u2717", "TP": "TP \u2713", "signal": "Signal", "EOD": "EOD"}
            reason_text = reason_icons.get(t.exit_reason, t.exit_reason or "—")
            self.table.setItem(row, 12, make_item(reason_text, Qt.AlignCenter))

        self.table.setSortingEnabled(True)

    def _on_row_double_click(self, index):
        row = index.row()
        # Map filtered rows back — get the trade number from column 0
        item = self.table.item(row, 0)
        if item:
            trade_idx = int(item.text()) - 1
            if 0 <= trade_idx < len(self._all_trades):
                self.jump_to_trade.emit(self._all_trades[trade_idx])

    def _export_csv(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Trade Journal", "trade_journal.csv", "CSV Files (*.csv)"
        )
        if not filepath:
            return

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            # Headers
            headers = []
            for col in range(self.table.columnCount()):
                headers.append(self.table.horizontalHeaderItem(col).text())
            writer.writerow(headers)
            # Rows
            for row in range(self.table.rowCount()):
                row_data = []
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    row_data.append(item.text() if item else "")
                writer.writerow(row_data)
