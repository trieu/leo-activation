import os
from celery import Celery
from celery.schedules import crontab
from main_configs import CELERY_REDIS_URL

# ---------------------------------------------------------
# Celery Worker Instance
# ---------------------------------------------------------
worker = Celery(
    'leo_sync_worker',
    broker=CELERY_REDIS_URL,
    backend=CELERY_REDIS_URL,
    include=['data_workers.tasks']
)


# ---------------------------------------------------------
# Core Configuration
# ---------------------------------------------------------
worker.conf.update(
    timezone='UTC',
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
)

# ---------------------------------------------------------
# Beat Schedule
# ---------------------------------------------------------
worker.conf.beat_schedule = {
    'sync-arango-to-pg-every-15-mins': {
        'task': 'tasks.sync_profiles_task',
        'schedule': crontab(minute='*/15'),  # :00, :15, :30, :45
    },
}
