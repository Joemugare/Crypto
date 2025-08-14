import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crypto_tracker.settings')
app = Celery('crypto_tracker')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()