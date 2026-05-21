@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*manage.py*runserver*8088*' -and $_.CommandLine -notlike '*Get-CimInstance*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
".venv\Scripts\python.exe" manage.py runserver 0.0.0.0:8088 --noreload
