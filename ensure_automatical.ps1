$ErrorActionPreference = "Continue"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$WatchdogLog = Join-Path $ProjectDir "watchdog.log"

function Write-WatchdogLog($Message) {
    $Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $WatchdogLog -Value "[$Stamp] $Message"
}

if (-not (Test-Path $Python)) {
    Write-WatchdogLog "Python not found: $Python"
    exit 1
}

$Processes = @(Get-CimInstance Win32_Process)

$WebRunning = $Processes | Where-Object {
    $_.CommandLine -like "*manage.py*runserver*8088*" -and
    $_.CommandLine -notlike "*Get-CimInstance*"
}

$BotRunning = $Processes | Where-Object {
    $_.CommandLine -like "*manage.py*run_telegram_bot*" -and
    $_.CommandLine -notlike "*Get-CimInstance*"
}

if (-not $WebRunning) {
    Write-WatchdogLog "Web server is not running. Starting..."
    Start-Process `
        -WindowStyle Hidden `
        -FilePath $Python `
        -ArgumentList "manage.py runserver 0.0.0.0:8088 --noreload" `
        -WorkingDirectory $ProjectDir `
        -RedirectStandardOutput (Join-Path $ProjectDir "web_server.out.log") `
        -RedirectStandardError (Join-Path $ProjectDir "web_server.err.log")
}

if (-not $BotRunning) {
    Write-WatchdogLog "Telegram bot is not running. Starting..."
    Start-Process `
        -WindowStyle Hidden `
        -FilePath $Python `
        -ArgumentList "manage.py run_telegram_bot" `
        -WorkingDirectory $ProjectDir `
        -RedirectStandardOutput (Join-Path $ProjectDir "telegram_bot.out.log") `
        -RedirectStandardError (Join-Path $ProjectDir "telegram_bot.err.log")
}

if ($WebRunning -and $BotRunning) {
    Write-WatchdogLog "OK"
}
