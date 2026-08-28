param([switch]$RefreshOnly)
$ErrorActionPreference = 'Stop'
$taskName = 'MOSS Transcribe Diarize - Start and refresh LAN forwarding'
$scriptPath = 'D:\Coding\MOSS-Transcribe-Diarize\ops\configure-windows-network.ps1'
$port = 7861
$ruleName = 'MOSS-Transcribe-Diarize-Account'

$networkingMode = ((& wsl.exe -d Ubuntu -- wslinfo --networking-mode 2>$null) -join '').Trim()
if (-not $networkingMode) { $networkingMode = 'nat' }
$usesPortProxy = $networkingMode -ne 'mirrored'
$wslAddress = $null
if ($usesPortProxy) {
    for ($attempt = 1; $attempt -le 20 -and -not $wslAddress; $attempt++) {
        $addressOutput = (& wsl.exe -d Ubuntu -- sh -lc 'ip -4 -o addr show dev eth0 scope global' 2>$null) -join ' '
        $wslAddress = [regex]::Match($addressOutput, '(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])').Value
        if (-not $wslAddress) { Start-Sleep -Seconds 2 }
    }
    if (-not $wslAddress) { throw 'Could not determine the Ubuntu WSL NAT IPv4 address.' }
}
& netsh.exe interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$port 2>$null | Out-Null
if ($usesPortProxy) {
    & netsh.exe interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$port connectaddress=$wslAddress connectport=$port | Out-Null
}
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'MOSS Account product (TLS)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private | Out-Null
}
& wsl.exe -d Ubuntu -- systemctl --user start moss-vllm.service moss-web.service
if (-not $RefreshOnly) {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -RefreshOnly"
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Description 'Starts MOSS and refreshes the TLS LAN forwarding.' -Force | Out-Null
}
Write-Output "MOSS Account TLS forwarding ready on port $port"
