"""
Enregistre la tâche périodique `dispatch_stock_alerts` dans Celery Beat.
Planifiée chaque jour à 08h00 (heure de Douala, Africa/Douala).
"""
from django.db import migrations


def register_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Déclenche toutes les heures — le dispatcher filtre selon le send_time de chaque tenant.
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "Africa/Douala"},
    )

    PeriodicTask.objects.update_or_create(
        name="Alertes stock WhatsApp — dispatch horaire",
        defaults={
            "task": "notifications.tasks.dispatch_stock_alerts",
            "crontab": schedule,
            "enabled": True,
        },
    )


def deregister_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="Alertes stock WhatsApp — dispatch horaire").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(register_task, deregister_task),
    ]
