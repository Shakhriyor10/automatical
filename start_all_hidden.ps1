$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $ProjectDir "start_web_hidden.ps1")
& (Join-Path $ProjectDir "start_bot_hidden.ps1")

Write-Host "Automatical started in background."
