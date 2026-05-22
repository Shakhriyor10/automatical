$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$WScript = Join-Path $env:SystemRoot "System32\wscript.exe"
$HiddenRunner = Join-Path $ProjectDir "run_hidden.vbs"
$WebScript = Join-Path $ProjectDir "start_web_hidden.ps1"
$BotScript = Join-Path $ProjectDir "start_bot_hidden.ps1"
$WatchdogScript = Join-Path $ProjectDir "ensure_automatical.ps1"
$FirewallScript = Join-Path $ProjectDir "open_firewall_8088.ps1"

if (-not (Test-Path $HiddenRunner)) {
    throw "Missing file: $HiddenRunner"
}

if (-not (Test-Path $WebScript)) {
    throw "Missing file: $WebScript"
}

if (-not (Test-Path $BotScript)) {
    throw "Missing file: $BotScript"
}

if (-not (Test-Path $WatchdogScript)) {
    throw "Missing file: $WatchdogScript"
}

if (Test-Path $FirewallScript) {
    & $FirewallScript
}

$WebAction = New-ScheduledTaskAction `
    -Execute $WScript `
    -Argument "//B //Nologo `"$HiddenRunner`" `"$WebScript`"" `
    -WorkingDirectory $ProjectDir

$BotAction = New-ScheduledTaskAction `
    -Execute $WScript `
    -Argument "//B //Nologo `"$HiddenRunner`" `"$BotScript`"" `
    -WorkingDirectory $ProjectDir

$WatchdogAction = New-ScheduledTaskAction `
    -Execute $WScript `
    -Argument "//B //Nologo `"$HiddenRunner`" `"$WatchdogScript`"" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Trigger.Delay = "PT30S"
$StartupTrigger = New-ScheduledTaskTrigger -AtStartup
$StartupTrigger.Delay = "PT30S"

$WatchdogTrigger = New-ScheduledTaskTrigger -AtLogOn
$WatchdogTrigger.Delay = "PT60S"

$WatchdogStartupTrigger = New-ScheduledTaskTrigger -AtStartup
$WatchdogStartupTrigger.Delay = "PT60S"

$WatchdogRepeatTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -Hidden `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName "Automatical Web Server" `
    -Action $WebAction `
    -Trigger $Trigger,$StartupTrigger `
    -Settings $Settings `
    -Description "Starts Automatical Django web server on login." `
    -Force

Register-ScheduledTask `
    -TaskName "Automatical Telegram Bot" `
    -Action $BotAction `
    -Trigger $Trigger,$StartupTrigger `
    -Settings $Settings `
    -Description "Starts Automatical Telegram bot and Wi-Fi scanner on login." `
    -Force

Register-ScheduledTask `
    -TaskName "Automatical Watchdog" `
    -Action $WatchdogAction `
    -Trigger $WatchdogTrigger,$WatchdogStartupTrigger,$WatchdogRepeatTrigger `
    -Settings $Settings `
    -Description "Keeps Automatical web server and Telegram bot running." `
    -Force

Write-Host "Autostart installed."
Write-Host "Used PowerShell: $PowerShell"
Write-Host "Used hidden runner: $HiddenRunner"
Write-Host "Tasks:"
Write-Host "- Automatical Web Server"
Write-Host "- Automatical Telegram Bot"
Write-Host "- Automatical Watchdog"
