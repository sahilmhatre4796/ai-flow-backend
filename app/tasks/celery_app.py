from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "aiflow",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,            # don't lose a job if a worker crashes mid-task
    worker_prefetch_multiplier=1,    # fairer distribution across workers for long-ish AI calls
    task_routes={
        "app.tasks.document_tasks.*": {"queue": "documents"},
        "app.tasks.email_tasks.*": {"queue": "emails"},
    },
)

# Registers task modules with this Celery app.
celery_app.autodiscover_tasks(["app.tasks"], related_name="document_tasks")
celery_app.autodiscover_tasks(["app.tasks"], related_name="email_tasks")
