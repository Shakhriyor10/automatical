$ErrorActionPreference = "SilentlyContinue"

Unregister-ScheduledTask -TaskName "Automatical Web Server" -Confirm:$false
Unregister-ScheduledTask -TaskName "Automatical Telegram Bot" -Confirm:$false
Unregister-ScheduledTask -TaskName "Automatical Watchdog" -Confirm:$false

Write-Host "Autostart removed."
