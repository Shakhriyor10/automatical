$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$OutLog = Join-Path $ProjectDir "telegram_bot.out.log"
$ErrLog = Join-Path $ProjectDir "telegram_bot.err.log"

if (-not (Test-Path $Python)) {
    throw "Python not found: $Python"
}

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*manage.py*run_telegram_bot*" -and $_.CommandLine -notlike "*Get-CimInstance*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Process `
    -WindowStyle Hidden `
    -FilePath $Python `
    -ArgumentList "manage.py run_telegram_bot" `
    -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog
