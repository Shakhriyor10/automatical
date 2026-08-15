from datetime import datetime, time, timedelta
from threading import Lock

from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateformat import format as date_format

from .models import AttendanceEvent, Device, Employee, Presence, UnknownDevice


SCAN_ABSENCE_SECONDS = getattr(settings, 'ATTENDANCE_ABSENCE_SECONDS', 300)
SCAN_MISSES_BEFORE_CHECKOUT = 1
PRESENT_WINDOW_SECONDS = SCAN_ABSENCE_SECONDS
UNKNOWN_WINDOW_SECONDS = 3600
API_SCAN_INTERVAL_SECONDS = 8
_api_scan_lock = Lock()
_last_api_scan_at = None


def dashboard(request):
    selected_date = _get_selected_date(request)
    context = {
        **_dashboard_context(selected_date),
        'selected_date': selected_date,
        'selected_date_value': selected_date.isoformat(),
        'previous_date': (selected_date - timedelta(days=1)).isoformat(),
        'next_date': (selected_date + timedelta(days=1)).isoformat(),
        'is_today': selected_date == timezone.localdate(),
        'monitor_interval_seconds': 10,
        'absence_seconds': SCAN_ABSENCE_SECONDS,
    }
    return render(request, 'attendance/dashboard.html', context)


def api_status(request):
    selected_date = _get_selected_date(request)
    if selected_date == timezone.localdate():
        _scan_if_needed()
    context = _dashboard_context(selected_date)
    return JsonResponse(_serialize_context(context))


def _scan_if_needed():
    global _last_api_scan_at

    now = timezone.now()
    if _last_api_scan_at and (now - _last_api_scan_at).total_seconds() < API_SCAN_INTERVAL_SECONDS:
        return

    if not _api_scan_lock.acquire(blocking=False):
        return

    try:
        now = timezone.now()
        if _last_api_scan_at and (now - _last_api_scan_at).total_seconds() < API_SCAN_INTERVAL_SECONDS:
            return
        call_command(
            'scan_wifi_attendance',
            skip_ping=False,
            absence_seconds=SCAN_ABSENCE_SECONDS,
            misses_before_checkout=SCAN_MISSES_BEFORE_CHECKOUT,
        )
        _last_api_scan_at = timezone.now()
    finally:
        _api_scan_lock.release()


def _dashboard_context(selected_date):
    now = timezone.now()
    start = timezone.make_aware(datetime.combine(selected_date, datetime.min.time()))
    end = start + timedelta(days=1)

    active_employees = Employee.objects.filter(is_active=True).order_by('full_name')
    presences = Presence.objects.select_related('employee', 'device').filter(employee__is_active=True)
    today_events = (
        AttendanceEvent.objects
        .select_related('employee', 'device')
        .filter(observed_at__gte=start, observed_at__lt=end)
        .order_by('observed_at')
    )

    present_cutoff = now - timedelta(seconds=PRESENT_WINDOW_SECONDS)
    present = (
        presences
        .filter(status=Presence.STATUS_PRESENT, last_seen_at__gte=present_cutoff)
        .order_by('employee__full_name')
    )

    registered_macs = Device.objects.values_list('mac_address', flat=True)
    unknown_cutoff = now - timedelta(seconds=UNKNOWN_WINDOW_SECONDS)
    unknown_devices = (
        UnknownDevice.objects
        .filter(ip_address__startswith='192.168.1.', last_seen_at__gte=unknown_cutoff)
        .exclude(mac_address='ff:ff:ff:ff:ff:ff')
        .exclude(mac_address__startswith='01:00:5e:')
        .exclude(mac_address__in=registered_macs)
        .order_by('-last_seen_at', 'ip_address')
    )

    daily_rows = _build_daily_rows(active_employees, today_events, presences, selected_date, present_cutoff)

    return {
        'present': present,
        'daily_rows': daily_rows,
        'unknown_devices': unknown_devices[:80],
        'present_count': present.count(),
        'absent_count': max(active_employees.count() - present.count(), 0),
        'check_in_count': today_events.filter(event_type=AttendanceEvent.CHECK_IN).count(),
        'check_out_count': today_events.filter(event_type=AttendanceEvent.CHECK_OUT).count(),
        'device_count': Device.objects.count(),
        'unknown_count': unknown_devices.count(),
    }


def scan_now(request):
    if request.method == 'POST':
        call_command(
            'scan_wifi_attendance',
            skip_ping=False,
            absence_seconds=SCAN_ABSENCE_SECONDS,
            misses_before_checkout=SCAN_MISSES_BEFORE_CHECKOUT,
        )
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'scanned_at': timezone.localtime().isoformat()})
        messages.success(request, 'Сканирование выполнено.')
    redirect_to = request.POST.get('next') or 'attendance:dashboard'
    return redirect(redirect_to)


def _get_selected_date(request):
    value = request.GET.get('date')
    if not value:
        return timezone.localdate()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return timezone.localdate()


def _build_daily_rows(employees, events, presences, selected_date, present_cutoff):
    events_by_employee = {}
    for event in events:
        events_by_employee.setdefault(event.employee_id, []).append(event)

    presence_by_employee = {presence.employee_id: presence for presence in presences}
    rows = []
    for employee in employees:
        employee_events = events_by_employee.get(employee.id, [])
        intervals = _build_intervals(employee_events)
        first_check_in = next(
            (event for event in employee_events if event.event_type == AttendanceEvent.CHECK_IN),
            None,
        )
        last_check_out = next(
            (event for event in reversed(employee_events) if event.event_type == AttendanceEvent.CHECK_OUT),
            None,
        )
        lateness = _calculate_lateness(employee, first_check_in, selected_date)
        presence = presence_by_employee.get(employee.id)
        is_present_now = bool(
            selected_date == timezone.localdate()
            and presence
            and presence.status == Presence.STATUS_PRESENT
            and presence.last_seen_at
            and presence.last_seen_at >= present_cutoff
        )

        rows.append({
            'employee': employee,
            'first_check_in': first_check_in,
            'last_check_out': last_check_out,
            'scheduled_start': employee.work_start_time,
            'lateness': lateness,
            'intervals': intervals,
            'events': employee_events,
            'check_in_count': sum(1 for event in employee_events if event.event_type == AttendanceEvent.CHECK_IN),
            'check_out_count': sum(1 for event in employee_events if event.event_type == AttendanceEvent.CHECK_OUT),
            'event_count': len(employee_events),
            'is_present_now': is_present_now,
            'status': 'На работе' if is_present_now else 'Нет',
            'last_ip': presence.last_ip if presence else None,
            'last_seen_at': presence.last_seen_at if presence else None,
        })
    return rows


def _build_intervals(events):
    intervals = []
    open_check_in = None
    for event in events:
        if event.event_type == AttendanceEvent.CHECK_IN:
            open_check_in = event
        elif event.event_type == AttendanceEvent.CHECK_OUT and open_check_in:
            intervals.append({
                'check_in': open_check_in,
                'check_out': event,
            })
            open_check_in = None

    if open_check_in:
        intervals.append({
            'check_in': open_check_in,
            'check_out': None,
        })
    return intervals


def _calculate_lateness(employee, first_check_in, selected_date):
    if not first_check_in or not employee.work_start_time or employee.late_grace_minutes is None:
        return {
            'minutes': None,
            'display': '-',
            'is_late': False,
        }

    scheduled_at = timezone.make_aware(datetime.combine(selected_date, employee.work_start_time))
    arrived_at = first_check_in.observed_at
    grace_minutes = employee.late_grace_minutes
    late_seconds = (arrived_at - scheduled_at).total_seconds() - (grace_minutes * 60)
    late_minutes = max(int(late_seconds // 60), 0)

    if late_minutes <= 0:
        return {
            'minutes': 0,
            'display': 'Вовремя',
            'is_late': False,
        }

    hours, minutes = divmod(late_minutes, 60)
    if hours:
        display = f'{hours} ч {minutes} мин' if minutes else f'{hours} ч'
    else:
        display = f'{minutes} мин'

    return {
        'minutes': late_minutes,
        'display': display,
        'is_late': True,
    }


def _serialize_context(context):
    return {
        'stats': {
            'present_count': context['present_count'],
            'absent_count': context['absent_count'],
            'check_in_count': context['check_in_count'],
            'check_out_count': context['check_out_count'],
            'device_count': context['device_count'],
            'unknown_count': context['unknown_count'],
        },
        'present': [
            {
                'employee': presence.employee.full_name,
                'first_seen_at': _format_dt(presence.first_seen_at),
                'last_seen_at': _format_dt(presence.last_seen_at),
                'last_ip': presence.last_ip or '',
            }
            for presence in context['present']
        ],
        'unknown_devices': [
            {
                'ip_address': device.ip_address,
                'mac_address': device.mac_address,
                'last_seen_at': _format_dt(device.last_seen_at),
            }
            for device in context['unknown_devices']
        ],
        'daily_rows': [
            {
                'employee': row['employee'].full_name,
                'position': row['employee'].position or '-',
                'first_check_in': _format_time(row['first_check_in'].observed_at) if row['first_check_in'] else '-',
                'last_check_out': _format_time(row['last_check_out'].observed_at) if row['last_check_out'] else '-',
                'scheduled_start': _format_time(row['scheduled_start']),
                'lateness': row['lateness']['display'],
                'lateness_minutes': row['lateness']['minutes'],
                'is_late': row['lateness']['is_late'],
                'is_present_now': row['is_present_now'],
                'last_ip': row['last_ip'] or '',
                'last_seen_at': _format_time(row['last_seen_at']) if row['last_seen_at'] else '',
                'check_in_count': row['check_in_count'],
                'check_out_count': row['check_out_count'],
                'intervals': [
                    {
                        'check_in': _format_time(interval['check_in'].observed_at),
                        'check_out': _format_time(interval['check_out'].observed_at) if interval['check_out'] else 'сейчас',
                        'open': interval['check_out'] is None,
                    }
                    for interval in row['intervals']
                ],
                'events': [
                    {
                        'time': _format_time(event.observed_at),
                        'type': 'Приход' if event.event_type == AttendanceEvent.CHECK_IN else 'Уход',
                        'type_class': 'event-in' if event.event_type == AttendanceEvent.CHECK_IN else 'event-out',
                        'ip': event.ip_address or '',
                    }
                    for event in row['events']
                ],
            }
            for row in context['daily_rows']
        ],
        'updated_at': _format_dt(timezone.now()),
    }


def _format_dt(value):
    if not value:
        return ''
    return date_format(timezone.localtime(value), 'H:i d.m.Y')


def _format_time(value):
    if not value:
        return ''
    if isinstance(value, time):
        return value.strftime('%H:%M')
    return date_format(timezone.localtime(value), 'H:i')
