"""Visual language for the companion and settings UI."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

ACCENT = "#b9a7ff"
ACCENT_STRONG = "#8c78ff"
STAR_BLUE = "#8fd8ff"
TEXT = "#f3efff"
TEXT_MUTED = "#a9a3c2"
SURFACE = "#12101c"
SURFACE_ALT = "#1a1728"
BORDER = "#332d4a"
DANGER = "#ff8fa8"

STYLE_NAMES = {
    "soft": (QColor(185, 167, 255), QColor(21, 18, 36, 242)),
    "star": (QColor(126, 203, 255), QColor(14, 23, 39, 244)),
    "warm": (QColor(255, 178, 196), QColor(36, 20, 30, 242)),
}


def app_font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("Microsoft YaHei UI", size)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setWeight(weight)
    return font


def app_icon(size: int = 256) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#7d6df0"))
    gradient.setColorAt(0.55, QColor("#3d2c75"))
    gradient.setColorAt(1.0, QColor("#111225"))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor(210, 196, 255, 150), max(2, size // 80)))
    painter.drawEllipse(QRectF(size * 0.08, size * 0.08, size * 0.84, size * 0.84))

    # Four-point star.
    cx, cy = size * 0.5, size * 0.50
    outer, inner = size * 0.30, size * 0.095
    path = QPainterPath()
    for index in range(8):
        angle = -3.14159265 / 2 + index * 3.14159265 / 4
        radius = outer if index % 2 == 0 else inner
        point = QPointF(cx + radius * __import__("math").cos(angle), cy + radius * __import__("math").sin(angle))
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    star_gradient = QLinearGradient(cx - outer, cy - outer, cx + outer, cy + outer)
    star_gradient.setColorAt(0.0, QColor("#fff7ff"))
    star_gradient.setColorAt(0.6, QColor("#b9a7ff"))
    star_gradient.setColorAt(1.0, QColor("#7ecbff"))
    painter.setBrush(star_gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(path)

    # Small satellite stars.
    painter.setBrush(QColor(255, 255, 255, 190))
    painter.drawEllipse(QPointF(size * 0.74, size * 0.26), size * 0.025, size * 0.025)
    painter.drawEllipse(QPointF(size * 0.25, size * 0.72), size * 0.018, size * 0.018)
    painter.end()
    return QIcon(pixmap)


def settings_stylesheet() -> str:
    return f"""
    QWidget {{
        background: {SURFACE};
        color: {TEXT};
        font-family: "Microsoft YaHei UI", "Segoe UI";
        font-size: 13px;
    }}
    QDialog, QMainWindow {{ background: {SURFACE}; }}
    QLabel {{ background: transparent; }}
    QLabel#Title {{ font-size: 23px; font-weight: 700; color: {TEXT}; }}
    QLabel#Subtitle {{ color: {TEXT_MUTED}; font-size: 12px; }}
    QLabel#SectionTitle {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
    QLabel#Hint {{ color: {TEXT_MUTED}; font-size: 11px; }}
    QLabel#Danger {{ color: {DANGER}; }}
    QLabel#Accent {{ color: {ACCENT}; }}
    QGroupBox {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        border-radius: 12px;
        margin-top: 14px;
        padding: 16px 14px 12px 14px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: {ACCENT};
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: #0e0c17;
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 7px 9px;
        selection-background-color: {ACCENT_STRONG};
        color: {TEXT};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {ACCENT};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{ color: #6e6787; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        selection-background-color: #362d59;
        color: {TEXT};
    }}
    QPushButton {{
        background: #211c34;
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 7px 15px;
        color: {TEXT};
    }}
    QPushButton:hover {{ background: #2b2442; border-color: #51466f; }}
    QPushButton:pressed {{ background: #171323; }}
    QPushButton:disabled {{ color: #6f6885; background: #181522; }}
    QPushButton#Primary {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8d7bf4, stop:1 #6f8ff0);
        border: none;
        color: #0f0c18;
        font-weight: 700;
    }}
    QPushButton#Primary:hover {{ background: #b9a7ff; }}
    QPushButton#Danger {{ color: {DANGER}; border-color: #583141; }}
    QPushButton#Ghost {{ background: transparent; }}
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-radius: 12px;
        background: {SURFACE_ALT};
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {TEXT_MUTED};
        padding: 9px 16px;
        margin-right: 2px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
    QTabBar::tab:hover {{ color: {TEXT}; }}
    QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px; height: 16px;
        border: 1px solid #4b4264;
        border-radius: 4px;
        background: #0e0c17;
    }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
    QSlider::groove:horizontal {{
        height: 5px; background: #272138; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: #efe9ff; width: 15px; margin: -5px 0; border-radius: 7px;
    }}
    QListWidget, QTableWidget, QTreeWidget {{
        background: #0f0d18;
        border: 1px solid {BORDER};
        border-radius: 10px;
        alternate-background-color: #14111f;
        selection-background-color: #332a52;
        outline: none;
    }}
    QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
    QListWidget::item:selected {{ background: #332a52; color: {TEXT}; }}
    QHeaderView::section {{
        background: #191526;
        color: {TEXT_MUTED};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 7px;
    }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #3c3453; border-radius: 4px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 9px; }}
    QScrollBar::handle:horizontal {{ background: #3c3453; border-radius: 4px; min-width: 24px; }}
    QToolTip {{
        background: #1e1930;
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 5px;
    }}
    QMenu {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        padding: 6px;
        border-radius: 8px;
    }}
    QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: #342b52; }}
    QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
    QProgressBar {{
        background: #100e18; border: 1px solid {BORDER}; border-radius: 5px;
        text-align: center; color: {TEXT_MUTED}; height: 8px;
    }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
    """
