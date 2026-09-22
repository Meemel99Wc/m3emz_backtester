"""
m3emz Backtester — Dark / Light Trading Terminal Theme
"""

# ── Dark Theme (default) ──────────────────────────────
BG_DEEP    = "#0d1117"
BG_PANEL   = "#161b22"
BG_HOVER   = "#1f2937"
BORDER     = "#30363d"
TEXT_PRI   = "#e6edf3"
TEXT_SEC   = "#8b949e"
GREEN      = "#00ff88"
RED        = "#ff4444"
BLUE       = "#1B74E4"
ORANGE     = "#f59e0b"
PURPLE     = "#a78bfa"

# ── Font Families ───────────────────────────────────────
FONT_MONO  = "JetBrains Mono, Consolas, Courier New, monospace"
FONT_UI    = "Segoe UI, Arial, sans-serif"

# ── Light Theme Palette ─────────────────────────────────
LIGHT = {
    "BG_DEEP":  "#f8f9fa",
    "BG_PANEL": "#ffffff",
    "BG_HOVER": "#e9ecef",
    "BORDER":   "#dee2e6",
    "TEXT_PRI": "#212529",
    "TEXT_SEC": "#6c757d",
    "GREEN":    "#198754",
    "RED":      "#dc3545",
    "BLUE":     "#0d6efd",
    "ORANGE":   "#fd7e14",
    "PURPLE":   "#6f42c1",
}

DARK = {
    "BG_DEEP":  BG_DEEP,
    "BG_PANEL": BG_PANEL,
    "BG_HOVER": BG_HOVER,
    "BORDER":   BORDER,
    "TEXT_PRI": TEXT_PRI,
    "TEXT_SEC": TEXT_SEC,
    "GREEN":    GREEN,
    "RED":      RED,
    "BLUE":     BLUE,
    "ORANGE":   ORANGE,
    "PURPLE":   PURPLE,
}


def _build_stylesheet(t: dict) -> str:
    return f"""
QMainWindow, QWidget {{
    background-color: {t['BG_DEEP']};
    color: {t['TEXT_PRI']};
    font-family: {FONT_UI};
    font-size: 13px;
}}
QSplitter::handle {{
    background-color: {t['BORDER']};
    width: 2px;
}}
QLabel {{
    color: {t['TEXT_PRI']};
}}
QLineEdit, QDoubleSpinBox, QSpinBox {{
    background-color: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    padding: 6px 10px;
    font-family: {FONT_MONO};
    font-size: 12px;
    selection-background-color: {t['BLUE']};
}}
QLineEdit:focus, QDoubleSpinBox:focus {{
    border: 1px solid {t['BLUE']};
}}
QComboBox {{
    background-color: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    padding: 6px 10px;
    font-size: 12px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    selection-background-color: {t['BG_HOVER']};
}}
QPushButton {{
    background-color: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    padding: 8px 16px;
    font-size: 12px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {t['BG_HOVER']};
}}
QPushButton:pressed {{
    background-color: {t['BORDER']};
}}
QPushButton:disabled {{
    color: {t['TEXT_SEC']};
    background-color: {t['BG_DEEP']};
}}
QPushButton#primary {{
    background-color: {t['BLUE']};
    color: white;
    border: none;
}}
QPushButton#primary:hover {{
    background-color: #2563eb;
}}
QPushButton#primary:disabled {{
    background-color: #1e3a5f;
    color: #5a7da0;
}}
QListWidget {{
    background-color: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    font-size: 12px;
    outline: none;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {t['BORDER']};
}}
QListWidget::item:selected {{
    background-color: {t['BG_HOVER']};
}}
QListWidget::item:hover {{
    background-color: {t['BG_HOVER']};
}}
QScrollBar:vertical {{
    background: {t['BG_DEEP']};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {t['BORDER']};
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {t['BG_DEEP']};
    height: 8px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {t['BORDER']};
    min-width: 30px;
    border-radius: 4px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QProgressBar {{
    background: {t['BG_PANEL']};
    border: 1px solid {t['BORDER']};
    text-align: center;
    color: {t['TEXT_PRI']};
    font-size: 11px;
    height: 18px;
}}
QProgressBar::chunk {{
    background: {t['BLUE']};
}}
QStatusBar {{
    background: {t['BG_PANEL']};
    color: {t['TEXT_SEC']};
    border-top: 1px solid {t['BORDER']};
    font-size: 11px;
}}
QMenuBar {{
    background: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border-bottom: 1px solid {t['BORDER']};
}}
QMenu {{
    background: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
}}
QMenu::item:selected {{
    background: {t['BG_HOVER']};
}}
QToolTip {{
    background: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    padding: 4px;
    font-size: 11px;
}}
QCheckBox {{
    color: {t['TEXT_PRI']};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {t['BORDER']};
    background: {t['BG_PANEL']};
}}
QCheckBox::indicator:checked {{
    background: {t['BLUE']};
    border: 1px solid {t['BLUE']};
}}
QTextEdit {{
    background-color: {t['BG_PANEL']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    font-size: 12px;
    selection-background-color: {t['BLUE']};
}}
QGroupBox {{
    color: {t['TEXT_SEC']};
    border: 1px solid {t['BORDER']};
    margin-top: 8px;
    padding-top: 16px;
    font-size: 11px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}}
QTabWidget::pane {{
    background-color: {t['BG_DEEP']};
    border: 1px solid {t['BORDER']};
}}
QTabBar::tab {{
    background-color: {t['BG_PANEL']};
    color: {t['TEXT_SEC']};
    border: 1px solid {t['BORDER']};
    padding: 6px 14px;
    font-size: 11px;
    font-weight: bold;
}}
QTabBar::tab:selected {{
    background-color: {t['BG_DEEP']};
    color: {t['TEXT_PRI']};
    border-bottom: 2px solid {t['BLUE']};
}}
QTabBar::tab:hover {{
    background-color: {t['BG_HOVER']};
    color: {t['TEXT_PRI']};
}}
"""


# ── Pre-built stylesheets ──────────────────────────────
STYLESHEET = _build_stylesheet(DARK)
STYLESHEET_LIGHT = _build_stylesheet(LIGHT)


def apply_theme(app, is_dark=True):
    """Apply dark or light theme globally and update module-level constants."""
    global BG_DEEP, BG_PANEL, BG_HOVER, BORDER, TEXT_PRI, TEXT_SEC
    global GREEN, RED, BLUE, ORANGE, PURPLE, STYLESHEET

    t = DARK if is_dark else LIGHT
    BG_DEEP  = t["BG_DEEP"]
    BG_PANEL = t["BG_PANEL"]
    BG_HOVER = t["BG_HOVER"]
    BORDER   = t["BORDER"]
    TEXT_PRI = t["TEXT_PRI"]
    TEXT_SEC = t["TEXT_SEC"]
    GREEN    = t["GREEN"]
    RED      = t["RED"]
    BLUE     = t["BLUE"]
    ORANGE   = t["ORANGE"]
    PURPLE   = t["PURPLE"]
    STYLESHEET = _build_stylesheet(t)
    app.setStyleSheet(STYLESHEET)
