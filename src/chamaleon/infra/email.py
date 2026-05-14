from __future__ import annotations

import smtplib
from email.message import EmailMessage

from chamaleon.config import Settings


class EmailDeliveryError(RuntimeError):
    pass


class EmailClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send_report(self, recipient: str, subject: str, content: str) -> None:
        if not self.settings.smtp_host or not self.settings.email_from:
            raise EmailDeliveryError("SMTP_HOST e EMAIL_FROM precisam estar configurados para enviar relatorios")

        message = EmailMessage()
        message["From"] = self.settings.email_from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(content)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_username and self.settings.smtp_password:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)
