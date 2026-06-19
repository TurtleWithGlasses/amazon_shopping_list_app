"""Application icon (shopping cart), rendered from SVG to all standard sizes."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icons" / "cart.svg"
_SIZES = (16, 24, 32, 48, 64, 128, 256)


def app_icon() -> QIcon:
    """A crisp multi-resolution cart icon for the window, taskbar, and tray."""
    if not _ICON_PATH.exists():
        return QIcon()
    try:
        from PySide6.QtSvg import QSvgRenderer
    except Exception:
        return QIcon(str(_ICON_PATH))  # rely on Qt's SVG icon plugin

    renderer = QSvgRenderer(str(_ICON_PATH))
    icon = QIcon()
    for size in _SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
