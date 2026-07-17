from app.services.email import send_invitation_email, send_password_reset_email, send_verification_email
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.email_tasks.send_verification_email_task")
def send_verification_email_task(to_address: str, token: str) -> None:
    send_verification_email(to_address, token)


@celery_app.task(name="app.tasks.email_tasks.send_password_reset_email_task")
def send_password_reset_email_task(to_address: str, token: str) -> None:
    send_password_reset_email(to_address, token)


@celery_app.task(name="app.tasks.email_tasks.send_invitation_email_task")
def send_invitation_email_task(to_address: str, workspace_name: str) -> None:
    send_invitation_email(to_address, workspace_name)
