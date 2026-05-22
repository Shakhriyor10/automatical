from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=150, verbose_name='ФИО')),
                ('position', models.CharField(blank=True, max_length=120, verbose_name='Должность')),
                ('phone', models.CharField(blank=True, max_length=50, verbose_name='Телефон')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
            ],
            options={
                'verbose_name': 'Сотрудник',
                'verbose_name_plural': 'Сотрудники',
                'ordering': ['full_name'],
            },
        ),
        migrations.CreateModel(
            name='UnknownDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(verbose_name='IP')),
                ('mac_address', models.CharField(max_length=17, unique=True, verbose_name='MAC')),
                ('first_seen_at', models.DateTimeField(auto_now_add=True, verbose_name='Первый раз замечено')),
                ('last_seen_at', models.DateTimeField(auto_now=True, verbose_name='Последний раз замечено')),
                ('note', models.CharField(blank=True, max_length=200, verbose_name='Заметка')),
            ],
            options={
                'verbose_name': 'Неизвестное устройство',
                'verbose_name_plural': 'Неизвестные устройства',
                'ordering': ['-last_seen_at'],
            },
        ),
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Название устройства')),
                ('mac_address', models.CharField(max_length=17, unique=True, verbose_name='MAC-адрес')),
                ('last_ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='Последний IP')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активно')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='devices', to='attendance.employee', verbose_name='Сотрудник')),
            ],
            options={
                'verbose_name': 'Устройство',
                'verbose_name_plural': 'Устройства',
                'ordering': ['employee__full_name', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Presence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('present', 'На работе'), ('absent', 'Нет на работе')], default='absent', max_length=20, verbose_name='Статус')),
                ('first_seen_at', models.DateTimeField(blank=True, null=True, verbose_name='Пришел')),
                ('last_seen_at', models.DateTimeField(blank=True, null=True, verbose_name='Последний раз в сети')),
                ('last_left_at', models.DateTimeField(blank=True, null=True, verbose_name='Ушел')),
                ('last_ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='Последний IP')),
                ('last_mac', models.CharField(blank=True, max_length=17, verbose_name='Последний MAC')),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='attendance.device', verbose_name='Последнее устройство')),
                ('employee', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='presence', to='attendance.employee', verbose_name='Сотрудник')),
            ],
            options={
                'verbose_name': 'Текущее присутствие',
                'verbose_name_plural': 'Текущее присутствие',
                'ordering': ['employee__full_name'],
            },
        ),
        migrations.CreateModel(
            name='AttendanceEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('check_in', 'Приход'), ('check_out', 'Уход')], max_length=20, verbose_name='Событие')),
                ('observed_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Время события')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP')),
                ('mac_address', models.CharField(blank=True, max_length=17, verbose_name='MAC')),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='attendance.device', verbose_name='Устройство')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='attendance.employee', verbose_name='Сотрудник')),
            ],
            options={
                'verbose_name': 'Событие посещаемости',
                'verbose_name_plural': 'События посещаемости',
                'ordering': ['-observed_at'],
            },
        ),
    ]
