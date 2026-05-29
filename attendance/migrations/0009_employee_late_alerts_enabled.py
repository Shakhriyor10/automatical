from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0008_daily_attendance_report'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='late_alerts_enabled',
            field=models.BooleanField(default=True, verbose_name='Предупреждать об опоздании'),
        ),
    ]
