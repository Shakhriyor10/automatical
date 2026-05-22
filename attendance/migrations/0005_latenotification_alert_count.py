from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0004_telegram_alerts'),
    ]

    operations = [
        migrations.AddField(
            model_name='latenotification',
            name='alert_count',
            field=models.PositiveIntegerField(default=0, verbose_name='Alert count'),
        ),
    ]
