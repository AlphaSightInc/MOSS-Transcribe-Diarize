param(
    [switch]$RefreshOnly
)

$ErrorActionPreference = 'Stop'
$listenPort = 7860
$ruleName = 'MOSS-Transcribe-Diarize-Web'
$taskName = 'MOSS Transcribe Diarize - Start and refresh LAN forwarding'
$scriptPath = 'D:\Coding\MOSS-Transcribe-Diarize\ops\configure-windows-network.ps1'

$wslAddress = $null
for ($attempt = 1; $attempt -le 20 -and -not $wslAddress; $attempt++) {
    $addressOutput = (& wsl.exe -d Ubuntu -- hostname -I 2>$null) -join ' '
    $wslAddress = [regex]::Match($addressOutput, '(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])').Value
    if (-not $wslAddress) {
        Start-Sleep -Seconds 2
    }
}
if (-not $wslAddress) {
    throw 'Could not determine the Ubuntu WSL IPv4 address.'
}

& netsh.exe interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$listenPort 2>$null | Out-Null
& netsh.exe interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$listenPort connectaddress=$wslAddress connectport=$listenPort | Out-Null

if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule `
        -Name $ruleName `
        -DisplayName 'MOSS Transcribe Diarize web app' `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $listenPort `
        -Profile Private | Out-Null
}

& wsl.exe -d Ubuntu -- systemctl --user start moss-vllm.service moss-web.service

if (-not $RefreshOnly) {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction `
        -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -RefreshOnly"
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Description 'Starts MOSS in WSL and refreshes the LAN port forward after sign-in.' `
        -Force | Out-Null
}

Write-Output "LAN forwarding ready: 0.0.0.0:${listenPort} -> ${wslAddress}:${listenPort}"

