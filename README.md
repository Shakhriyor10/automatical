# Automatical

Локальная Django-система для учета прихода и ухода сотрудников автосалона по Wi-Fi устройствам.

## Как это работает

1. Ноутбук находится в той же Wi-Fi сети, что и телефоны сотрудников.
2. Команда `scan_wifi_attendance` сканирует сеть `192.168.1.0/24`.
3. Если MAC-адрес устройства привязан к сотруднику, система фиксирует приход.
4. Если устройство не видно дольше заданного времени, система фиксирует уход.
5. Неизвестные устройства сохраняются отдельно, чтобы их можно было привязать к сотрудникам через админку.

Пароль от роутера в код не добавлен специально. Для этой версии доступ к админке роутера не нужен.

## Установка

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

## Запуск панели

```powershell
python manage.py runserver 0.0.0.0:8000
```

На этом проекте удобнее запускать готовым файлом:

```powershell
.\start_server.bat
```

Панель: `http://127.0.0.1:8000/`

Админка: `http://127.0.0.1:8000/admin/`

В админке нужно добавить сотрудников и их устройства. Главное поле для учета - `MAC-адрес`.

## Ручной запуск сканирования

```powershell
python manage.py scan_wifi_attendance
```

Если нужно изменить сеть:

```powershell
python manage.py scan_wifi_attendance --network 192.168.1.0/24
```

Если сотрудник вышел из Wi-Fi и его устройство не видно 5 минут, будет записан уход. Таймаут можно изменить:

```powershell
python manage.py scan_wifi_attendance --absence-seconds 300
```

## Постоянный мониторинг

Чтобы система сама записывала каждый приход и уход, оставьте эту команду запущенной на ноутбуке:

```powershell
python manage.py monitor_wifi_attendance --interval 30 --absence-seconds 300 --misses-before-checkout 12
```

Или готовым файлом:

```powershell
.\start_monitor.bat
```

Система будет сканировать Wi-Fi каждые 30 секунд. Если сотрудник вышел из сети и не виден примерно 5 минут, будет записан уход. Если он снова появился, будет записан новый приход.

## Автоматический запуск каждые 2 минуты

Откройте PowerShell от имени администратора в папке проекта и выполните:

```powershell
$project = (Get-Location).Path
$python = Join-Path $project ".venv\Scripts\python.exe"
$action = New-ScheduledTaskAction -Execute $python -Argument "manage.py scan_wifi_attendance" -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName "Automatical WiFi Attendance" -Action $action -Trigger $trigger -Description "Scans Wi-Fi devices and records employee attendance"
```

## Важные ограничения

- На телефонах может быть включена рандомизация MAC-адреса. Для рабочего Wi-Fi ее лучше отключить, иначе телефон может определяться как новое устройство.
- Устройство считается присутствующим, пока оно периодически видно в сети.
- Для точности ноутбук должен быть постоянно включен и подключен к этой же Wi-Fi сети.
- Перед использованием сотрудников нужно уведомить о таком учете, потому что это персональные данные.
