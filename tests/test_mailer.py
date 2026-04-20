from unittest.mock import MagicMock, patch

from src.mailer import send_mail


def test_send_mail_calls_smtp_ssl():
    with patch("src.mailer.smtplib.SMTP_SSL") as smtp_cls:
        smtp_obj = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp_obj
        send_mail(
            host="smtp.gmail.com", port=465,
            username="u@x", password="p",
            sender="u@x", recipient="to@x",
            subject="s", html="<b>h</b>", text="h",
        )
    smtp_obj.login.assert_called_once_with("u@x", "p")
    args, _ = smtp_obj.send_message.call_args
    msg = args[0]
    assert msg["Subject"] == "s"
    assert msg["From"] == "u@x"
    assert msg["To"] == "to@x"
