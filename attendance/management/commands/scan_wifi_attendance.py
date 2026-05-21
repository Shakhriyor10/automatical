import ipaddress
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from attendance.models import AttendanceEvent, Device, Presence, UnknownDevice, normalize_mac


MIN_GOOD_SCAN_DEVICES = 5

ARP_ROW_RE = re.compile(
    r'(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+'
    r'(?P<mac>[0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})\s+'
    r'(?P<kind>\w+)'
)


class Command(BaseCommand):
    help = 'Scans the local Wi-Fi network and records employee check-in/check-out events.'

    def add_arguments(self, parser):
        parser.add_argument('--network', default=settings.ATTENDANCE_NETWORK)
        parser.add_argument('--absence-seconds', type=int, default=settings.ATTENDANCE_ABSENCE_SECONDS)
        parser.add_argument('--absence-minutes', type=int, default=None)
        parser.add_argument('--skip-ping', action='store_true')
        parser.add_argument('--strict-ping', action='store_true')
        parser.add_argument('--workers', type=int, default=64)
        parser.add_argument('--misses-before-checkout', type=int, default=1)

    def handle(self, *args, **options):
        now = timezone.now()
        network = ipaddress.ip_network(options['network'], strict=False)

        active_ips = None
        seen = self._read_arp_table(network, active_ips)
        if options['strict_ping'] and not options['skip_ping']:
            self.stdout.write(f'Scanning {self._format_network_range(network)}...')
            self._clear_arp_cache()
            active_ips = self._ping_sweep(network, options['workers'])
            seen = self._read_arp_table(network, active_ips)
        elif not options['skip_ping']:
            self.stdout.write(f'Scanning {self._format_network_range(network)}...')
            self._ping_sweep(network, options['workers'])
            seen.update(self._read_arp_table(network, active_ips))

        absence_seconds = options['absence_seconds']
        if options['absence_minutes'] is not None:
            absence_seconds = options['absence_minutes'] * 60

        stats = self._apply_seen_devices(seen, now, absence_seconds, options['misses_before_checkout'])

        self.stdout.write(
            self.style.SUCCESS(
                'Done: {seen} seen, {known} known, {unknown} unknown, '
                '{checkins} check-ins, {checkouts} check-outs'.format(**stats)
            )
        )

    def _ping_sweep(self, network, workers):
        hosts = [str(host) for host in network.hosts()]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = executor.map(self._ping, hosts)
        return {ip for ip, is_active in results if is_active}

    def _format_network_range(self, network):
        hosts = list(network.hosts())
        if not hosts:
            return str(network)

        first = hosts[0]
        last = hosts[-1]
        if first.version == 4:
            first_parts = str(first).split('.')
            last_parts = str(last).split('.')
            if first_parts[:3] == last_parts[:3]:
                return f"{'.'.join(first_parts[:3])}.{first_parts[3]}-{last_parts[3]}"

        return f'{first}-{last}'

    def _ping(self, ip):
        result = subprocess.run(
            ['ping', '-n', '1', '-w', '250', ip],
            stdout=subprocess.PIPE,
            text=True,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return ip, 'TTL=' in result.stdout.upper()

    def _is_ip_reachable(self, ip):
        if not ip:
            return False
        return self._ping(ip)[1]

    def _clear_arp_cache(self):
        subprocess.run(
            ['arp', '-d', '*'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    def _read_arp_table(self, network, active_ips):
        result = subprocess.run(
            ['arp', '-a'],
            capture_output=True,
            text=True,
            check=False,
        )
        devices = {}
        for line in result.stdout.splitlines():
            match = ARP_ROW_RE.search(line)
            if not match:
                continue
            mac = normalize_mac(match.group('mac'))
            ip = match.group('ip')
            if active_ips is not None and ip not in active_ips:
                continue
            if self._is_trackable_device(ip, mac, network):
                devices[mac] = ip
        return devices

    def _is_trackable_device(self, ip, mac, network):
        address = ipaddress.ip_address(ip)
        if address not in network:
            return False
        if address.is_multicast or address == network.broadcast_address or address.is_loopback:
            return False
        if mac == 'ff:ff:ff:ff:ff:ff':
            return False
        if mac.startswith('01:00:5e:'):
            return False
        return True

    @transaction.atomic
    def _apply_seen_devices(self, seen, now, absence_seconds, misses_before_checkout):
        timeout_before = now - timedelta(seconds=absence_seconds)
        today = timezone.localdate(now)
        day_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        day_end = day_start + timedelta(days=1)
        devices = list(Device.objects.select_related('employee').filter(is_active=True, employee__is_active=True))
        known_macs = {device.mac_address for device in devices}
        known_ips = {device.last_ip for device in devices if device.last_ip}
        seen_by_ip = {ip: mac for mac, ip in seen.items()}

        known_seen = {}
        checkins = 0
        unknown = 0

        for device in devices:
            observed = self._observe_registered_device(device, seen, seen_by_ip)
            if not observed:
                continue

            mac, ip = observed
            self._refresh_device_identity(device, mac, ip, known_macs)
            UnknownDevice.objects.filter(mac_address__in=[mac, device.mac_address]).delete()

            previous = known_seen.get(device.employee_id)
            if previous and previous[0].updated_at >= device.updated_at:
                continue
            known_seen[device.employee_id] = (device, mac, ip)

            presence, _ = Presence.objects.get_or_create(employee=device.employee)
            last_today_event = AttendanceEvent.objects.filter(
                employee=device.employee,
                observed_at__gte=day_start,
                observed_at__lt=day_end,
            ).order_by('-observed_at').first()

            if not last_today_event or last_today_event.event_type == AttendanceEvent.CHECK_OUT:
                checkins += 1
                AttendanceEvent.objects.create(
                    employee=device.employee,
                    device=device,
                    event_type=AttendanceEvent.CHECK_IN,
                    observed_at=now,
                    ip_address=ip,
                    mac_address=mac,
                )
                presence.first_seen_at = now
            elif not presence.first_seen_at:
                presence.first_seen_at = now

            presence.status = Presence.STATUS_PRESENT
            presence.device = device
            presence.last_seen_at = now
            presence.last_ip = ip
            presence.last_mac = mac
            presence.missed_scans = 0
            presence.save()

        for mac, ip in seen.items():
            if mac in known_macs or ip in known_ips:
                continue
            UnknownDevice.objects.update_or_create(mac_address=mac, defaults={'ip_address': ip})
            unknown += 1

        checkouts = 0
        if len(seen) < MIN_GOOD_SCAN_DEVICES:
            return {
                'seen': len(seen),
                'known': len(known_seen),
                'unknown': unknown,
                'checkins': checkins,
                'checkouts': checkouts,
            }

        stale_presences = Presence.objects.select_related('employee', 'device').filter(
            status=Presence.STATUS_PRESENT,
            last_seen_at__lt=timeout_before,
        )
        for presence in stale_presences:
            if presence.employee_id in known_seen:
                continue

            presence.missed_scans += 1
            if presence.missed_scans < misses_before_checkout:
                presence.save(update_fields=['missed_scans'])
                continue

            last_today_event = AttendanceEvent.objects.filter(
                employee=presence.employee,
                observed_at__gte=day_start,
                observed_at__lt=day_end,
            ).order_by('-observed_at').first()
            if not last_today_event or last_today_event.event_type == AttendanceEvent.CHECK_OUT:
                presence.status = Presence.STATUS_ABSENT
                presence.last_left_at = now
                presence.missed_scans = 0
                presence.save(update_fields=['status', 'last_left_at', 'missed_scans'])
                continue

            checkouts += 1
            AttendanceEvent.objects.create(
                employee=presence.employee,
                device=presence.device,
                event_type=AttendanceEvent.CHECK_OUT,
                observed_at=now,
                ip_address=presence.last_ip,
                mac_address=presence.last_mac,
            )
            presence.status = Presence.STATUS_ABSENT
            presence.last_left_at = now
            presence.missed_scans = 0
            presence.save(update_fields=['status', 'last_left_at', 'missed_scans'])

        return {
            'seen': len(seen),
            'known': len(known_seen),
            'unknown': unknown,
            'checkins': checkins,
            'checkouts': checkouts,
        }

    def _observe_registered_device(self, device, seen, seen_by_ip):
        if device.mac_address in seen:
            return device.mac_address, seen[device.mac_address]

        if device.last_ip in seen_by_ip:
            return seen_by_ip[device.last_ip], device.last_ip

        if self._is_ip_reachable(device.last_ip):
            return device.mac_address, device.last_ip

        return None

    def _refresh_device_identity(self, device, mac, ip, known_macs):
        update_fields = ['last_ip', 'updated_at']
        device.last_ip = ip

        if (
            mac
            and device.mac_address != mac
            and mac not in known_macs
            and not Device.objects.filter(mac_address=mac).exclude(pk=device.pk).exists()
        ):
            old_mac = device.mac_address
            device.mac_address = mac
            known_macs.discard(old_mac)
            known_macs.add(mac)
            update_fields.append('mac_address')

        device.save(update_fields=update_fields)
