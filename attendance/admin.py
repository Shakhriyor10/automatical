from django.contrib import admin

from .models import AttendanceEvent, DailyAttendanceReport, Device, Employee, LateNotification, Presence, UnknownDevice


class DeviceInline(admin.TabularInline):
    model = Device
    extra = 1


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'position', 'phone', 'telegram_user', 'work_start_time', 'late_grace_minutes', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('full_name', 'position', 'phone', 'telegram_user', 'devices__mac_address')
    inlines = (DeviceInline,)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'employee', 'mac_address', 'last_ip', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'employee__full_name', 'mac_address', 'last_ip')


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'status', 'first_seen_at', 'last_seen_at', 'last_left_at', 'last_ip')
    list_filter = ('status',)
    search_fields = ('employee__full_name', 'last_mac', 'last_ip')


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(admin.ModelAdmin):
    list_display = ('employee', 'event_type', 'observed_at', 'ip_address', 'mac_address')
    list_filter = ('event_type', 'observed_at')
    search_fields = ('employee__full_name', 'mac_address', 'ip_address')
    date_hierarchy = 'observed_at'


@admin.register(UnknownDevice)
class UnknownDeviceAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'mac_address', 'first_seen_at', 'last_seen_at', 'note')
    search_fields = ('ip_address', 'mac_address', 'note')


@admin.register(LateNotification)
class LateNotificationAdmin(admin.ModelAdmin):
    list_display = ('employee', 'alert_date', 'chat_id', 'message_id', 'alert_count', 'status', 'last_alert_at', 'resolved_at')
    list_filter = ('status', 'alert_date')
    search_fields = ('employee__full_name', 'chat_id', 'message_id')


@admin.register(DailyAttendanceReport)
class DailyAttendanceReportAdmin(admin.ModelAdmin):
    list_display = ('report_date', 'chat_id', 'message_id', 'sent_at', 'updated_at')
    list_filter = ('report_date',)
    search_fields = ('chat_id', 'message_id')
