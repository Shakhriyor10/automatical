from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0002_presence_missed_scans'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='late_grace_minutes',
            field=models.PositiveIntegerField(default=0, verbose_name='Допустимое опоздание, мин'),
        ),
        migrations.AddField(
            model_name='employee',
            name='work_start_time',
            field=models.TimeField(default='09:00', verbose_name='Начало работы'),
        ),
    ]
