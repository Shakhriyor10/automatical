from datetime import date, datetime, time
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import AttendanceEvent, DailyAttendanceReport, Employee, LateNotification
from .telegram_bot import build_daily_report_action, build_late_alert_actions


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
