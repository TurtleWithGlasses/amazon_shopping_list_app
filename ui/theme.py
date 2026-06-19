"""Application theming: Fusion base + hand-rolled QSS in three looks."""
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

DEFAULT_FONT_SIZE = 10

# Drop a sci-fi .ttf/.otf here (e.g. Orbitron) and it's used automatically.
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# Qt walks this list and uses the first installed family; Bahnschrift ships with
# Windows 11 and reads as technical/sci-fi, so it's a solid fallback.
SCIFI_FONT_STACK = ["Orbitron", "Rajdhani", "Bahnschrift", "Consolas", "Segoe UI"]

_bundled_families = None


def _load_bundled_fonts():
    global _bundled_families
    if _bundled_families is None:
        _bundled_families = []
        if _FONT_DIR.is_dir():
            for path in sorted(_FONT_DIR.glob("*.ttf")) + sorted(_FONT_DIR.glob("*.otf")):
                font_id = QFontDatabase.addApplicationFont(str(path))
                if font_id != -1:
                    _bundled_families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return _bundled_families


def user_font_size() -> int:
    try:
        return int(QSettings().value("font_size", DEFAULT_FONT_SIZE))
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE


def _font_families() -> list:
    # A user-chosen font (Settings → Appearance) takes priority over the bundled
    # Orbitron and the built-in sci-fi fallback stack.
    user_family = QSettings().value("font_family")
    ordered = ([user_family] if user_family else []) + _load_bundled_fonts() + SCIFI_FONT_STACK
    families, seen = [], set()
    for fam in ordered:
        if fam and fam not in seen:
            seen.add(fam)
            families.append(fam)
    return families


def _font_css() -> str:
    return ", ".join(f'"{fam}"' for fam in _font_families())


def _apply_font(app) -> None:
    font = QFont()
    font.setFamilies(_font_families())
    font.setPointSize(user_font_size())
    app.setFont(font)

# Each theme is a flat color map consumed by the palette + QSS builders.
THEMES = {
    "light": {
        "window": "#f5f6f8", "base": "#ffffff", "alt": "#eef1f5",
        "text": "#1f2329", "subtext": "#6b7280", "border": "#d6dae0",
        "accent": "#2563eb", "accent_text": "#ffffff", "header": "#e9edf2",
        "button": "#ffffff", "selection": "#2563eb", "selection_text": "#ffffff",
    },
    "dark": {
        "window": "#1e1f24", "base": "#26282e", "alt": "#2c2f36",
        "text": "#e6e8eb", "subtext": "#9aa0a8", "border": "#3a3d45",
        "accent": "#3b82f6", "accent_text": "#ffffff", "header": "#2a2d34",
        "button": "#2f323a", "selection": "#3b82f6", "selection_text": "#ffffff",
    },
    "material": {
        "window": "#1b1f24", "base": "#222831", "alt": "#2a313b",
        "text": "#eceff1", "subtext": "#90a4ae", "border": "#37414d",
        "accent": "#26a69a", "accent_text": "#04302b", "header": "#263038",
        "button": "#2b333d", "selection": "#26a69a", "selection_text": "#04302b",
    },
}

# (key, display label) — order shown in the Settings dropdown.
THEME_CHOICES = [("material", "Material (teal)"), ("light", "Light"), ("dark", "Dark")]
DEFAULT_THEME = "material"


def _palette(t: dict) -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    p.setColor(role.Window, QColor(t["window"]))
    p.setColor(role.WindowText, QColor(t["text"]))
    p.setColor(role.Base, QColor(t["base"]))
    p.setColor(role.AlternateBase, QColor(t["alt"]))
    p.setColor(role.Text, QColor(t["text"]))
    p.setColor(role.Button, QColor(t["button"]))
    p.setColor(role.ButtonText, QColor(t["text"]))
    p.setColor(role.Highlight, QColor(t["accent"]))
    p.setColor(role.HighlightedText, QColor(t["accent_text"]))
    p.setColor(role.ToolTipBase, QColor(t["base"]))
    p.setColor(role.ToolTipText, QColor(t["text"]))
    p.setColor(role.PlaceholderText, QColor(t["subtext"]))
    return p


def _qss(t: dict, font_css: str) -> str:
    return """
    QWidget {{ background: {window}; color: {text}; font-family: {font}; }}
    QLabel, QCheckBox {{ background: transparent; }}
    QToolTip {{ background: {base}; color: {text}; border: 1px solid {border}; padding: 4px; }}
    QMainWindow, QDialog {{ background: {window}; }}

    QMenuBar {{ background: {header}; }}
    QMenuBar::item {{ background: transparent; padding: 4px 10px; }}
    QMenuBar::item:selected {{ background: {accent}; color: {accent_text}; border-radius: 4px; }}
    QMenu {{ background: {base}; border: 1px solid {border}; }}
    QMenu::item {{ padding: 5px 22px; }}
    QMenu::item:selected {{ background: {accent}; color: {accent_text}; }}
    QStatusBar {{ background: {header}; color: {subtext}; }}

    QPushButton {{
        background: {button}; color: {text};
        border: 1px solid {border}; border-radius: 6px; padding: 5px 12px;
    }}
    QPushButton:hover {{ border-color: {accent}; }}
    QPushButton:pressed {{ background: {accent}; color: {accent_text}; border-color: {accent}; }}
    QPushButton:disabled {{ color: {subtext}; background: {window}; }}

    QToolButton {{ background: {button}; border: 1px solid {border}; border-radius: 6px; }}
    QToolButton:hover {{ border-color: {accent}; }}
    QToolButton:pressed {{ background: {accent}; }}

    QCheckBox::indicator {{
        width: 16px; height: 16px; border: 1px solid {border};
        border-radius: 4px; background: {base};
    }}
    QCheckBox::indicator:hover {{ border-color: {accent}; }}
    QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}

    QLineEdit, QComboBox {{
        background: {base}; border: 1px solid {border}; border-radius: 6px; padding: 5px 8px;
        selection-background-color: {accent}; selection-color: {accent_text};
    }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {base}; border: 1px solid {border};
        selection-background-color: {accent}; selection-color: {accent_text};
    }}

    QGroupBox {{ border: 1px solid {border}; border-radius: 8px; margin-top: 12px; padding: 10px 8px 8px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {subtext}; }}

    QTableView {{
        background: {base}; alternate-background-color: {alt};
        gridline-color: {border}; border: 1px solid {border}; border-radius: 8px;
    }}
    QTableView::item {{ padding: 2px 4px; }}
    QTableView::item:selected {{ background: {selection}; color: {selection_text}; }}
    QHeaderView::section {{
        background: {header}; color: {subtext}; padding: 6px; border: none;
        border-right: 1px solid {border}; border-bottom: 1px solid {border};
    }}

    QScrollBar:vertical {{ background: {window}; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {border}; border-radius: 6px; min-height: 24px; }}
    QScrollBar:horizontal {{ background: {window}; height: 12px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {border}; border-radius: 6px; min-width: 24px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    """.format(font=font_css, **t)


def apply_theme(app, mode: str = DEFAULT_THEME) -> None:
    theme = THEMES.get(mode, THEMES[DEFAULT_THEME])
    app.setStyle("Fusion")
    app.setPalette(_palette(theme))
    _apply_font(app)
    app.setStyleSheet(_qss(theme, _font_css()))
