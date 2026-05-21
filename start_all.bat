@echo off
cd /d "%~dp0"

start "Automatical Web Server" cmd /k ".venv\Scripts\python.exe manage.py runserver 0.0.0.0:8088 --noreload"
start "Automatical Telegram Bot" cmd /k ".venv\Scripts\python.exe manage.py run_telegram_bot"

echo Web server: http://127.0.0.1:8088/
echo From another computer: http://YOUR_COMPUTER_IP:8088/
echo Telegram bot started.
pause
