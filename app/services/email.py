"""
Minimal SMTP email sender. In development, if SMTP isn't configured, emails
are logged instead of sent — never silently dropped, never faked as "sent".
"""
import logging
import smtplib
from email.mime.text import MIMEText

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("aiflow.email")


def send_email(to_address: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — logging email instead of sending.\nTo: %s\nSubject: %s\n%s",
                        to_address, subject, body)
        return

    message = MIMEText(body, "plain")
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_ADDRESS
    message["To"] = to_address

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_ADDRESS, [to_address], message.as_string())


def send_verification_email(to_address: str, token: str) -> None:
    link = f"{settings.PUBLIC_BASE_URL}/auth/verify-email?token={token}"
    send_email(to_address, "Verify your AI FLOW email", f"Click to verify your email:\n{link}")


def send_password_reset_email(to_address: str, token: str) -> None:
    link = f"{settings.PUBLIC_BASE_URL}/auth/reset-password?token={token}"
    send_email(to_address, "Reset your AI FLOW password", f"Click to reset your password:\n{link}\nThis link expires soon.")


def send_invitation_email(to_address: str, workspace_name: str) -> None:
    link = f"{settings.PUBLIC_BASE_URL}/register?invited=1"
    send_email(
        to_address,
        f"You've been invited to {workspace_name} on AI FLOW",
        f"You've been invited to join the \"{workspace_name}\" workspace on AI FLOW.\nSign up here:\n{link}",
    )
