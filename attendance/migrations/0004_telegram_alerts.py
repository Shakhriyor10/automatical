from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0003_employee_schedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='telegram_user',
            field=models.CharField(blank=True, max_length=100, verbose_name='Telegram user'),
        ),
        migrations.CreateModel(
            name='LateNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alert_date', models.DateField(verbose_name='Date')),
                ('chat_id', models.CharField(max_length=64, verbose_name='Telegram chat id')),
                ('message_id', models.PositiveIntegerField(blank=True, null=True, verbose_name='Telegram message id')),
                ('status', models.CharField(choices=[('active', 'Active'), ('resolved', 'Resolved')], default='active', max_length=20, verbose_name='Status')),
                ('last_alert_at', models.DateTimeField(blank=True, null=True, verbose_name='Last alert')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='Resolved at')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='attendance.employee', verbose_name='Сотрудник')),
            ],
            options={
                'verbose_name': 'Telegram late notification',
                'verbose_name_plural': 'Telegram late notifications',
                'ordering': ['-alert_date', 'employee__full_name'],
                'unique_together': {('employee', 'alert_date', 'chat_id')},
            },
        ),
    ]
