param(
    [switch]$RefreshOnly,
    [switch]$IncludeLive
)

$ErrorActionPreference = 'Stop'
$taskName = 'MOSS Transcribe Diarize - Start and refresh LAN forwarding'
$scriptPath = 'D:\Coding\MOSS-Transcribe-Diarize\ops\configure-windows-network.ps1'

# One row per forwarded port. The batch row is what this script has always forwarded and is
# never conditional: the plaintext batch service must keep working whatever the live service
# does. The live service is a separate WSL unit on its own TLS port, so it is forwarded only
# when a deployment asks for it with -IncludeLive.
$forwards = @(
    [pscustomobject]@{
        Port        = 7860
        RuleName    = 'MOSS-Transcribe-Diarize-Web'
        DisplayName = 'MOSS Transcribe Diarize web app'
        Services    = @('moss-vllm.service', 'moss-web.service')
    }
)
if ($IncludeLive) {
    $forwards += [pscustomobject]@{
        Port        = 7861
        RuleName    = 'MOSS-Transcribe-Diarize-Live'
        DisplayName = 'MOSS Transcribe Diarize live web app (TLS)'
        Services    = @('moss-live-web.service')
    }
}

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

foreach ($forward in $forwards) {
    $listenPort = $forward.Port
    & netsh.exe interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$listenPort 2>$null | Out-Null
    & netsh.exe interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$listenPort connectaddress=$wslAddress connectport=$listenPort | Out-Null

    if (-not (Get-NetFirewallRule -Name $forward.RuleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule `
            -Name $forward.RuleName `
            -DisplayName $forward.DisplayName `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $listenPort `
            -Profile Private | Out-Null
    }
}

$services = $forwards | ForEach-Object { $_.Services } | Select-Object -Unique
& wsl.exe -d Ubuntu -- systemctl --user start @services

if (-not $RefreshOnly) {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $argumentList = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -RefreshOnly"
    if ($IncludeLive) {
        $argumentList += ' -IncludeLive'
    }
    $action = New-ScheduledTaskAction `
        -Execute 'powershell.exe' `
        -Argument $argumentList
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

foreach ($forward in $forwards) {
    Write-Output "LAN forwarding ready: 0.0.0.0:$($forward.Port) -> ${wslAddress}:$($forward.Port)"
}
