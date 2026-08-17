# Установка на новый компьютер

## Что установить

1. Python 3.12 или новее: https://www.python.org/downloads/
   При установке включите галочку `Add python.exe to PATH`.
2. Git: https://git-scm.com/download/win

## Перенос проекта

Вариант 1: скачать с GitHub.

```powershell
git clone https://github.com/Shakhriyor10/automatical.git
cd automatical
```

Вариант 2: просто скопировать всю папку проекта на новый компьютер.

Если хотите перенести текущих сотрудников, устройства и историю, обязательно скопируйте файл:

```text
db.sqlite3
```

## Установка зависимостей

Откройте PowerShell в папке проекта:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
```

## Настройка Telegram

Создайте файл `.env` рядом с `manage.py`.
Можно скопировать `.env.example` и переименовать в `.env`.

Главное заполнить:

```text
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
ATTENDANCE_NETWORK=192.168.1.0/24
ATTENDANCE_GATEWAY_IP=192.168.1.1
TELEGRAM_LATE_ALERT_CHAT_ID=id_вашей_группы
TELEGRAM_SCAN_INTERVAL_SECONDS=10
TELEGRAM_LATE_ALERT_REPEAT_MINUTES=30
```

Для другой компании сначала выполните `ipconfig`. Если IPv4-адрес, например, `192.168.0.25`, а шлюз `192.168.0.1`, запишите в `.env`:

```text
ATTENDANCE_NETWORK=192.168.0.0/24
ATTENDANCE_GATEWAY_IP=192.168.0.1
```

После изменения `.env` перезапустите веб-сервер и Telegram-бота.

Если группа не получает сообщения, проверьте `chat_id`.
У супергрупп Telegram id часто выглядит как `-1001234567890`.

## Ручной запуск

Запустить все сразу:

```powershell
.\start_all.bat
```

Или отдельно:

```powershell
.\start_server.bat
.\start_bot.bat
```

Панель будет здесь:

```text
http://127.0.0.1:8088/
```

С другого компьютера в той же Wi-Fi сети:

```text
http://IP_КОМПЬЮТЕРА:8088/
```

IP компьютера можно посмотреть так:

```powershell
ipconfig
```

Ищите строку `IPv4-адрес`, например `192.168.1.9`.
Тогда с другого компьютера открывайте:

```text
http://192.168.1.9:8088/
```

## Автозапуск при включении компьютера

Откройте PowerShell от имени администратора в папке проекта и выполните:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\install_autostart.ps1
```

После этого при входе в Windows автоматически и в фоне, без окон командной строки, запустятся:

- Django web server на `0.0.0.0:8088`
- Telegram bot с автосканом Wi-Fi
- Watchdog, который каждую минуту проверяет, что сервер и bot живы

Автозапуск использует `run_hidden.vbs`, чтобы PowerShell-окна не мигали на экране.

Скрипт также откроет порт `8088` в Windows Firewall для частных/доменных сетей.
Если запускаете без автозапуска, порт можно открыть отдельно:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\open_firewall_8088.ps1
```

Логи будут сохраняться в файлы:

- `web_server.out.log`
- `web_server.err.log`
- `telegram_bot.out.log`
- `telegram_bot.err.log`
- `watchdog.log`

Для ручного фонового запуска без окон:

```powershell
.\start_all_hidden.ps1
```

## Проверка автозапуска

В PowerShell:

```powershell
Get-ScheduledTask -TaskName "Automatical Web Server"
Get-ScheduledTask -TaskName "Automatical Telegram Bot"
Get-ScheduledTask -TaskName "Automatical Watchdog"
```

Чтобы отключить автозапуск:

```powershell
.\uninstall_autostart.ps1
```

## Важно

- Новый компьютер должен быть подключен к тому же Wi-Fi.
- Телефоны сотрудников должны быть в этой Wi-Fi сети.
- У сотрудников желательно отключить рандомизацию MAC для рабочей сети.
- Если база не перенесена, сотрудников и устройства нужно добавить заново.

## Если пропал Wi-Fi или интернет

- Если Wi-Fi временно пропал или ноутбук не видит сеть, система не должна сразу записывать всем `уход`.
  Скан защищен от плохих сканов: если сеть почти пустая, checkout не записывается.
- Если интернет пропал, Telegram bot продолжит работать локально и будет пытаться переподключиться к Telegram.
  Когда интернет вернется, bot сам продолжит отвечать и отправлять групповые предупреждения.
- Если сам процесс сервера или Telegram bot упал, `Automatical Watchdog` поднимет его снова в течение примерно 1 минуты.
- Если предупреждение нужно изменить на `Сотрудник пришел`, но в момент прихода не было интернета,
  bot попробует изменить это сообщение позже, когда связь с Telegram вернется.
- Если свет пропал и компьютер выключился, система начнет работать снова после включения Windows и входа в пользователя.
  Для запуска до входа пользователя нужно настроить задачу Windows как `Run whether user is logged on or not` или включить автоматический вход Windows.
- Логи ошибок:

```text
web_server.err.log
telegram_bot.err.log
watchdog.log
```
