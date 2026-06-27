"""Small modal dialog for editing a product's name, URL, and target price."""
import re
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)


class EditProductDialog(QDialog):
    def __init__(self, name: str, url: str, target_price: Optional[float] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit product")
        self.setMinimumWidth = 480

        layout = QFormLayout(self)
        self.name_edit = QLineEdit(name or "")
        self.url_edit = QLineEdit(url or "")
        self.name_edit.setMinimumWidth(420)
        self.target_edit = QLineEdit("" if target_price is None else f"{target_price:g}")
        self.target_edit.setPlaceholderText("e.g. 14999 — alert when price drops to/below this; empty = off")
        layout.addRow("Name:", self.name_edit)
        layout.addRow("URL:", self.url_edit)
        layout.addRow("Target price:", self.target_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @staticmethod
    def _parse_target(text: str) -> Optional[float]:
        """Parse a user-entered amount (handles '15000', '14999,50', '14.999,50')."""
        s = re.sub(r"[^\d.,]", "", text or "")
        if not s:
            return None
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        elif "." in s and len(s.rsplit(".", 1)[-1]) == 3:
            s = s.replace(".", "")  # lone dot with a 3-digit tail = thousands (12.500 → 12500)
        try:
            return float(s)
        except ValueError:
            return None

    def values(self) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        name = self.name_edit.text().strip() or None
        url = self.url_edit.text().strip() or None
        target = self._parse_target(self.target_edit.text())
        return name, url, target
