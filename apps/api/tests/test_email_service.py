import logging

from app.config import Settings
from app.services.email_service import PasswordResetEmailSender, SMTP_TIMEOUT_SECONDS


def test_console_delivery_is_explicitly_development_only(caplog) -> None:
    sender = PasswordResetEmailSender(Settings(_env_file=None))

    with caplog.at_level(logging.WARNING, logger="applylens.email"):
        sender.send(
            "candidate@example.com",
            "http://localhost:5173/?reset_token=development-token",
        )

    assert "Development-only password reset link" in caplog.text
    assert "development-token" in caplog.text


def test_smtp_delivery_uses_tls_authentication_and_expected_message(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeSmtp:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            captured.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def ehlo(self) -> None:
            captured["ehlo_count"] = int(captured.get("ehlo_count", 0)) + 1

        def starttls(self, *, context) -> None:
            captured["tls_context"] = context

        def login(self, username: str, password: str) -> None:
            captured.update(username=username, password=password)

        def send_message(self, message) -> None:
            captured["message"] = message

    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", FakeSmtp)
    settings = Settings(
        _env_file=None,
        email_delivery="smtp",
        smtp_host="smtp.example.com",
        smtp_port=2525,
        smtp_username="applylens",
        smtp_password="secret-password",
        smtp_from_email="support@example.com",
    )

    PasswordResetEmailSender(settings).send(
        "candidate@example.com",
        "https://app.example.com/?reset_token=one-time-token",
    )

    assert captured["host"] == "smtp.example.com"
    assert captured["port"] == 2525
    assert captured["timeout"] == SMTP_TIMEOUT_SECONDS
    assert captured["ehlo_count"] == 2
    assert captured["username"] == "applylens"
    assert captured["password"] == "secret-password"
    message = captured["message"]
    assert message["From"] == "support@example.com"
    assert message["To"] == "candidate@example.com"
    assert "one-time-token" in message.get_content()
