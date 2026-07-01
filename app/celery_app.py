"""
Configurazione Celery — usa Redis (fornito da Railway) come broker e backend risultati.
"""
import os
from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "arflow_backend",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Rome",
    enable_utc=True,
    task_track_started=True,
    # Conversioni CAD possono richiedere minuti — timeout generoso
    task_time_limit=600,       # 10 minuti hard limit
    task_soft_time_limit=540,  # 9 minuti soft limit (permette cleanup)
)
