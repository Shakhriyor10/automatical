import time
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

try:
    import msvcrt
except ImportError:
    msvcrt = None


class Command(BaseCommand):
    help = 'Continuously scans Wi-Fi and records employee attendance events.'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=10)
        parser.add_argument('--network', default=None)
        parser.add_argument('--absence-seconds', type=int, default=None)
        parser.add_argument('--absence-minutes', type=int, default=None)
        parser.add_argument('--misses-before-checkout', type=int, default=1)

    def handle(self, *args, **options):
        lock_file = None
        if msvcrt:
            lock_path = Path(settings.BASE_DIR) / '.attendance_monitor.lock'
            lock_file = lock_path.open('a+')
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.stdout.write(self.style.WARNING('Monitor is already running. Exiting this duplicate process.'))
                return

        interval = max(10, options['interval'])
        self.stdout.write(self.style.SUCCESS(f'Monitor started. Scan interval: {interval} seconds.'))

        try:
            while True:
                command_options = {}
                if options['network']:
                    command_options['network'] = options['network']
                if options['absence_seconds'] is not None:
                    command_options['absence_seconds'] = options['absence_seconds']
                if options['absence_minutes'] is not None:
                    command_options['absence_minutes'] = options['absence_minutes']
                command_options['misses_before_checkout'] = options['misses_before_checkout']
                command_options['skip_ping'] = False

                call_command('scan_wifi_attendance', **command_options)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Monitor stopped.'))
        finally:
            if lock_file:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                finally:
                    lock_file.close()
