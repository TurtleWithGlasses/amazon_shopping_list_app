"""Settings: change account credentials and export data."""
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.cloud import auth
from services import export as export_service
from services.timescales import DEFAULT_TIMESCALE, TIMESCALE_LABELS


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)

        layout.addWidget(self._build_account_group())
        layout.addWidget(self._build_export_group())

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    # --- account -----------------------------------------------------------

    def _build_account_group(self) -> QGroupBox:
        box = QGroupBox("Account")
        form = QFormLayout(box)

        self.first_edit = QLineEdit(auth.current_first_name())
        self.last_edit = QLineEdit(auth.current_last_name())
        save_name = QPushButton("Save name")
        save_name.clicked.connect(self._save_name)
        form.addRow("First name:", self.first_edit)
        form.addRow("Last name:", self.last_edit)
        form.addRow("", save_name)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("New password (min 6 characters)")
        change_pw = QPushButton("Change password")
        change_pw.clicked.connect(self._change_password)
        form.addRow("Password:", self.password_edit)
        form.addRow("", change_pw)

        self.email_edit = QLineEdit(auth.current_email() or "")
        change_email = QPushButton("Change email")
        change_email.clicked.connect(self._change_email)
        form.addRow("Email:", self.email_edit)
        form.addRow("", change_email)

        return box

    def _save_name(self) -> None:
        try:
            auth.update_profile(self.first_edit.text().strip(), self.last_edit.text().strip())
        except Exception as exc:
            QMessageBox.warning(self, "Update failed", str(exc))
            return
        QMessageBox.information(self, "Saved", "Your name was updated.")

    def _change_password(self) -> None:
        password = self.password_edit.text()
        if len(password) < 6:
            QMessageBox.warning(self, "Password", "Password must be at least 6 characters.")
            return
        try:
            auth.update_password(password)
        except Exception as exc:
            QMessageBox.warning(self, "Update failed", str(exc))
            return
        self.password_edit.clear()
        QMessageBox.information(self, "Password changed", "Your password was updated.")

    def _change_email(self) -> None:
        new_email = self.email_edit.text().strip()
        if not new_email:
            return
        try:
            auth.update_email(new_email)
        except Exception as exc:
            QMessageBox.warning(self, "Update failed", str(exc))
            return
        QMessageBox.information(
            self, "Confirm email",
            "A confirmation link was sent to the new address. "
            "The change takes effect once you confirm it.",
        )

    # --- export ------------------------------------------------------------

    def _build_export_group(self) -> QGroupBox:
        box = QGroupBox("Export data")
        outer = QVBoxLayout(box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Timescale:"))
        self.timescale = QComboBox()
        self.timescale.addItems(TIMESCALE_LABELS)
        self.timescale.setCurrentText(DEFAULT_TIMESCALE)
        row.addWidget(self.timescale)
        row.addStretch(1)
        outer.addLayout(row)

        buttons = QHBoxLayout()
        csv_button = QPushButton("Export CSV…")
        csv_button.clicked.connect(lambda: self._export("csv"))
        xlsx_button = QPushButton("Export Excel…")
        xlsx_button.clicked.connect(lambda: self._export("xlsx"))
        buttons.addWidget(csv_button)
        buttons.addWidget(xlsx_button)
        outer.addLayout(buttons)
        return box

    def _export(self, fmt: str) -> None:
        if fmt == "xlsx":
            file_filter, default = "Excel files (*.xlsx)", "price_history.xlsx"
        else:
            file_filter, default = "CSV files (*.csv)", "price_history.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save export", default, file_filter)
        if not path:
            return
        try:
            rows = export_service.export_to_file(path, self.timescale.currentText())
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Exported", f"Exported {rows} row(s) to {path}")
