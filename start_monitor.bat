@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*manage.py*monitor_wifi_attendance*' -and $_.CommandLine -notlike '*Get-CimInstance*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
".venv\Scripts\python.exe" manage.py monitor_wifi_attendance --interval 10 --absence-seconds 60 --misses-before-checkout 1
