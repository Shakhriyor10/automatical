import asyncio
import contextlib
import os
from pathlib import Path
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

from attendance.telegram_bot import (
    build_daily_report_action,
    build_late_alert_actions,
    mark_late_notification_resolved,
    router,
    run_scan,
    save_daily_report_content,
    save_daily_report_message,
    save_late_notification_message,
)


class Command(BaseCommand):
    help = 'Runs the Telegram attendance bot.'

    def add_arguments(self, parser):
        parser.add_argument('--token', default=None, help='Telegram bot token. Can also be set in .env as TELEGRAM_BOT_TOKEN.')
        parser.add_argument('--scan-interval', type=int, default=None, help='Background Wi-Fi scan interval in seconds.')
        parser.add_argument('--late-alert-chat-id', default=None, help='Telegram group chat id for late alerts.')
        parser.add_argument('--late-alert-start-time', default=None, help='Optional HH:MM test time that overrides employee schedule.')

    def handle(self, *args, **options):
        load_env_file(Path(settings.BASE_DIR) / '.env')
        token = options['token'] or os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('BOT_TOKEN')
        if not token:
            raise CommandError('Telegram token is missing. Add TELEGRAM_BOT_TOKEN=... to .env or run with --token.')
        if token == 'PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE':
            raise CommandError('Replace TELEGRAM_BOT_TOKEN in .env with the real token from @BotFather.')

        allowed_user_ids = parse_allowed_user_ids(os.environ.get('TELEGRAM_ALLOWED_USER_IDS', ''))
        admin_user_ids = parse_allowed_user_ids(os.environ.get('TELEGRAM_ADMIN_USER_IDS', ''))
        scan_interval = options['scan_interval'] or int(os.environ.get('TELEGRAM_SCAN_INTERVAL_SECONDS', '10'))
        scan_interval = max(scan_interval, 5)
        late_alert_chat_id = options['late_alert_chat_id'] or os.environ.get('TELEGRAM_LATE_ALERT_CHAT_ID', '')
        late_alert_start_time = parse_optional_time(
            options['late_alert_start_time'] or os.environ.get('TELEGRAM_LATE_ALERT_START_TIME', '')
        )
        late_alert_check_interval = int(os.environ.get('TELEGRAM_LATE_ALERT_CHECK_INTERVAL_SECONDS', '30'))
        late_alert_check_interval = max(late_alert_check_interval, 5)
        daily_report_chat_id = os.environ.get('TELEGRAM_DAILY_REPORT_CHAT_ID', '') or late_alert_chat_id
        daily_report_time = parse_required_time(os.environ.get('TELEGRAM_DAILY_REPORT_TIME', '09:00'), 'TELEGRAM_DAILY_REPORT_TIME')
        daily_report_check_interval = max(int(os.environ.get('TELEGRAM_DAILY_REPORT_CHECK_INTERVAL_SECONDS', '10')), 5)

        self.stdout.write(self.style.SUCCESS('Telegram bot started. Press Ctrl+C to stop.'))
        self.stdout.write(f'Background Wi-Fi scan interval: {scan_interval} seconds.')
        if late_alert_chat_id:
            self.stdout.write(f'Late alerts chat id: {late_alert_chat_id}.')
            if late_alert_start_time:
                self.stdout.write(f'Late alert test start time: {late_alert_start_time:%H:%M}.')
            self.stdout.write('Late alerts: one warning per employee per day.')
        else:
            self.stdout.write(self.style.WARNING('TELEGRAM_LATE_ALERT_CHAT_ID is empty. Group late alerts are disabled.'))
        if daily_report_chat_id:
            self.stdout.write(
                f'Daily attendance report: after {daily_report_time:%H:%M} '
                f'to chat {daily_report_chat_id}.'
            )
        else:
            self.stdout.write(self.style.WARNING('Daily attendance report is disabled because group chat id is empty.'))
        if allowed_user_ids:
            self.stdout.write(f'Allowed Telegram users: {", ".join(map(str, sorted(allowed_user_ids)))}')
        else:
            self.stdout.write(self.style.WARNING('TELEGRAM_ALLOWED_USER_IDS is empty. Bot is available to anyone who knows it.'))
        if admin_user_ids:
            self.stdout.write(f'Telegram bot admins: {", ".join(map(str, sorted(admin_user_ids)))}')
        else:
            self.stdout.write(self.style.WARNING('TELEGRAM_ADMIN_USER_IDS is empty. Bot admin settings are disabled.'))

        asyncio.run(run_bot_forever(
            token=token,
            allowed_user_ids=allowed_user_ids,
            admin_user_ids=admin_user_ids,
            scan_interval=scan_interval,
            late_alert_chat_id=late_alert_chat_id,
            late_alert_start_time=late_alert_start_time,
            late_alert_check_interval=late_alert_check_interval,
            daily_report_chat_id=daily_report_chat_id,
            daily_report_time=daily_report_time,
            daily_report_check_interval=daily_report_check_interval,
        ))


async def run_bot_forever(**kwargs):
    reconnect_delay = 5
    while True:
        try:
            await run_bot_once(**kwargs)
            reconnect_delay = 5
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f'Telegram bot stopped by error: {exc}')
            print(f'Reconnecting in {reconnect_delay} seconds...')
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)


async def run_bot_once(
    token,
    allowed_user_ids,
    admin_user_ids,
    scan_interval,
    late_alert_chat_id,
    late_alert_start_time,
    late_alert_check_interval,
    daily_report_chat_id,
    daily_report_time,
    daily_report_check_interval,
):
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(allowed_user_ids=allowed_user_ids, admin_user_ids=admin_user_ids)
    dispatcher.include_router(router)
    tasks = [asyncio.create_task(background_scanner(scan_interval))]
    if late_alert_chat_id:
        tasks.append(asyncio.create_task(background_late_alerts(
            bot=bot,
            chat_id=late_alert_chat_id,
            alert_start_time=late_alert_start_time,
            interval=late_alert_check_interval,
        )))
    if daily_report_chat_id:
        tasks.append(asyncio.create_task(background_daily_report(
            bot=bot,
            chat_id=daily_report_chat_id,
            send_time=daily_report_time,
            interval=daily_report_check_interval,
        )))
    try:
        await dispatcher.start_polling(bot)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await bot.session.close()


async def background_scanner(interval):
    while True:
        try:
            await asyncio.to_thread(run_scan)
        except Exception as exc:
            print(f'Wi-Fi scan failed: {exc}')
        await asyncio.sleep(interval)


async def background_late_alerts(bot, chat_id, alert_start_time, interval):
    while True:
        try:
            actions = await asyncio.to_thread(build_late_alert_actions, chat_id, alert_start_time)
            for action in actions:
                if action['type'] == 'send_warning':
                    try:
                        message = await bot.send_message(chat_id=chat_id, text=action['text'])
                    except Exception as exc:
                        print(f'Late alert send failed: {exc}')
                        continue
                    await asyncio.to_thread(save_late_notification_message, action['notification_id'], message.message_id)
                elif action['type'] == 'delete_warning':
                    delivered = False
                    try:
                        await bot.delete_message(
                            chat_id=chat_id,
                            message_id=action['message_id'],
                        )
                        delivered = True
                    except TelegramBadRequest as exc:
                        if 'message to delete not found' in str(exc).lower():
                            delivered = True
                        else:
                            print(f'Late alert delete failed: {exc}')
                    except Exception as exc:
                        print(f'Late alert delete failed: {exc}')
                    if delivered:
                        await asyncio.to_thread(mark_late_notification_resolved, action['notification_id'])
                elif action['type'] == 'resolve_undelivered':
                    await asyncio.to_thread(mark_late_notification_resolved, action['notification_id'])
        except Exception as exc:
            print(f'Late alert loop failed: {exc}')
        await asyncio.sleep(interval)


async def background_daily_report(bot, chat_id, send_time, interval):
    while True:
        try:
            action = await asyncio.to_thread(
                build_daily_report_action,
                chat_id,
                send_time,
            )
            if action and action['type'] == 'send':
                try:
                    message = await bot.send_message(chat_id=chat_id, text=action['text'])
                except Exception as exc:
                    print(f'Daily report send failed: {exc}')
                else:
                    await asyncio.to_thread(
                        save_daily_report_message,
                        action['report_id'],
                        message.message_id,
                        action['text'],
                    )
            elif action and action['type'] == 'edit':
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=action['message_id'],
                        text=action['text'],
                    )
                except Exception as exc:
                    print(f'Daily report edit failed: {exc}')
                else:
                    await asyncio.to_thread(save_daily_report_content, action['report_id'], action['text'])
        except Exception as exc:
            print(f'Daily report loop failed: {exc}')
        await asyncio.sleep(interval)


def load_env_file(path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def parse_allowed_user_ids(value):
    user_ids = set()
    for item in value.split(','):
        item = item.strip()
        if not item:
            continue
        try:
            user_ids.add(int(item))
        except ValueError as exc:
            raise CommandError(f'Invalid TELEGRAM_ALLOWED_USER_IDS value: {item}') from exc
    return user_ids


def parse_optional_time(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%H:%M').time()
    except ValueError as exc:
        raise CommandError('TELEGRAM_LATE_ALERT_START_TIME must be in HH:MM format, for example 09:20.') from exc


def parse_required_time(value, variable_name):
    try:
        return datetime.strptime(value.strip(), '%H:%M').time()
    except ValueError as exc:
        raise CommandError(f'{variable_name} must be in HH:MM format, for example 09:00.') from exc
