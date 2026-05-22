from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0006_initialize_late_alert_count'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='late_grace_minutes',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Допустимое опоздание, мин'),
        ),
        migrations.AlterField(
            model_name='employee',
            name='work_start_time',
            field=models.TimeField(blank=True, null=True, verbose_name='Начало работы'),
        ),
    ]
