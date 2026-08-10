from email.message import EmailMessage
import logging
import smtplib
import ssl

from app.config import Settings


SMTP_TIMEOUT_SECONDS = 10
logger = logging.getLogger("applylens.email")


class PasswordResetEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, recipient: str, reset_url: str) -> None:
        if self.settings.email_delivery == "console":
            logger.warning(
                "Development-only password reset link: %s",
                reset_url,
            )
            return

        message = EmailMessage()
        message["Subject"] = "Reset your ApplyLens AI password"
        message["From"] = str(self.settings.smtp_from_email)
        message["To"] = recipient
        message.set_content(
            "Use this link to reset your ApplyLens AI password:\n\n"
            f"{reset_url}\n\n"
            "This link expires in one hour and can be used only once. "
            "If you did not request it, you can ignore this email."
        )

        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            smtp.ehlo()
            if self.settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(
                self.settings.smtp_username,
                self.settings.smtp_password.get_secret_value(),
            )
            smtp.send_message(message)
