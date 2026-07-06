"""Login / register dialog backed by Supabase Auth."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.cloud import auth, session_store


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Price Tracker — Sign in")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.first_name_edit = QLineEdit()
        self.first_name_edit.setPlaceholderText("First name (for registration)")
        self.last_name_edit = QLineEdit()
        self.last_name_edit.setPlaceholderText("Last name (for registration)")
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("you@example.com")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("password")
        form.addRow("First name:", self.first_name_edit)
        form.addRow("Last name:", self.last_name_edit)
        form.addRow("Email:", self.email_edit)
        form.addRow("Password:", self.password_edit)
        layout.addLayout(form)

        self.remember_checkbox = QCheckBox("Remember me")
        self.remember_checkbox.setToolTip(
            "Stay signed in on this computer (stores a secure token, not your password)."
        )
        layout.addWidget(self.remember_checkbox)

        # Prefill the last email and tick "remember" if a session is saved.
        saved_email = session_store.load_email()
        if saved_email:
            self.email_edit.setText(saved_email)
        self.remember_checkbox.setChecked(session_store.has_saved_session())

        # Log in / Register / Forgot password on one row, evenly sized.
        buttons = QHBoxLayout()
        self.login_button = QPushButton("Log in")
        self.register_button = QPushButton("Register")
        self.forgot_button = QPushButton("Forgot password?")
        self.forgot_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.clicked.connect(self._login)
        self.register_button.clicked.connect(self._register)
        self.forgot_button.clicked.connect(self._forgot_password)
        for button in (self.login_button, self.register_button, self.forgot_button):
            buttons.addWidget(button, 1)  # equal stretch so they align on one row
        layout.addLayout(buttons)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.password_edit.returnPressed.connect(self._login)

    def _credentials(self):
        return self.email_edit.text().strip(), self.password_edit.text()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.login_button.setEnabled(not busy)
        self.register_button.setEnabled(not busy)
        self.status.setText(message)

    def _login(self) -> None:
        email, password = self._credentials()
        if not email or not password:
            self.status.setText("Enter your email and password.")
            return
        self._set_busy(True, "Signing in…")
        try:
            auth.sign_in(email, password)
        except Exception as exc:
            self._set_busy(False, "")
            QMessageBox.warning(self, "Sign in failed", self._friendly_error(exc))
            return
        if self.remember_checkbox.isChecked():
            session_store.save_session(auth.current_refresh_token(), email)
        else:
            session_store.clear_session()
        self.accept()

    def _register(self) -> None:
        email, password = self._credentials()
        first = self.first_name_edit.text().strip()
        last = self.last_name_edit.text().strip()
        if not email or not password:
            self.status.setText("Enter an email and password to register.")
            return
        if not first or not last:
            self.status.setText("Enter your first and last name to register.")
            return
        if len(password) < 6:
            self.status.setText("Password must be at least 6 characters.")
            return
        self._set_busy(True, "Creating account…")
        try:
            auth.sign_up(email, password, first_name=first, last_name=last)
        except Exception as exc:
            self._set_busy(False, "")
            QMessageBox.warning(self, "Registration failed", self._friendly_error(exc))
            return
        self._set_busy(False, "")
        QMessageBox.information(
            self,
            "Confirm your email",
            "Account created. Check your inbox for a confirmation link, then log in.",
        )

    def _forgot_password(self) -> None:
        from ui.reset_password_dialog import ResetPasswordDialog
        ResetPasswordDialog(self.email_edit.text().strip(), parent=self).exec()

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc).lower()
        if "not confirmed" in text or "confirm" in text:
            return "Your email isn't confirmed yet. Click the link we emailed you, then log in."
        if "invalid" in text and "credential" in text:
            return "Incorrect email or password."
        return str(exc)
