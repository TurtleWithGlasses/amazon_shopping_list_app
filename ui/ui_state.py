"""Remember UI choices between sessions (window sizes, column widths, splitter
positions, dropdown selections) in QSettings.

Each piece of state lives under its own key, e.g. "group_view/geometry". Restores
are best-effort: a missing or stale value (e.g. a table that gained a column)
just leaves the widget at its default.
"""
from PySide6.QtCore import QSettings


def value(key: str, default=None):
    return QSettings().value(key, default)


def set_value(key: str, val) -> None:
    QSettings().setValue(key, val)


# --- windows ---------------------------------------------------------------

def restore_geometry(window, key: str) -> bool:
    """Restore a window's saved size/position; False if none was saved."""
    geometry = QSettings().value(f"{key}/geometry")
    return geometry is not None and window.restoreGeometry(geometry)


def save_geometry(window, key: str) -> None:
    QSettings().setValue(f"{key}/geometry", window.saveGeometry())


# --- table headers (column widths / order) -----------------------------------

def remember_header(header, key: str) -> None:
    """Restore a header's saved column widths/order, then save on every change.
    Safe to call again on a rebuilt table (the group view rebuilds its table)."""
    state = QSettings().value(f"{key}/header")
    if state is not None:
        header.restoreState(state)

    def save(*_args):
        QSettings().setValue(f"{key}/header", header.saveState())

    header.sectionResized.connect(save)
    header.sectionMoved.connect(save)


# --- splitters ------------------------------------------------------------

def remember_splitter(splitter, key: str) -> None:
    """Restore a splitter's saved sizes, then save whenever the user drags it."""
    state = QSettings().value(f"{key}/splitter")
    if state is not None:
        splitter.restoreState(state)
    splitter.splitterMoved.connect(
        lambda *_: QSettings().setValue(f"{key}/splitter", splitter.saveState())
    )


# --- combo boxes ---------------------------------------------------------------

def remember_combo_text(combo, key: str, default: str) -> None:
    """Select the saved option (if it still exists, else `default`) and save
    whenever the selection changes. Call after the items are added and before
    connecting handlers that should only react to user changes."""
    saved = QSettings().value(key, default)
    if combo.findText(saved) < 0:
        saved = default
    combo.setCurrentText(saved)
    combo.currentTextChanged.connect(lambda text: QSettings().setValue(key, text))
