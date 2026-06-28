import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kenpro_store.settings")

app = Celery("kenpro_store")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
