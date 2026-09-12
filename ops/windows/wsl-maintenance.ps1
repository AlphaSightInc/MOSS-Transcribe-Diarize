# UNTESTED ON WINDOWS: 2.1 must validate after host recovery, outside any attempt.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('set-sparse', 'move', 'compact-check')]
    [string]$Action,
    [string]$Destination,
    [string]$Distro = 'Ubuntu',
    [ValidateNotNullOrEmpty()]
    [string[]]$KeepaliveTasks = @('MinerU-WSL-Keepalive', 'MinerU-Windows-Watchdog'),
    [switch]$DryRun,
    [switch]$Force,
    [string]$Acknowledgement,
    [string]$LogDirectory = (Join-Path $env:LOCALAPPDATA 'MOSS\maintenance')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows only; no maintenance performed.' }
if (-not $DryRun -and (-not $Force -or $Acknowledgement -cne 'no cutover attempt is running')) {
    throw 'REFUSED: require -Force -Acknowledgement "no cutover attempt is running" after release-owner confirmation. Never interrupt a cutover protecting moss-web.'
}
if ($Action -eq 'move' -and [string]::IsNullOrWhiteSpace($Destination)) {
    throw 'move requires -Destination.'
}
if ($Action -ne 'move' -and $Destination) { throw '-Destination is only valid for move.' }
if ($Action -eq 'move' -and $Destination -notmatch '^[A-Za-z]:\\') {
    throw 'Destination must be an absolute local Windows drive path.'
}

$started = Get-Date
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$script:LogPath = Join-Path $LogDirectory ("wsl-maintenance-{0}-{1}.jsonl" -f $started.ToString('yyyyMMddTHHmmssfff'), $PID)
function Write-Record([string]$Stage, [hashtable]$Fields = @{}) {
    $record = @{ timestamp = (Get-Date).ToString('o'); stage = $Stage }
    foreach ($key in $Fields.Keys) { $record[$key] = $Fields[$key] }
    $line = $record | ConvertTo-Json -Compress -Depth 5
    Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

# The one shipped Windows launcher which starts WSL. Attribution is deliberately
# narrower than a project-name substring. See README; do not add generic shells.
$script:ToolPattern = '(?i)(?:^|\s)-File\s+(?:"[^"]*|[^\s"]*)[\\/]MOSS-Transcribe-Diarize(?:-wt-[^\\/"\s]+)?[\\/]ops[\\/]configure-windows-network\.ps1(?:"|\s|$)'
function Get-Launchers {
    $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $byId = @{}
    foreach ($process in $processes) { $byId[[int]$process.ProcessId] = $process }
    foreach ($process in $processes) {
        if ([int]$process.ProcessId -eq $PID) { continue }
        $command = [string]$process.CommandLine
        # A wsl.exe with unreadable arguments is unknown, never assumed harmless.
        if ($command -notmatch '(?i)\bwsl\.exe\b' -and $process.Name -ine 'wsl.exe') { continue }
        $parent = $byId[[int]$process.ParentProcessId]
        $controllerId = 0
        $allowed = $process.Name -in @('powershell.exe', 'pwsh.exe') -and $command -match $script:ToolPattern
        if (-not $allowed -and $null -ne $parent -and $parent.Name -in @('powershell.exe', 'pwsh.exe') -and [string]$parent.CommandLine -match $script:ToolPattern) {
            $allowed = $true
            $controllerId = [int]$parent.ProcessId
        }
        [pscustomobject]@{
            Id = [int]$process.ProcessId; Name = [string]$process.Name
            ParentId = [int]$process.ParentProcessId; ControllerId = $controllerId
            Allowed = [bool]$allowed
        }
    }
}

function Report-Launchers($Launchers) {
    foreach ($launcher in $Launchers) {
        Write-Record 'launcher' @{ pid = $launcher.Id; parent_pid = $launcher.ParentId;
            process_name = $launcher.Name; controller_pid = $launcher.ControllerId;
            attribution = $(if ($launcher.Allowed) { 'repo-network-setup' } else { 'unknown' }) }
    }
}

function Stop-OwnedLaunchers {
    $launchers = @(Get-Launchers)
    Report-Launchers $launchers
    if (@($launchers | Where-Object { -not $_.Allowed }).Count -gt 0) {
        throw 'Unattributed WSL launcher: close it manually with its owner; nothing in this scan was killed.'
    }
    # Never terminate this wrapper or a shell/agent supervising it.
    $ancestors = @($PID)
    $cursor = $PID
    $snapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    while ($cursor -ne 0) {
        $row = @($snapshot | Where-Object { [int]$_.ProcessId -eq $cursor })
        if ($row.Count -ne 1) { break }
        $cursor = [int]$row[0].ParentProcessId
        if ($ancestors -contains $cursor) { break }
        $ancestors += $cursor
    }
    $stopIds = @($launchers | ForEach-Object {
        if ($_.ControllerId -ne 0) { $_.ControllerId }
        $_.Id
    } | Select-Object -Unique)
    foreach ($stopId in $stopIds) {
        if ($ancestors -contains $stopId) { throw 'Refused to stop a supervising process; close its launcher manually.' }
    }
    foreach ($stopId in $stopIds) {
        $live = Get-Process -Id $stopId -ErrorAction SilentlyContinue
        if ($null -ne $live) {
            Stop-Process -Id $stopId -Force -ErrorAction Stop
            Write-Record 'owned_launcher_stopped' @{ pid = $stopId }
        }
    }
}

function Invoke-Wsl([string[]]$Arguments) {
    # Capture output in memory; upstream/native error bodies are not retained.
    $output = @(& wsl.exe @Arguments 2>&1)
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "wsl command failed with exit code $code; no force-override attempted." }
    return (($output -join "`n") -replace "`0", '')
}

function Test-Stopped {
    $listing = Invoke-Wsl -Arguments @('--list', '--verbose')
    $pattern = '(?m)^\s*\*?\s*' + [regex]::Escape($Distro) + '\s+Stopped\s+2\s*$'
    $stopped = $listing -match $pattern
    $vmProcesses = @(Get-Process -Name 'vmmem*' -ErrorAction SilentlyContinue)
    Write-Record 'stopped_observation' @{ distro_stopped = $stopped; vmmem_count = $vmProcesses.Count }
    return ($stopped -and $vmProcesses.Count -eq 0)
}

function Wait-Stopped {
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $quietSince = -1.0
    while ($timer.Elapsed.TotalSeconds -lt 120) {
        $launchers = @(Get-Launchers)
        if ($launchers.Count -gt 0) {
            Report-Launchers $launchers
            throw 'A WSL launcher appeared during maintenance; refusing the disk operation.'
        }
        if (Test-Stopped) {
            if ($quietSince -lt 0) { $quietSince = $timer.Elapsed.TotalSeconds }
            if ($timer.Elapsed.TotalSeconds - $quietSince -ge 20) { return }
        } else { $quietSince = -1.0 }
        Start-Sleep -Seconds 1
    }
    throw 'Stopped state and absence of vmmem were not continuous for 20 seconds within 120 seconds.'
}

function Get-Disk {
    $entries = @(Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' |
        ForEach-Object { Get-ItemProperty -LiteralPath $_.PSPath } |
        Where-Object { $_.DistributionName -ceq $Distro })
    if ($entries.Count -ne 1) { throw 'Exactly one distro registration is required in the current Windows account.' }
    $entry = $entries[0]
    $name = 'ext4.vhdx'
    if ($null -ne $entry.PSObject.Properties['VhdFileName'] -and $entry.VhdFileName) { $name = $entry.VhdFileName }
    $base = [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($entry.BasePath))
    $image = Get-Item -LiteralPath (Join-Path $base $name) -ErrorAction Stop
    [pscustomobject]@{ Base = $base; Image = $image }
}

function Test-ExclusiveDisk($Disk) {
    # Read-only open, no shared handles; compact-check never changes VHD bytes.
    $handle = [System.IO.File]::Open($Disk.Image.FullName, [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)
    $handle.Dispose()
    Write-Record 'exclusive_disk_open_verified' @{ logical_bytes = $Disk.Image.Length }
}

$task = $null
$reenable = $false
$exitCode = 0
# All WSL shutdowns affect all distributions: only one maintenance wrapper may run.
$mutex = [System.Threading.Mutex]::new($false, 'Global\MOSS-WSL-Maintenance')
$ownsMutex = $false
try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) { throw 'Another MOSS maintenance wrapper owns the maintenance lock.' }
    Write-Record 'started' @{ started = $started.ToString('o'); action = $Action; distro = $Distro;
        dry_run = [bool]$DryRun; validation = 'untested_on_windows' }
    $task = @(foreach ($taskName in $KeepaliveTasks) {
        $taskMatches = @(Get-ScheduledTask -TaskName $taskName -ErrorAction Stop)
        if ($taskMatches.Count -ne 1) { throw 'Exactly one task must match each requested name; no task changes performed.' }
        $taskMatches[0]
    })
    $before = Get-Disk
    if ($Action -eq 'move' -and (Test-Path -LiteralPath $Destination)) {
        throw 'Move destination must not already exist; select a new directory on the approved drive.'
    }
    if ($DryRun) {
        $launchers = @(Get-Launchers)
        Report-Launchers $launchers
        if (@($launchers | Where-Object { -not $_.Allowed }).Count -gt 0) {
            throw 'Dry-run refusal: unknown WSL launchers require their owner to close them.'
        }
        Write-Record 'dry_run_plan' @{ disable_stop_keepalive = $true; shutdown = $true;
            stopped_seconds = 20; action = $Action; destination = $Destination;
            finally_reenable = $true; readiness_verified = $false }
    } else {
        # Set before Disable: even partial failure must attempt re-enablement.
        $reenable = $true
        $task | Disable-ScheduledTask | Out-Null
        $task | Stop-ScheduledTask
        Write-Record 'keepalive_disabled_and_stopped'
        Stop-OwnedLaunchers
        Write-Record 'shutdown_requested'
        $null = Invoke-Wsl -Arguments @('--shutdown')
        Wait-Stopped
        Test-ExclusiveDisk $before
        Write-Record 'action_started' @{ action = $Action }
        switch ($Action) {
            'set-sparse' { $null = Invoke-Wsl -Arguments @('--manage', $Distro, '--set-sparse', 'true') }
            'move' { $null = Invoke-Wsl -Arguments @('--manage', $Distro, '--move', $Destination) }
            'compact-check' { Write-Record 'compact_check_only_no_compaction' }
        }
        Wait-Stopped
        $after = Get-Disk
        Test-ExclusiveDisk $after
        if ($Action -eq 'set-sparse' -and
            (($after.Image.Attributes -band [System.IO.FileAttributes]::SparseFile) -eq 0)) {
            throw 'Sparse-file attribute verification failed.'
        }
        if ($Action -eq 'move') {
            $expected = [System.IO.Path]::GetFullPath($Destination).TrimEnd([char]92)
            $actual = $after.Base.Replace('\\?\', '').TrimEnd([char]92)
            if ($actual -ine $expected -or (Test-Path -LiteralPath $before.Image.FullName)) {
                throw 'Move verification failed: registration/destination or old VHD location disagrees.'
            }
        }
        Write-Record 'verified' @{ action = $Action; logical_bytes_before = $before.Image.Length;
            logical_bytes_after = $after.Image.Length; vhdx = $after.Image.FullName }
    }
} catch {
    $exitCode = 1
    # Fixed stage + exception type; no raw process command lines or native bodies.
    Write-Host ("FAILED: " + $_.Exception.Message)
    try { Write-Record 'failed' @{ exception_type = $_.Exception.GetType().Name } } catch { Write-Warning 'Failure log write failed.' }
} finally {
    if ($reenable -and $null -ne $task) {
        foreach ($taskToEnable in $task) {
            try {
                $taskToEnable | Enable-ScheduledTask | Out-Null
                $enabled = Get-ScheduledTask -TaskName $taskToEnable.TaskName -TaskPath $taskToEnable.TaskPath
                if ($enabled.State -eq 'Disabled') { throw 'Restart task remains disabled.' }
                Write-Record 'restart_task_reenabled' @{ task = $taskToEnable.TaskName }
            } catch {
                $exitCode = 1
                Write-Warning ("TASK RE-ENABLE NOT CONFIRMED: check and re-enable manually: " + $taskToEnable.TaskName)
            }
        }
    }
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
    Write-Host ("Maintenance log: " + $script:LogPath)
}
exit $exitCode
