from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import AttendanceEvent, DailyAttendanceReport, Employee, EmployeeDayOff, LateNotification, UnknownDevice
from .views import _dashboard_context
from .telegram_bot import (
    add_employee_day_off,
    build_daily_attendance_message,
    build_daily_report_action,
    build_late_alert_actions,
    remove_employee_day_off,
)


class TelegramOfflineRecoveryTests(TestCase):
    report_date = date(2026, 5, 25)
    chat_id = 'group'

    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 5, 25, 12, 0))
        self.employee = Employee.objects.create(
            full_name='Test Employee',
            work_start_time=time(9, 0),
            late_grace_minutes=20,
        )

    def test_daily_report_pending_send_retries_after_start_time(self):
        report = DailyAttendanceReport.objects.create(
            report_date=self.report_date,
            chat_id=self.chat_id,
        )
        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.report_date),
            patch('attendance.telegram_bot.timezone.localtime', return_value=self.now),
        ):
            action = build_daily_report_action(self.chat_id, time(9, 0))

        self.assertEqual(action['type'], 'send')
        self.assertEqual(action['report_id'], report.id)

    def test_daily_report_sends_once_even_when_started_late(self):
        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.report_date),
            patch('attendance.telegram_bot.timezone.localtime', return_value=self.now),
        ):
            action = build_daily_report_action(self.chat_id, time(9, 0))

        self.assertEqual(action['type'], 'send')

    def test_failed_late_warning_is_offered_again_until_delivered(self):
        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.report_date),
            patch('attendance.telegram_bot.timezone.now', return_value=self.now),
        ):
            first_actions = build_late_alert_actions(self.chat_id)
            second_actions = build_late_alert_actions(self.chat_id)

        self.assertEqual(first_actions[0]['type'], 'send_warning')
        self.assertEqual(second_actions[0]['type'], 'send_warning')
        notification = LateNotification.objects.get(employee=self.employee)
        self.assertEqual(notification.alert_count, 0)
        self.assertIsNone(notification.message_id)

    def test_delivered_late_warning_is_not_repeated(self):
        LateNotification.objects.create(
            employee=self.employee,
            alert_date=self.report_date,
            chat_id=self.chat_id,
            message_id=123,
            alert_count=1,
            status=LateNotification.STATUS_ACTIVE,
            last_alert_at=self.now,
        )
        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.report_date),
            patch('attendance.telegram_bot.timezone.now', return_value=self.now),
        ):
            actions = build_late_alert_actions(self.chat_id)

        self.assertEqual(actions, [])

    def test_late_warning_can_be_disabled_per_employee(self):
        self.employee.late_alerts_enabled = False
        self.employee.save(update_fields=['late_alerts_enabled'])
        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.report_date),
            patch('attendance.telegram_bot.timezone.now', return_value=self.now),
        ):
            actions = build_late_alert_actions(self.chat_id)

        self.assertEqual(actions, [])

    def test_disabling_late_alerts_deletes_active_warning(self):
        self.employee.late_alerts_enabled = False
        self.employee.save(update_fields=['late_alerts_enabled'])
        notification = LateNotification.objects.create(
            employee=self.employee,
            alert_date=self.report_date,
            chat_id=self.chat_id,
            message_id=789,
            alert_count=1,
            status=LateNotification.STATUS_ACTIVE,
        )
        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.report_date),
            patch('attendance.telegram_bot.timezone.now', return_value=self.now),
        ):
            actions = build_late_alert_actions(self.chat_id)

        self.assertEqual(
            actions,
            [{'type': 'delete_warning', 'notification_id': notification.id, 'message_id': 789}],
        )

    def test_arrival_requests_resolution_for_warning_never_delivered(self):
        notification = LateNotification.objects.create(
            employee=self.employee,
            alert_date=self.report_date,
            chat_id=self.chat_id,
            status=LateNotification.STATUS_ACTIVE,
        )
        AttendanceEvent.objects.create(
            employee=self.employee,
            event_type=AttendanceEvent.CHECK_IN,
            observed_at=self.now,
        )

        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.report_date),
            patch('attendance.telegram_bot.timezone.now', return_value=self.now),
        ):
            actions = build_late_alert_actions(self.chat_id)

        self.assertEqual(
            actions,
            [{'type': 'resolve_undelivered', 'notification_id': notification.id}],
        )

    def test_arrival_deletes_delivered_warning(self):
        notification = LateNotification.objects.create(
            employee=self.employee,
            alert_date=self.report_date,
            chat_id=self.chat_id,
            message_id=456,
            alert_count=1,
            status=LateNotification.STATUS_ACTIVE,
        )
        AttendanceEvent.objects.create(
            employee=self.employee,
            event_type=AttendanceEvent.CHECK_IN,
            observed_at=self.now,
        )

        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.report_date),
            patch('attendance.telegram_bot.timezone.now', return_value=self.now),
        ):
            actions = build_late_alert_actions(self.chat_id)

        self.assertEqual(
            actions,
            [{'type': 'delete_warning', 'notification_id': notification.id, 'message_id': 456}],
        )


class EmployeeDayOffTests(TestCase):
    selected_date = date(2026, 8, 17)

    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 8, 17, 12, 0))
        self.employee = Employee.objects.create(
            full_name='Day Off Employee',
            work_start_time=time(9, 0),
            late_grace_minutes=15,
        )

    def test_day_off_suppresses_late_warning(self):
        EmployeeDayOff.objects.create(
            employee=self.employee,
            start_date=self.selected_date,
            end_date=self.selected_date,
        )
        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.selected_date),
            patch('attendance.telegram_bot.timezone.now', return_value=self.now),
        ):
            actions = build_late_alert_actions('group')

        self.assertEqual(actions, [])
        self.assertFalse(LateNotification.objects.exists())

    def test_day_off_resolves_existing_warning(self):
        notification = LateNotification.objects.create(
            employee=self.employee,
            alert_date=self.selected_date,
            chat_id='group',
            message_id=321,
            status=LateNotification.STATUS_ACTIVE,
        )
        EmployeeDayOff.objects.create(
            employee=self.employee,
            start_date=self.selected_date,
            end_date=self.selected_date,
        )
        with (
            patch('attendance.telegram_bot.timezone.localdate', return_value=self.selected_date),
            patch('attendance.telegram_bot.timezone.now', return_value=self.now),
        ):
            actions = build_late_alert_actions('group')

        self.assertEqual(actions, [{
            'type': 'delete_warning',
            'notification_id': notification.id,
            'message_id': 321,
        }])

    def test_daily_message_shows_day_off(self):
        EmployeeDayOff.objects.create(
            employee=self.employee,
            start_date=self.selected_date,
            end_date=self.selected_date,
        )

        text = build_daily_attendance_message(self.selected_date)

        self.assertIn('Day Off Employee', text)
        self.assertIn('Статус: <b>Выходной</b>', text)
        self.assertNotIn('Статус: <b>Не пришел</b>', text)

    def test_admin_can_add_range_and_remove_it_by_contained_date(self):
        end_date = self.selected_date + timedelta(days=2)

        add_employee_day_off(self.employee.id, self.selected_date, end_date)
        self.assertTrue(EmployeeDayOff.objects.filter(
            employee=self.employee,
            start_date=self.selected_date,
            end_date=end_date,
        ).exists())

        remove_employee_day_off(self.employee.id, self.selected_date + timedelta(days=1))
        self.assertFalse(EmployeeDayOff.objects.filter(employee=self.employee).exists())


class ConfigurableNetworkTests(TestCase):
    @override_settings(ATTENDANCE_NETWORK='10.20.30.0/24')
    def test_dashboard_uses_network_from_settings(self):
        expected = UnknownDevice.objects.create(
            ip_address='10.20.30.15',
            mac_address='02:11:22:33:44:55',
        )
        UnknownDevice.objects.create(
            ip_address='192.168.1.15',
            mac_address='02:aa:bb:cc:dd:ee',
        )

        context = _dashboard_context(timezone.localdate())

        self.assertEqual([device.id for device in context['unknown_devices']], [expected.id])
        self.assertEqual(context['unknown_count'], 1)
