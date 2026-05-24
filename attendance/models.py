from django.db import models
from django.utils import timezone


class Employee(models.Model):
    full_name = models.CharField('ФИО', max_length=150)
    position = models.CharField('Должность', max_length=120, blank=True)
    phone = models.CharField('Телефон', max_length=50, blank=True)
    telegram_user = models.CharField('Telegram user', max_length=100, blank=True)
    work_start_time = models.TimeField('Начало работы', blank=True, null=True)
    late_grace_minutes = models.PositiveIntegerField('Допустимое опоздание, мин', blank=True, null=True)
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'

    def __str__(self):
        return self.full_name


class Device(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='devices',
        verbose_name='Сотрудник',
    )
    name = models.CharField('Название устройства', max_length=120)
    mac_address = models.CharField('MAC-адрес', max_length=17, unique=True)
    last_ip = models.GenericIPAddressField('Последний IP', blank=True, null=True)
    is_active = models.BooleanField('Активно', default=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        ordering = ['employee__full_name', 'name']
        verbose_name = 'Устройство'
        verbose_name_plural = 'Устройства'

    def save(self, *args, **kwargs):
        self.mac_address = normalize_mac(self.mac_address)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.employee} - {self.name}'


class Presence(models.Model):
    STATUS_PRESENT = 'present'
    STATUS_ABSENT = 'absent'
    STATUS_CHOICES = (
        (STATUS_PRESENT, 'На работе'),
        (STATUS_ABSENT, 'Нет на работе'),
    )

    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='presence',
        verbose_name='Сотрудник',
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name='Последнее устройство',
    )
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default=STATUS_ABSENT)
    first_seen_at = models.DateTimeField('Пришел', blank=True, null=True)
    last_seen_at = models.DateTimeField('Последний раз в сети', blank=True, null=True)
    last_left_at = models.DateTimeField('Ушел', blank=True, null=True)
    last_ip = models.GenericIPAddressField('Последний IP', blank=True, null=True)
    last_mac = models.CharField('Последний MAC', max_length=17, blank=True)
    missed_scans = models.PositiveIntegerField('Пропущенные сканы', default=0)

    class Meta:
        ordering = ['employee__full_name']
        verbose_name = 'Текущее присутствие'
        verbose_name_plural = 'Текущее присутствие'

    def __str__(self):
        return f'{self.employee}: {self.get_status_display()}'


class AttendanceEvent(models.Model):
    CHECK_IN = 'check_in'
    CHECK_OUT = 'check_out'
    EVENT_CHOICES = (
        (CHECK_IN, 'Приход'),
        (CHECK_OUT, 'Уход'),
    )

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name='Сотрудник')
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, blank=True, null=True, verbose_name='Устройство')
    event_type = models.CharField('Событие', max_length=20, choices=EVENT_CHOICES)
    observed_at = models.DateTimeField('Время события', default=timezone.now)
    ip_address = models.GenericIPAddressField('IP', blank=True, null=True)
    mac_address = models.CharField('MAC', max_length=17, blank=True)

    class Meta:
        ordering = ['-observed_at']
        verbose_name = 'Событие посещаемости'
        verbose_name_plural = 'События посещаемости'

    def __str__(self):
        return f'{self.employee} - {self.get_event_type_display()} - {self.observed_at:%Y-%m-%d %H:%M}'


class UnknownDevice(models.Model):
    ip_address = models.GenericIPAddressField('IP')
    mac_address = models.CharField('MAC', max_length=17, unique=True)
    first_seen_at = models.DateTimeField('Первый раз замечено', auto_now_add=True)
    last_seen_at = models.DateTimeField('Последний раз замечено', auto_now=True)
    note = models.CharField('Заметка', max_length=200, blank=True)

    class Meta:
        ordering = ['-last_seen_at']
        verbose_name = 'Неизвестное устройство'
        verbose_name_plural = 'Неизвестные устройства'

    def save(self, *args, **kwargs):
        self.mac_address = normalize_mac(self.mac_address)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.ip_address} - {self.mac_address}'


class LateNotification(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_RESOLVED = 'resolved'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Active'),
        (STATUS_RESOLVED, 'Resolved'),
    )

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name='Сотрудник')
    alert_date = models.DateField('Date')
    chat_id = models.CharField('Telegram chat id', max_length=64)
    message_id = models.PositiveIntegerField('Telegram message id', blank=True, null=True)
    alert_count = models.PositiveIntegerField('Alert count', default=0)
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    last_alert_at = models.DateTimeField('Last alert', blank=True, null=True)
    resolved_at = models.DateTimeField('Resolved at', blank=True, null=True)
    created_at = models.DateTimeField('Created', auto_now_add=True)
    updated_at = models.DateTimeField('Updated', auto_now=True)

    class Meta:
        ordering = ['-alert_date', 'employee__full_name']
        unique_together = ('employee', 'alert_date', 'chat_id')
        verbose_name = 'Telegram late notification'
        verbose_name_plural = 'Telegram late notifications'

    def __str__(self):
        return f'{self.employee} - {self.alert_date} - {self.status}'


class DailyAttendanceReport(models.Model):
    report_date = models.DateField('Date')
    chat_id = models.CharField('Telegram chat id', max_length=64)
    message_id = models.PositiveIntegerField('Telegram message id', blank=True, null=True)
    content = models.TextField('Last message content', blank=True)
    sent_at = models.DateTimeField('Sent at', blank=True, null=True)
    updated_at = models.DateTimeField('Updated', auto_now=True)

    class Meta:
        ordering = ['-report_date']
        unique_together = ('report_date', 'chat_id')
        verbose_name = 'Telegram daily attendance report'
        verbose_name_plural = 'Telegram daily attendance reports'

    def __str__(self):
        return f'{self.report_date} - {self.chat_id}'


def normalize_mac(value):
    cleaned = value.strip().lower().replace('-', ':')
    parts = cleaned.split(':')
    if len(parts) == 6:
        return ':'.join(part.zfill(2) for part in parts)
    return cleaned
