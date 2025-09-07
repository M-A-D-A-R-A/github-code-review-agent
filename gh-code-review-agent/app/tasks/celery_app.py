import os
from celery import Celery
from ..config import get_settings


celery = Celery(
    get_settings().APP_NAME,
    broker=get_settings().CELERY_BROKER_URL,
    backend=get_settings().CELERY_RESULT_BACKEND,
)


# Sensible defaults
celery.conf.update(
    task_track_started=True,
    result_expires=60 * 60 * 6, # 6 hours
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    worker_send_task_events=True,
    task_send_sent_event=True,
    imports=("app.tasks.task",)
)