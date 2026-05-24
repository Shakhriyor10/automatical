from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0007_optional_employee_schedule'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyAttendanceReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_date', models.DateField(verbose_name='Date')),
                ('chat_id', models.CharField(max_length=64, verbose_name='Telegram chat id')),
                ('message_id', models.PositiveIntegerField(blank=True, null=True, verbose_name='Telegram message id')),
                ('content', models.TextField(blank=True, verbose_name='Last message content')),
                ('sent_at', models.DateTimeField(blank=True, null=True, verbose_name='Sent at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated')),
            ],
            options={
                'verbose_name': 'Telegram daily attendance report',
                'verbose_name_plural': 'Telegram daily attendance reports',
                'ordering': ['-report_date'],
                'unique_together': {('report_date', 'chat_id')},
            },
        ),
    ]
