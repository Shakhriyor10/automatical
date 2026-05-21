$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$OutLog = Join-Path $ProjectDir "web_server.out.log"
$ErrLog = Join-Path $ProjectDir "web_server.err.log"

if (-not (Test-Path $Python)) {
    throw "Python not found: $Python"
}

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*manage.py*runserver*8088*" -and $_.CommandLine -notlike "*Get-CimInstance*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Process `
    -WindowStyle Hidden `
    -FilePath $Python `
    -ArgumentList "manage.py runserver 0.0.0.0:8088 --noreload" `
    -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog
