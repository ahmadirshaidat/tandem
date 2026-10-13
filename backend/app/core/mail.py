import os
import smtplib
import ssl
import uuid
from email.message import EmailMessage

from app.core.config import settings


def send_reset(email: str, url: str):
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = email
    message["Subject"] = "Reset your Tandem password"
    message.set_content(
        f"Reset your password: {url}\n\nThis link expires in 30 minutes and works once."
    )
    if settings.mail_mode == "smtp":
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(message)
    else:
        settings.mail_outbox.mkdir(parents=True, exist_ok=True, mode=0o700)
        file = settings.mail_outbox / f"{uuid.uuid4()}.eml"
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(message.as_string())
