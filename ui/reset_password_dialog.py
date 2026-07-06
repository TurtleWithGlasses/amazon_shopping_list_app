"""Forgot / reset password flow (Phase 42) — fully in-app, no hosted page.

Two steps in one dialog:
  1. Request — enter the email; Supabase emails a 6-digit recovery code.
  2. Reset   — enter the code + a new password; verify the code (which opens a
               short recovery session) and set the new password.

The 'Reset Password' email template must include `{{ .Token }}` so the code is
delivered. Shows a neutral confirmation regardless of whether the address exists.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.cloud import auth

_MIN_PASSWORD = 6


class ResetPasswordDialog(QDialog):
    def __init__(self, email: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reset password")
        self.setMinimumWidth(420)
        self._email = email

        layout = QVBoxLayout(self)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_request_page(email))
        self.pages.addWidget(self._build_reset_page())
        layout.addWidget(self.pages)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

    # --- step 1: request a code -------------------------------------------

    def _build_request_page(self, email: str) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        intro = QLabel(
            "Enter your account email. We'll send you a code to reset your "
            "password."
        )
        intro.setWordWrap(True)
        v.addWidget(intro)

        form = QFormLayout()
        self.email_edit = QLineEdit(email)
        self.email_edit.setPlaceholderText("you@example.com")
        form.addRow("Email:", self.email_edit)
        v.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.send_button = QPushButton("Send code")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self._send_code)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.send_button)
        v.addLayout(buttons)
        self.email_edit.returnPressed.connect(self._send_code)
        return page

    def _send_code(self) -> None:
        email = self.email_edit.text().strip()
        if not email:
            self.status.setText("Enter your email.")
            return
        self.send_button.setEnabled(False)
        self.status.setText("Sending…")
        try:
            auth.send_password_reset(email)
        except Exception as exc:
            self.status.setText(self._friendly_error(exc))
            self.send_button.setEnabled(True)
            return
        self._email = email
        QMessageBox.information(
            self, "Check your email",
            f"If an account exists for {email}, a 6-digit reset code is on its "
            "way. Enter it on the next screen.",
        )
        self.status.setText("")
        self.pages.setCurrentIndex(1)

    # --- step 2: verify + set new password --------------------------------

    def _build_reset_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel("Enter the code from the email and choose a new password."))
        form = QFormLayout()
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("code from the email")
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_edit.setPlaceholderText("new password")
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText("confirm new password")
        form.addRow("Code:", self.code_edit)
        form.addRow("New password:", self.new_password_edit)
        form.addRow("Confirm:", self.confirm_edit)
        v.addLayout(form)

        buttons = QHBoxLayout()
        self.resend_button = QPushButton("Resend code")
        self.resend_button.clicked.connect(self._send_code)
        buttons.addWidget(self.resend_button)
        buttons.addStretch(1)
        self.reset_button = QPushButton("Reset password")
        self.reset_button.setObjectName("primary")
        self.reset_button.clicked.connect(self._reset)
        buttons.addWidget(self.reset_button)
        v.addLayout(buttons)
        self.confirm_edit.returnPressed.connect(self._reset)
        return page

    def _reset(self) -> None:
        code = "".join(self.code_edit.text().split())  # drop any stray spaces
        new_password = self.new_password_edit.text()
        confirm = self.confirm_edit.text()
        if not code:
            self.status.setText("Enter the code from the email.")
            return
        if len(new_password) < _MIN_PASSWORD:
            self.status.setText(f"Password must be at least {_MIN_PASSWORD} characters.")
            return
        if new_password != confirm:
            self.status.setText("The passwords don't match.")
            return
        self.reset_button.setEnabled(False)
        self.status.setText("Resetting…")
        try:
            auth.verify_recovery_otp(self._email, code)
            auth.update_password(new_password)
        except Exception as exc:
            self.reset_button.setEnabled(True)
            self.status.setText(self._friendly_error(exc))
            return
        QMessageBox.information(
            self, "Password changed",
            "Your password has been reset. You can now sign in with it.",
        )
        self.accept()

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc).strip()
        low = text.lower()
        if "expired" in low or "invalid" in low or "otp" in low or "token" in low:
            return ("That code didn't work — codes expire and each new email "
                    "replaces the previous one. Open the newest email and enter "
                    "that code, or click \"Resend code\" and use the new one.")
        if "rate" in low or "limit" in low or "seconds" in low:
            return "Too many attempts. Please wait a minute and try again."
        return text or "Couldn't reset the password. Please try again."
