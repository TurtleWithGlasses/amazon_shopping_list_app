"""Settings: change account credentials and export data."""
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFontDialog,
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
from ui.theme import DEFAULT_THEME, THEME_CHOICES, apply_theme, user_font_size


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)

        layout.addWidget(self._build_appearance_group())
        layout.addWidget(self._build_account_group())
        layout.addWidget(self._build_export_group())

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    # --- appearance --------------------------------------------------------

    def _build_appearance_group(self) -> QGroupBox:
        box = QGroupBox("Appearance")
        outer = QVBoxLayout(box)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        for key, label in THEME_CHOICES:
            self.theme_combo.addItem(label, key)
        current = QSettings().value("theme", DEFAULT_THEME)
        index = self.theme_combo.findData(current)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.currentIndexChanged.connect(self._change_theme)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        outer.addLayout(theme_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("Font:"))
        self.font_label = QLabel(self._current_font_text())
        font_row.addWidget(self.font_label)
        font_row.addStretch(1)
        choose = QPushButton("Choose font…")
        choose.clicked.connect(self._choose_font)
        reset = QPushButton("Default")
        reset.clicked.connect(self._reset_font)
        font_row.addWidget(choose)
        font_row.addWidget(reset)
        outer.addLayout(font_row)
        return box

    def _change_theme(self) -> None:
        mode = self.theme_combo.currentData()
        QSettings().setValue("theme", mode)
        apply_theme(QApplication.instance(), mode)  # live, no restart needed

    # --- font --------------------------------------------------------------

    def _current_font_text(self) -> str:
        family = QSettings().value("font_family")
        if family:
            return f"{family}  ({user_font_size()} pt)"
        return "Orbitron (default)"

    def _choose_font(self) -> None:
        settings = QSettings()
        current = QFont(settings.value("font_family") or "Orbitron", user_font_size())
        result = QFontDialog.getFont(current, self, "Choose font")
        # PySide6 returns (font, ok) — handle either order defensively.
        font = next((x for x in result if isinstance(x, QFont)), None)
        ok = next((x for x in result if isinstance(x, bool)), False)
        if not ok or font is None:
            return
        settings.setValue("font_family", font.family())
        settings.setValue("font_size", font.pointSize() if font.pointSize() > 0 else 10)
        apply_theme(QApplication.instance(), settings.value("theme", DEFAULT_THEME))
        self.font_label.setText(self._current_font_text())

    def _reset_font(self) -> None:
        settings = QSettings()
        settings.remove("font_family")
        settings.remove("font_size")
        apply_theme(QApplication.instance(), settings.value("theme", DEFAULT_THEME))
        self.font_label.setText(self._current_font_text())

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
