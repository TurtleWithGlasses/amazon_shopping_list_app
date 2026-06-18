"""Small modal dialog for editing a product's name and URL."""
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)


class EditProductDialog(QDialog):
    def __init__(self, name: str, url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit product")
        self.setMinimumWidth = 480

        layout = QFormLayout(self)
        self.name_edit = QLineEdit(name or "")
        self.url_edit = QLineEdit(url or "")
        self.name_edit.setMinimumWidth(420)
        layout.addRow("Name:", self.name_edit)
        layout.addRow("URL:", self.url_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> Tuple[Optional[str], Optional[str]]:
        name = self.name_edit.text().strip() or None
        url = self.url_edit.text().strip() or None
        return name, url
