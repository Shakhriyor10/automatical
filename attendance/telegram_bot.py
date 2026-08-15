import html
from threading import Lock
from dataclasses import dataclass
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management import call_command
from django.db.models import Prefetch
from django.utils import timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from .models import AttendanceEvent, DailyAttendanceReport, Employee, EmployeeDayOff, LateNotification, Presence


router = Router()

DATE_FORMAT = '%Y-%m-%d'
MAX_MESSAGE_LENGTH = 3900
MAX_LATE_WARNINGS_PER_DAY = 1
_scan_lock = Lock()


@dataclass
class EmployeeDayRow:
    employee_id: int
    name: str
    position: str
    scheduled_start: str
    first_in: str
    last_out: str
    lateness: str
    has_arrived_today: bool
    is_late: bool
    is_present: bool
    check_in_count: int
    check_out_count: int
    is_day_off: bool


def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Сегодня'), KeyboardButton(text='Сейчас на работе')],
            [KeyboardButton(text='Кого нет'), KeyboardButton(text='Сканировать')],
            [KeyboardButton(text='Дата /date'), KeyboardButton(text='Админ')],
        ],
        resize_keyboard=True,
        input_field_placeholder='Выберите действие',
    )


def report_keyboard(selected_date):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='Вчера', callback_data=f'day:{selected_date - timedelta(days=1)}'),
                InlineKeyboardButton(text='Сегодня', callback_data=f'day:{timezone.localdate()}'),
                InlineKeyboardButton(text='Завтра', callback_data=f'day:{selected_date + timedelta(days=1)}'),
            ],
            [
                InlineKeyboardButton(text='Сейчас на работе', callback_data='present'),
                InlineKeyboardButton(text='Кого нет', callback_data='absent'),
            ],
            [InlineKeyboardButton(text='Сканировать Wi-Fi', callback_data='scan')],
        ]
    )


def _is_allowed(user_id, allowed_user_ids):
    return not allowed_user_ids or user_id in allowed_user_ids


def _is_admin(user_id, admin_user_ids):
    return user_id in admin_user_ids


async def _guard_message(message, allowed_user_ids):
    if _is_allowed(message.from_user.id, allowed_user_ids):
        return True
    await message.answer('У вас нет доступа к этому боту.')
    return False


async def _guard_callback(callback, allowed_user_ids):
    if _is_allowed(callback.from_user.id, allowed_user_ids):
        return True
    await callback.answer('Нет доступа', show_alert=True)
    return False


async def _guard_admin_message(message, allowed_user_ids, admin_user_ids):
    if not await _guard_message(message, allowed_user_ids):
        return False
    if _is_admin(message.from_user.id, admin_user_ids):
        return True
    await message.answer('Эта настройка доступна только админу бота.')
    return False


async def _guard_admin_callback(callback, allowed_user_ids, admin_user_ids):
    if not await _guard_callback(callback, allowed_user_ids):
        return False
    if _is_admin(callback.from_user.id, admin_user_ids):
        return True
    await callback.answer('Только для админа бота', show_alert=True)
    return False


@router.message(CommandStart())
async def start(message: Message, allowed_user_ids: set[int]):
    if not await _guard_message(message, allowed_user_ids):
        return
    text = (
        '<b>Автосалон: учет сотрудников</b>\n\n'
        'Я показываю, кто сегодня пришел, кого нет, во сколько был первый приход, '
        'последний уход и опоздание.\n\n'
        'Команды:\n'
        '/today - отчет за сегодня\n'
        '/present - кто сейчас на работе\n'
        '/absent - кого сейчас нет\n'
        '/date 2026-05-21 - отчет за дату\n'
        '/scan - запустить сканирование Wi-Fi\n'
        '/admin - график и выходные сотрудников'
    )
    await message.answer(text, reply_markup=main_keyboard())


@router.message(Command('admin'))
@router.message(F.text.casefold() == 'админ')
async def admin_panel(message: Message, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_message(message, allowed_user_ids, admin_user_ids):
        return
    text, keyboard = await sync_to_async(build_admin_home)()
    await message.answer(text, reply_markup=keyboard)


@router.message(Command('setstart'))
async def admin_set_start(message: Message, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_message(message, allowed_user_ids, admin_user_ids):
        return
    parts = (message.text or '').split()
    if len(parts) != 3:
        await message.answer('Формат: <code>/setstart ID HH:MM</code>\nНапример: <code>/setstart 3 09:30</code>')
        return
    try:
        employee_id = int(parts[1])
        start_time = datetime.strptime(parts[2], '%H:%M').time()
    except ValueError:
        await message.answer('Нужно так: <code>/setstart ID HH:MM</code>')
        return
    text, keyboard = await sync_to_async(set_employee_start_time)(employee_id, start_time)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command('setgrace'))
async def admin_set_grace(message: Message, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_message(message, allowed_user_ids, admin_user_ids):
        return
    parts = (message.text or '').split()
    if len(parts) != 3:
        await message.answer('Формат: <code>/setgrace ID MIN</code>\nНапример: <code>/setgrace 3 20</code>')
        return
    try:
        employee_id = int(parts[1])
        grace_minutes = int(parts[2])
    except ValueError:
        await message.answer('Нужно так: <code>/setgrace ID MIN</code>')
        return
    if grace_minutes < 0:
        await message.answer('Допустимое опоздание не может быть меньше 0 минут.')
        return
    text, keyboard = await sync_to_async(set_employee_grace_minutes)(employee_id, grace_minutes)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command('dayoff'))
async def admin_add_day_off(message: Message, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_message(message, allowed_user_ids, admin_user_ids):
        return
    parts = (message.text or '').split()
    if len(parts) not in (3, 4):
        await message.answer(
            'Один день: <code>/dayoff ID YYYY-MM-DD</code>\n'
            'Несколько дней: <code>/dayoff ID YYYY-MM-DD YYYY-MM-DD</code>'
        )
        return
    try:
        employee_id = int(parts[1])
        start_date = datetime.strptime(parts[2], DATE_FORMAT).date()
        end_date = datetime.strptime(parts[3], DATE_FORMAT).date() if len(parts) == 4 else start_date
    except ValueError:
        await message.answer('ID должен быть числом, даты — в формате <code>YYYY-MM-DD</code>.')
        return
    text, keyboard = await sync_to_async(add_employee_day_off)(employee_id, start_date, end_date)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command('removedayoff'))
async def admin_remove_day_off(message: Message, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_message(message, allowed_user_ids, admin_user_ids):
        return
    parts = (message.text or '').split()
    if len(parts) != 3:
        await message.answer('Формат: <code>/removedayoff ID YYYY-MM-DD</code>')
        return
    try:
        employee_id = int(parts[1])
        selected_date = datetime.strptime(parts[2], DATE_FORMAT).date()
    except ValueError:
        await message.answer('ID должен быть числом, дата — в формате <code>YYYY-MM-DD</code>.')
        return
    text, keyboard = await sync_to_async(remove_employee_day_off)(employee_id, selected_date)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command('today'))
@router.message(F.text.casefold() == 'сегодня')
async def today(message: Message, allowed_user_ids: set[int]):
    if not await _guard_message(message, allowed_user_ids):
        return
    selected_date = timezone.localdate()
    await _answer_report(message, selected_date)


@router.message(Command('date'))
async def date_report(message: Message, allowed_user_ids: set[int]):
    if not await _guard_message(message, allowed_user_ids):
        return

    parts = (message.text or '').split(maxsplit=1)
    if len(parts) == 1:
        await message.answer(
            'Напишите дату так:\n<code>/date 2026-05-21</code>',
            reply_markup=main_keyboard(),
        )
        return

    try:
        selected_date = datetime.strptime(parts[1].strip(), DATE_FORMAT).date()
    except ValueError:
        await message.answer('Дата должна быть в формате <code>YYYY-MM-DD</code>. Например: <code>/date 2026-05-21</code>')
        return

    await _answer_report(message, selected_date)


@router.message(F.text.casefold() == 'дата /date')
async def date_hint(message: Message, allowed_user_ids: set[int]):
    if not await _guard_message(message, allowed_user_ids):
        return
    await message.answer('Для просмотра другой даты напишите:\n<code>/date 2026-05-21</code>')


@router.message(Command('present'))
@router.message(F.text.casefold() == 'сейчас на работе')
async def present(message: Message, allowed_user_ids: set[int]):
    if not await _guard_message(message, allowed_user_ids):
        return
    text = await sync_to_async(build_present_report)()
    await _send_long(message, text, reply_markup=main_keyboard())


@router.message(Command('absent'))
@router.message(F.text.casefold() == 'кого нет')
async def absent(message: Message, allowed_user_ids: set[int]):
    if not await _guard_message(message, allowed_user_ids):
        return
    text = await sync_to_async(build_absent_report)()
    await _send_long(message, text, reply_markup=main_keyboard())


@router.message(Command('scan'))
@router.message(F.text.casefold() == 'сканировать')
async def scan(message: Message, allowed_user_ids: set[int]):
    if not await _guard_message(message, allowed_user_ids):
        return
    wait_message = await message.answer('Сканирую Wi-Fi...')
    await sync_to_async(run_scan)()
    await wait_message.edit_text('Сканирование готово.')
    await _answer_report(message, timezone.localdate())


@router.callback_query(F.data.startswith('day:'))
async def day_callback(callback: CallbackQuery, allowed_user_ids: set[int]):
    if not await _guard_callback(callback, allowed_user_ids):
        return
    value = callback.data.split(':', 1)[1]
    try:
        selected_date = datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        await callback.answer('Неверная дата', show_alert=True)
        return
    text = await sync_to_async(build_day_report)(selected_date)
    await callback.message.edit_text(text, reply_markup=report_keyboard(selected_date))
    await callback.answer()


@router.callback_query(F.data == 'present')
async def present_callback(callback: CallbackQuery, allowed_user_ids: set[int]):
    if not await _guard_callback(callback, allowed_user_ids):
        return
    text = await sync_to_async(build_present_report)()
    await callback.message.edit_text(text, reply_markup=report_keyboard(timezone.localdate()))
    await callback.answer()


@router.callback_query(F.data == 'absent')
async def absent_callback(callback: CallbackQuery, allowed_user_ids: set[int]):
    if not await _guard_callback(callback, allowed_user_ids):
        return
    text = await sync_to_async(build_absent_report)()
    await callback.message.edit_text(text, reply_markup=report_keyboard(timezone.localdate()))
    await callback.answer()


@router.callback_query(F.data == 'scan')
async def scan_callback(callback: CallbackQuery, allowed_user_ids: set[int]):
    if not await _guard_callback(callback, allowed_user_ids):
        return
    await callback.answer('Сканирую...')
    await sync_to_async(run_scan)()
    text = await sync_to_async(build_day_report)(timezone.localdate())
    await callback.message.edit_text(text, reply_markup=report_keyboard(timezone.localdate()))


@router.callback_query(F.data == 'admin:home')
async def admin_home_callback(callback: CallbackQuery, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_callback(callback, allowed_user_ids, admin_user_ids):
        return
    text, keyboard = await sync_to_async(build_admin_home)()
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:emp:'))
async def admin_employee_callback(callback: CallbackQuery, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_callback(callback, allowed_user_ids, admin_user_ids):
        return
    employee_id = _callback_employee_id(callback.data)
    text, keyboard = await sync_to_async(build_admin_employee_card)(employee_id)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:start:'))
async def admin_start_hint_callback(callback: CallbackQuery, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_callback(callback, allowed_user_ids, admin_user_ids):
        return
    employee_id = _callback_employee_id(callback.data)
    await callback.answer()
    await callback.message.answer(
        f'Напишите новое начало работы так:\n<code>/setstart {employee_id} 09:30</code>'
    )


@router.callback_query(F.data.startswith('admin:grace:'))
async def admin_grace_hint_callback(callback: CallbackQuery, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_callback(callback, allowed_user_ids, admin_user_ids):
        return
    employee_id = _callback_employee_id(callback.data)
    await callback.answer()
    await callback.message.answer(
        f'Напишите допустимое опоздание так:\n<code>/setgrace {employee_id} 20</code>'
    )


@router.callback_query(F.data.startswith('admin:clear:'))
async def admin_clear_schedule_callback(callback: CallbackQuery, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_callback(callback, allowed_user_ids, admin_user_ids):
        return
    employee_id = _callback_employee_id(callback.data)
    text, keyboard = await sync_to_async(clear_employee_schedule)(employee_id)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer('График убран')


@router.callback_query(F.data.startswith('admin:dayoff:'))
async def admin_day_off_hint_callback(callback: CallbackQuery, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_callback(callback, allowed_user_ids, admin_user_ids):
        return
    employee_id = _callback_employee_id(callback.data)
    await callback.answer()
    await callback.message.answer(
        'Добавить один выходной:\n'
        f'<code>/dayoff {employee_id} {timezone.localdate():%Y-%m-%d}</code>\n\n'
        'Добавить несколько дней:\n'
        f'<code>/dayoff {employee_id} {timezone.localdate():%Y-%m-%d} '
        f'{timezone.localdate() + timedelta(days=2):%Y-%m-%d}</code>\n\n'
        'Удалить выходной по дате:\n'
        f'<code>/removedayoff {employee_id} {timezone.localdate():%Y-%m-%d}</code>'
    )


@router.callback_query(F.data.startswith('admin:toggle:'))
async def admin_toggle_late_alerts_callback(callback: CallbackQuery, allowed_user_ids: set[int], admin_user_ids: set[int]):
    if not await _guard_admin_callback(callback, allowed_user_ids, admin_user_ids):
        return
    employee_id = _callback_employee_id(callback.data)
    text, keyboard = await sync_to_async(toggle_employee_late_alerts)(employee_id)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer('Статус изменен')


async def _answer_report(message, selected_date):
    text = await sync_to_async(build_day_report)(selected_date)
    await _send_long(message, text, reply_markup=report_keyboard(selected_date))


async def _send_long(message, text, reply_markup=None):
    chunks = []
    current = ''
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > MAX_MESSAGE_LENGTH:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)

    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


def build_admin_home():
    employees = list(Employee.objects.filter(is_active=True).order_by('full_name'))
    lines = [
        '<b>Настройки сотрудников</b>',
        '',
        'Выберите сотрудника, чтобы изменить график, предупреждения или выходные.',
    ]
    if not employees:
        lines.append('Активных сотрудников пока нет.')
        return '\n'.join(lines), None

    buttons = [
        [InlineKeyboardButton(text=f'{employee.id}. {employee.full_name}', callback_data=f'admin:emp:{employee.id}')]
        for employee in employees
    ]
    return '\n'.join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_employee_card(employee_id):
    employee = Employee.objects.filter(id=employee_id).first()
    if not employee:
        return 'Сотрудник не найден.', _admin_back_keyboard()

    text = _admin_employee_text(employee)
    return text, _admin_employee_keyboard(employee)


def set_employee_start_time(employee_id, start_time):
    employee = Employee.objects.filter(id=employee_id).first()
    if not employee:
        return 'Сотрудник не найден.', _admin_back_keyboard()
    employee.work_start_time = start_time
    employee.save(update_fields=['work_start_time'])
    return _admin_employee_text(employee), _admin_employee_keyboard(employee)


def set_employee_grace_minutes(employee_id, grace_minutes):
    employee = Employee.objects.filter(id=employee_id).first()
    if not employee:
        return 'Сотрудник не найден.', _admin_back_keyboard()
    employee.late_grace_minutes = grace_minutes
    employee.save(update_fields=['late_grace_minutes'])
    return _admin_employee_text(employee), _admin_employee_keyboard(employee)


def clear_employee_schedule(employee_id):
    employee = Employee.objects.filter(id=employee_id).first()
    if not employee:
        return 'Сотрудник не найден.', _admin_back_keyboard()
    employee.work_start_time = None
    employee.late_grace_minutes = None
    employee.save(update_fields=['work_start_time', 'late_grace_minutes'])
    return _admin_employee_text(employee), _admin_employee_keyboard(employee)


def toggle_employee_late_alerts(employee_id):
    employee = Employee.objects.filter(id=employee_id).first()
    if not employee:
        return 'Сотрудник не найден.', _admin_back_keyboard()
    employee.late_alerts_enabled = not employee.late_alerts_enabled
    employee.save(update_fields=['late_alerts_enabled'])
    return _admin_employee_text(employee), _admin_employee_keyboard(employee)


def add_employee_day_off(employee_id, start_date, end_date):
    employee = Employee.objects.filter(id=employee_id).first()
    if not employee:
        return 'Сотрудник не найден.', _admin_back_keyboard()
    if end_date < start_date:
        return 'Последняя дата не может быть раньше первой.', _admin_employee_keyboard(employee)
    EmployeeDayOff.objects.get_or_create(
        employee=employee,
        start_date=start_date,
        end_date=end_date,
    )
    return _admin_employee_text(employee), _admin_employee_keyboard(employee)


def remove_employee_day_off(employee_id, selected_date):
    employee = Employee.objects.filter(id=employee_id).first()
    if not employee:
        return 'Сотрудник не найден.', _admin_back_keyboard()
    deleted, _ = EmployeeDayOff.objects.filter(
        employee=employee,
        start_date__lte=selected_date,
        end_date__gte=selected_date,
    ).delete()
    prefix = '' if deleted else 'На эту дату выходной не найден.\n\n'
    return prefix + _admin_employee_text(employee), _admin_employee_keyboard(employee)


def _admin_employee_text(employee):
    start = _format_time(employee.work_start_time)
    grace = '-' if employee.late_grace_minutes is None else f'{employee.late_grace_minutes} мин'
    alerts = 'включены' if employee.late_alerts_enabled else 'выключены'
    days_off = list(employee.days_off.filter(end_date__gte=timezone.localdate()).order_by('start_date')[:5])
    days_off_text = ', '.join(_format_day_off_period(item) for item in days_off) or '-'
    return (
        f'<b>{html.escape(employee.full_name)}</b>\n\n'
        f'ID: <code>{employee.id}</code>\n'
        f'Начало работы: <b>{start}</b>\n'
        f'Допустимое опоздание: <b>{grace}</b>\n'
        f'Предупреждения об опоздании: <b>{alerts}</b>\n\n'
        f'Ближайшие выходные: <b>{days_off_text}</b>\n\n'
        'Чтобы предупреждения работали, нужно указать начало работы и допустимое опоздание.'
    )


def _admin_employee_keyboard(employee):
    status_text = 'Выключить предупреждения' if employee.late_alerts_enabled else 'Включить предупреждения'
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Изменить начало работы', callback_data=f'admin:start:{employee.id}')],
            [InlineKeyboardButton(text='Изменить допустимое опоздание', callback_data=f'admin:grace:{employee.id}')],
            [InlineKeyboardButton(text='Убрать рабочий график', callback_data=f'admin:clear:{employee.id}')],
            [InlineKeyboardButton(text=status_text, callback_data=f'admin:toggle:{employee.id}')],
            [InlineKeyboardButton(text='Добавить или убрать выходной', callback_data=f'admin:dayoff:{employee.id}')],
            [InlineKeyboardButton(text='Назад к списку', callback_data='admin:home')],
        ]
    )


def _admin_back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='Назад к списку', callback_data='admin:home')]]
    )


def _callback_employee_id(data):
    try:
        return int(data.rsplit(':', 1)[1])
    except (TypeError, ValueError):
        return 0


def run_scan():
    if not _scan_lock.acquire(blocking=False):
        return False
    try:
        call_command(
            'scan_wifi_attendance',
            skip_ping=False,
            absence_seconds=getattr(settings, 'ATTENDANCE_ABSENCE_SECONDS', 60),
            misses_before_checkout=1,
        )
        return True
    finally:
        _scan_lock.release()


def build_late_alert_actions(chat_id, alert_start_time=None):
    selected_date = timezone.localdate()
    now = timezone.now()
    start = timezone.make_aware(datetime.combine(selected_date, datetime.min.time()))
    end = start + timedelta(days=1)
    actions = []

    employees = list(Employee.objects.filter(is_active=True).order_by('full_name'))
    events_by_employee = {}
    day_off_employee_ids = set(EmployeeDayOff.objects.filter(
        start_date__lte=selected_date,
        end_date__gte=selected_date,
    ).values_list('employee_id', flat=True))
    for event in AttendanceEvent.objects.filter(observed_at__gte=start, observed_at__lt=end).order_by('observed_at'):
        events_by_employee.setdefault(event.employee_id, []).append(event)

    for employee in employees:
        events = events_by_employee.get(employee.id, [])
        first_in = next((event for event in events if event.event_type == AttendanceEvent.CHECK_IN), None)
        notification = LateNotification.objects.filter(
            employee=employee,
            alert_date=selected_date,
            chat_id=str(chat_id),
        ).first()

        if employee.id in day_off_employee_ids:
            if notification and notification.status == LateNotification.STATUS_ACTIVE:
                actions.append(_resolve_late_notification_action(notification))
            continue

        if first_in:
            if notification and notification.status == LateNotification.STATUS_ACTIVE:
                if notification.message_id:
                    actions.append({
                        'type': 'delete_warning',
                        'notification_id': notification.id,
                        'message_id': notification.message_id,
                    })
                else:
                    actions.append({
                        'type': 'resolve_undelivered',
                        'notification_id': notification.id,
                    })
            continue

        if not employee.late_alerts_enabled:
            if notification and notification.status == LateNotification.STATUS_ACTIVE:
                if notification.message_id:
                    actions.append({
                        'type': 'delete_warning',
                        'notification_id': notification.id,
                        'message_id': notification.message_id,
                    })
                else:
                    actions.append({
                        'type': 'resolve_undelivered',
                        'notification_id': notification.id,
                    })
            continue

        due_at = _employee_late_due_at(employee, selected_date, alert_start_time)
        if due_at is None:
            continue
        if now < due_at:
            continue

        if notification and notification.status == LateNotification.STATUS_RESOLVED:
            continue

        if notification and notification.alert_count >= MAX_LATE_WARNINGS_PER_DAY:
            continue

        if not notification:
            notification = LateNotification.objects.create(
                employee=employee,
                alert_date=selected_date,
                chat_id=str(chat_id),
                status=LateNotification.STATUS_ACTIVE,
            )

        notification.status = LateNotification.STATUS_ACTIVE
        notification.save(update_fields=['status', 'updated_at'])
        actions.append({
            'type': 'send_warning',
            'notification_id': notification.id,
            'text': build_late_warning_text(employee, due_at),
        })

    return actions


def save_late_notification_message(notification_id, message_id):
    now = timezone.now()
    notification = LateNotification.objects.get(id=notification_id)
    notification.message_id = message_id
    notification.alert_count += 1
    notification.last_alert_at = now
    notification.updated_at = now
    notification.save(update_fields=['message_id', 'alert_count', 'last_alert_at', 'updated_at'])


def mark_late_notification_resolved(notification_id):
    now = timezone.now()
    LateNotification.objects.filter(id=notification_id).update(
        status=LateNotification.STATUS_RESOLVED,
        resolved_at=now,
        updated_at=now,
    )


def build_daily_report_action(chat_id, send_time):
    selected_date = timezone.localdate()
    local_now = timezone.localtime()
    current_time = local_now.time().replace(tzinfo=None)
    report = DailyAttendanceReport.objects.filter(
        report_date=selected_date,
        chat_id=str(chat_id),
    ).first()

    if not report and current_time < send_time:
        return None

    text = build_daily_attendance_message(selected_date)
    if not report:
        report = DailyAttendanceReport.objects.create(
            report_date=selected_date,
            chat_id=str(chat_id),
        )

    if not report.message_id:
        return {'type': 'send', 'report_id': report.id, 'text': text}

    if report.content != text:
        return {
            'type': 'edit',
            'report_id': report.id,
            'message_id': report.message_id,
            'text': text,
        }

    return None


def save_daily_report_message(report_id, message_id, content):
    now = timezone.now()
    DailyAttendanceReport.objects.filter(id=report_id).update(
        message_id=message_id,
        content=content,
        sent_at=now,
        updated_at=now,
    )


def save_daily_report_content(report_id, content):
    DailyAttendanceReport.objects.filter(id=report_id).update(
        content=content,
        updated_at=timezone.now(),
    )


def build_daily_attendance_message(selected_date):
    start = timezone.make_aware(datetime.combine(selected_date, datetime.min.time()))
    end = start + timedelta(days=1)
    employees = list(Employee.objects.filter(is_active=True).order_by('full_name'))
    first_arrivals = {}
    day_off_employee_ids = set(EmployeeDayOff.objects.filter(
        start_date__lte=selected_date,
        end_date__gte=selected_date,
    ).values_list('employee_id', flat=True))
    for event in AttendanceEvent.objects.filter(
        observed_at__gte=start,
        observed_at__lt=end,
        event_type=AttendanceEvent.CHECK_IN,
    ).order_by('observed_at'):
        first_arrivals.setdefault(event.employee_id, event)

    lines = [
        '☀️ <b>Доброе утро, коллеги!</b>',
        'Буду ждать вас в офисе и аккуратно отмечу, кто во сколько пришел 😊',
        '',
        f'📋 <b>Список сотрудников за {selected_date:%d.%m.%Y}</b>',
        '',
    ]
    if not employees:
        lines.append('Активных сотрудников пока нет.')
        return '\n'.join(lines)

    for employee in employees:
        if employee.id in day_off_employee_ids:
            lines.extend([
                f'🟣 {_employee_telegram_mention(employee)}',
                'Статус: <b>Выходной</b>',
                '',
            ])
            continue
        arrival = first_arrivals.get(employee.id)
        arrival_icon = '🟢' if arrival else '⚪'
        lines.extend([
            f'{arrival_icon} {_employee_telegram_mention(employee)}',
            f'Начало работы: <b>{_format_time(employee.work_start_time)}</b>',
            f'Пришел: <b>{_format_time(arrival.observed_at) if arrival else "-"}</b>',
            '',
        ])
    return '\n'.join(lines).rstrip()


def build_late_warning_text(employee, due_at):
    mention = _employee_telegram_mention(employee)
    return (
        '🔴 <b>Предупреждение об опоздании</b>\n\n'
        f'{mention}\n'
        'Статус: <b>Не пришел</b>\n'
        f'Начало работы: <b>{_format_time(employee.work_start_time)}</b>\n'
        f'Должен быть до: <b>{_format_time(due_at)}</b>\n\n'
        'Сотрудник пока не отмечен в Wi-Fi.'
    )


def build_arrived_alert_text(employee, first_in):
    mention = _employee_telegram_mention(employee)
    return (
        '🟢 <b>Сотрудник пришел</b>\n\n'
        f'{mention}\n'
        'Статус: <b>Пришел</b>\n'
        f'Пришел: <b>{_format_time(first_in.observed_at)}</b>'
    )


def _employee_late_due_at(employee, selected_date, alert_start_time=None):
    if not employee.work_start_time or employee.late_grace_minutes is None:
        return None

    work_start = alert_start_time or employee.work_start_time
    due_at = timezone.make_aware(datetime.combine(selected_date, work_start))
    if alert_start_time is None:
        due_at += timedelta(minutes=employee.late_grace_minutes)
    return due_at


def _employee_telegram_mention(employee):
    value = (employee.telegram_user or '').strip()
    safe_name = html.escape(employee.full_name)
    if not value:
        return f'👤 <b>{safe_name}</b>'
    if value.startswith('@'):
        return f'{html.escape(value)} - <b>{safe_name}</b>'
    if value.isdigit():
        return f'<a href="tg://user?id={value}">{safe_name}</a>'
    return f'@{html.escape(value)} - <b>{safe_name}</b>'


def build_present_report():
    selected_date = timezone.localdate()
    rows = _build_rows(selected_date)
    present_rows = [row for row in rows if row.is_present]

    lines = [
        '<b>Сейчас на работе</b>',
        f'Обновлено: {_format_dt(timezone.now())}',
        '',
    ]
    if not present_rows:
        lines.append('Пока никого не видно в Wi-Fi.')
    else:
        for row in present_rows:
            lines.append(_employee_line(row))
    return '\n'.join(lines)


def build_absent_report():
    selected_date = timezone.localdate()
    rows = _build_rows(selected_date)
    absent_rows = [row for row in rows if not row.is_present and not row.is_day_off]

    lines = [
        '<b>Кого сейчас нет</b>',
        f'Обновлено: {_format_dt(timezone.now())}',
        '',
    ]
    if not absent_rows:
        lines.append('Все активные сотрудники сейчас на работе.')
    else:
        for row in absent_rows:
            lines.append(_employee_line(row))
    return '\n'.join(lines)


def build_day_report(selected_date):
    rows = _build_rows(selected_date)
    present_count = sum(1 for row in rows if row.is_present)
    day_off_count = sum(1 for row in rows if row.is_day_off)
    absent_count = len(rows) - present_count - day_off_count
    check_in_count = sum(row.check_in_count for row in rows)
    check_out_count = sum(row.check_out_count for row in rows)

    title_date = selected_date.strftime('%d.%m.%Y')
    lines = [
        f'<b>Журнал сотрудников за {title_date}</b>',
        f'На работе: <b>{present_count}</b> | Нет: <b>{absent_count}</b>',
        f'Выходной: <b>{day_off_count}</b>',
        f'Приходов: <b>{check_in_count}</b> | Уходов: <b>{check_out_count}</b>',
        '',
    ]

    if not rows:
        lines.append('Активных сотрудников пока нет.')
        return '\n'.join(lines)

    for row in rows:
        lines.append(_employee_line(row))
    return '\n'.join(lines)


def _build_rows(selected_date):
    now = timezone.now()
    start = timezone.make_aware(datetime.combine(selected_date, datetime.min.time()))
    end = start + timedelta(days=1)
    present_cutoff = now - timedelta(seconds=getattr(settings, 'ATTENDANCE_ABSENCE_SECONDS', 60))

    employees = list(
        Employee.objects
        .filter(is_active=True)
        .prefetch_related(
            Prefetch(
                'attendanceevent_set',
                queryset=AttendanceEvent.objects.filter(observed_at__gte=start, observed_at__lt=end).order_by('observed_at'),
                to_attr='day_events',
            )
        )
        .order_by('full_name')
    )
    presences = {
        presence.employee_id: presence
        for presence in Presence.objects.filter(employee__is_active=True).select_related('employee')
    }
    day_off_employee_ids = set(EmployeeDayOff.objects.filter(
        start_date__lte=selected_date,
        end_date__gte=selected_date,
    ).values_list('employee_id', flat=True))

    rows = []
    for employee in employees:
        events = list(employee.day_events)
        first_in = next((event for event in events if event.event_type == AttendanceEvent.CHECK_IN), None)
        last_out = next((event for event in reversed(events) if event.event_type == AttendanceEvent.CHECK_OUT), None)
        lateness = _calculate_lateness(employee, first_in, selected_date)
        presence = presences.get(employee.id)
        is_present = bool(
            selected_date == timezone.localdate()
            and presence
            and presence.status == Presence.STATUS_PRESENT
            and presence.last_seen_at
            and presence.last_seen_at >= present_cutoff
        )

        rows.append(
            EmployeeDayRow(
                employee_id=employee.id,
                name=employee.full_name,
                position=employee.position or '-',
                scheduled_start=_format_time(employee.work_start_time),
                first_in=_format_time(first_in.observed_at) if first_in else '-',
                last_out=_format_time(last_out.observed_at) if last_out else '-',
                lateness=lateness,
                has_arrived_today=bool(first_in),
                is_late=lateness not in ('-', 'Вовремя'),
                is_present=is_present,
                check_in_count=sum(1 for event in events if event.event_type == AttendanceEvent.CHECK_IN),
                check_out_count=sum(1 for event in events if event.event_type == AttendanceEvent.CHECK_OUT),
                is_day_off=employee.id in day_off_employee_ids,
            )
        )
    return rows


def _employee_line(row):
    if row.is_day_off:
        return (
            f'🟣 👤 <b>{html.escape(row.name)}</b> - {html.escape(row.position)}\n'
            'Статус: <b>Выходной</b>\n'
        )
    status_icon = '🟢' if row.is_present else '🔴'
    status = 'На работе' if row.is_present else 'Нет'
    name_icon = _arrival_icon(row)
    parts = [
        f'{name_icon} 👤 <b>{html.escape(row.name)}</b> - {html.escape(row.position)}',
        f'{status_icon} Статус: <b>{status}</b>',
        f'Начало: {row.scheduled_start}',
        f'Пришел: {row.first_in}',
        f'Ушел: {row.last_out}',
        f'Опоздание: {row.lateness}',
    ]
    return '\n'.join(parts) + '\n'


def _arrival_icon(row):
    if not row.has_arrived_today:
        return '🔴'
    if row.is_late:
        return '🟠'
    return '🟢'


def _calculate_lateness(employee, first_check_in, selected_date):
    if not first_check_in or not employee.work_start_time or employee.late_grace_minutes is None:
        return '-'

    scheduled_at = timezone.make_aware(datetime.combine(selected_date, employee.work_start_time))
    grace_minutes = employee.late_grace_minutes
    late_seconds = (first_check_in.observed_at - scheduled_at).total_seconds() - (grace_minutes * 60)
    late_minutes = max(int(late_seconds // 60), 0)

    if late_minutes <= 0:
        return 'Вовремя'

    hours, minutes = divmod(late_minutes, 60)
    if hours and minutes:
        return f'{hours} ч {minutes} мин'
    if hours:
        return f'{hours} ч'
    return f'{minutes} мин'


def _format_dt(value):
    return timezone.localtime(value).strftime('%H:%M %d.%m.%Y') if value else '-'


def _format_time(value):
    if not value:
        return '-'
    if hasattr(value, 'strftime'):
        if hasattr(value, 'tzinfo') and value.tzinfo:
            value = timezone.localtime(value)
        return value.strftime('%H:%M')
    return str(value)


def _format_day_off_period(day_off):
    if day_off.start_date == day_off.end_date:
        return day_off.start_date.strftime('%d.%m.%Y')
    return f'{day_off.start_date:%d.%m.%Y}–{day_off.end_date:%d.%m.%Y}'


def _resolve_late_notification_action(notification):
    if notification.message_id:
        return {
            'type': 'delete_warning',
            'notification_id': notification.id,
            'message_id': notification.message_id,
        }
    return {
        'type': 'resolve_undelivered',
        'notification_id': notification.id,
    }
