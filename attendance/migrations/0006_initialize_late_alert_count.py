from django.db import migrations


def initialize_alert_count(apps, schema_editor):
    LateNotification = apps.get_model('attendance', 'LateNotification')
    LateNotification.objects.filter(message_id__isnull=False, alert_count=0).update(alert_count=1)


def reverse_initialize_alert_count(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0005_latenotification_alert_count'),
    ]

    operations = [
        migrations.RunPython(initialize_alert_count, reverse_initialize_alert_count),
    ]
