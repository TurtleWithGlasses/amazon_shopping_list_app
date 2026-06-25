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
# `surface_variant` = tonal fill (M3 buttons/inputs); `hover` = state-layer tint;
# `link` = product-name link color, tuned to read well on each theme.
THEMES = {
    "stitch": {
        "window": "#f6f8fc", "base": "#ffffff", "alt": "#eef1f8",
        "text": "#1b1f27", "subtext": "#5b6472", "border": "#cdd3df",
        "accent": "#4f63d2", "accent_text": "#ffffff", "header": "#eef1f8",
        "button": "#eaedf6", "selection": "#4f63d2", "selection_text": "#ffffff",
        "surface_variant": "#e7ebf5", "hover": "#dde3f3", "link": "#3a4ba8",
    },
    "light": {
        "window": "#f5f6f8", "base": "#ffffff", "alt": "#eef1f5",
        "text": "#1f2329", "subtext": "#6b7280", "border": "#d6dae0",
        "accent": "#2563eb", "accent_text": "#ffffff", "header": "#e9edf2",
        "button": "#eaedf2", "selection": "#2563eb", "selection_text": "#ffffff",
        "surface_variant": "#e6e9f0", "hover": "#dfe3ea", "link": "#1f57c4",
    },
    "dark": {
        "window": "#1e1f24", "base": "#26282e", "alt": "#2c2f36",
        "text": "#e6e8eb", "subtext": "#9aa0a8", "border": "#3a3d45",
        "accent": "#3b82f6", "accent_text": "#ffffff", "header": "#2a2d34",
        "button": "#2f323a", "selection": "#3b82f6", "selection_text": "#ffffff",
        "surface_variant": "#343843", "hover": "#3a3f4b", "link": "#8ab4f8",
    },
    "material": {
        "window": "#1b1f24", "base": "#222831", "alt": "#2a313b",
        "text": "#eceff1", "subtext": "#90a4ae", "border": "#37414d",
        "accent": "#26a69a", "accent_text": "#04302b", "header": "#263038",
        "button": "#2b333d", "selection": "#26a69a", "selection_text": "#04302b",
        "surface_variant": "#2f3a44", "hover": "#33414b", "link": "#5ec8bd",
    },
}

# (key, display label) — order shown in the Settings dropdown.
THEME_CHOICES = [
    ("stitch", "Stitch (Material 3)"),
    ("material", "Material (teal)"),
    ("light", "Light"),
    ("dark", "Dark"),
]
DEFAULT_THEME = "stitch"


def link_color() -> QColor:
    """Product-name link color for the active theme (harmonizes per theme)."""
    mode = QSettings().value("theme", DEFAULT_THEME) or DEFAULT_THEME
    theme = THEMES.get(mode, THEMES[DEFAULT_THEME])
    return QColor(theme["link"])


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
    """Material 3 / Google-Stitch-flavored QSS: tonal pill buttons, filled
    rounded inputs, a card-like table, and minimal chrome."""
    return """
    QWidget {{ background: {window}; color: {text}; font-family: {font}; }}
    QLabel, QCheckBox {{ background: transparent; }}
    /* Table cell wrappers stay transparent so the row color/selection shows. */
    #rowcell {{ background: transparent; }}
    QToolTip {{ background: {base}; color: {text}; border: 1px solid {border};
               padding: 6px 8px; border-radius: 6px; }}
    QMainWindow, QDialog {{ background: {window}; }}

    QMenuBar {{ background: {window}; }}
    QMenuBar::item {{ background: transparent; padding: 6px 12px; border-radius: 8px; }}
    QMenuBar::item:selected {{ background: {surface_variant}; color: {text}; }}
    QMenu {{ background: {base}; border: 1px solid {border}; border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 7px 24px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {accent}; color: {accent_text}; }}
    QStatusBar {{ background: {window}; color: {subtext}; }}
    QStatusBar::item {{ border: none; }}

    /* M3 tonal button — the default for secondary actions (incl. row actions). */
    QPushButton {{
        background: {surface_variant}; color: {text};
        border: none; border-radius: 16px; padding: 7px 16px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {hover}; }}
    QPushButton:pressed {{ background: {accent}; color: {accent_text}; }}
    QPushButton:disabled {{ background: {window}; color: {subtext}; }}

    /* M3 filled primary button — set objectName('primary') on key CTAs. */
    QPushButton#primary {{
        background: {accent}; color: {accent_text};
        border: none; border-radius: 18px; padding: 8px 20px; font-weight: 600;
    }}
    QPushButton#primary:hover {{ background: {selection}; }}
    QPushButton#primary:disabled {{ background: {surface_variant}; color: {subtext}; }}

    QToolButton {{ background: {surface_variant}; border: none; border-radius: 8px; padding: 2px; }}
    QToolButton:hover {{ background: {hover}; }}
    QToolButton:pressed {{ background: {accent}; }}

    QCheckBox::indicator {{
        width: 18px; height: 18px; border: 2px solid {subtext};
        border-radius: 5px; background: transparent;
    }}
    QCheckBox::indicator:hover {{ border-color: {accent}; }}
    QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}

    QLineEdit, QComboBox {{
        background: {surface_variant}; border: 1px solid transparent; border-radius: 10px;
        padding: 8px 12px; selection-background-color: {accent}; selection-color: {accent_text};
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; background: {base}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {base}; border: 1px solid {border}; border-radius: 8px; outline: none;
        selection-background-color: {accent}; selection-color: {accent_text};
    }}

    QGroupBox {{ border: 1px solid {border}; border-radius: 12px; margin-top: 14px; padding: 12px 10px 10px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {subtext}; }}

    QTableView {{
        background: {base}; alternate-background-color: {alt};
        gridline-color: transparent; border: 1px solid {border}; border-radius: 12px; outline: none;
    }}
    QTableView::item {{ padding: 4px 6px; border: none; }}
    QTableView::item:selected {{ background: {selection}; color: {selection_text}; }}
    QHeaderView {{ background: {window}; }}
    QHeaderView::section {{
        background: {window}; color: {subtext}; padding: 8px 6px; border: none;
        border-bottom: 2px solid {border}; font-weight: 600;
    }}
    QHeaderView::section:hover {{ color: {text}; }}
    QTableCornerButton::section {{ background: {window}; border: none; }}

    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {subtext}; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; min-width: 30px; }}
    QScrollBar::handle:horizontal:hover {{ background: {subtext}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """.format(font=font_css, **t)


def apply_theme(app, mode: str = DEFAULT_THEME) -> None:
    theme = THEMES.get(mode, THEMES[DEFAULT_THEME])
    app.setStyle("Fusion")
    app.setPalette(_palette(theme))
    _apply_font(app)
    app.setStyleSheet(_qss(theme, _font_css()))
