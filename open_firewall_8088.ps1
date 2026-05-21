$ErrorActionPreference = "Stop"

$RuleName = "Automatical Django 8088"
$ExistingRule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue

if ($ExistingRule) {
    Set-NetFirewallRule -DisplayName $RuleName -Enabled True -Profile Private,Domain
    Write-Host "Firewall rule already exists and is enabled: $RuleName"
} else {
    New-NetFirewallRule `
        -DisplayName $RuleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 8088 `
        -Profile Private,Domain | Out-Null
    Write-Host "Firewall rule created: $RuleName"
}

Write-Host "Port 8088 is open for Private/Domain networks."
