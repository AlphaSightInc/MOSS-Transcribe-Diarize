# WSL maintenance wrapper

**Windows dry-run refusal/non-mutation validated, 2026-09-12 08:48 EDT.**
Both `-Action compact-check -DryRun` and `-Action set-sparse -DryRun` executed
under Windows PowerShell as `gyauo`, without cmdlet, path or elevation errors.
Both returned **exit 1**, correctly refusing existing unknown `wsl.exe` launchers
(PIDs 85800 and 58692, parent chain 106140 → 85800 → 58692):

```text
FAILED: Dry-run refusal: unknown WSL launchers require their owner to close them.
```

Each JSONL log contains only `started` (`dry_run=true`), two `launcher` records,
and `failed` (`RuntimeException`). No `shutdown_requested`, task mutation,
`action_started`, or `restart_task_reenabled` records occurred. Source inspection
confirms the dry branch cannot call shutdown, task/process changes or `wsl --manage`;
it only writes its log and acquires/releases a temporary mutex. Both MinerU tasks
remained enabled/running, and VM process IDs/start times were identical before/after.
Logs: `D:\wsl\moss-dryrun-logs\wsl-maintenance-20260912T084824521-70860.jsonl`
and `wsl-maintenance-20260912T084825939-88188.jsonl` in the same directory.

**Successful dry-run plan and destructive maintenance paths remain unvalidated.**
The runtime's legacy `validation=untested_on_windows` field remains unchanged;
this scoped verification does not validate live sparse/move operations. No process
was stopped or allowlist broadened to make a dry-run pass.

`wsl-maintenance.ps1` handles the host's two known restart sources: the
`MinerU-WSL-Keepalive` / `MinerU-Windows-Watchdog` scheduled tasks and attributable
MOSS tooling launching `wsl.exe`. Recovery found that the two tasks can restart
Ubuntu (and WslService) within ~20 seconds of shutdown. Both must be temporarily
disabled/stopped for maintenance and re-enabled afterward. It never runs `wsl.exe -d Ubuntu`, opens a Linux shell, or queries a Linux
unit to establish offline state. All inspection uses Windows processes, the current
Windows account's WSL registration and `wsl --list --verbose`.

## Preconditions and procedure

1. **The release owner must confirm no cutover attempt is running.** An attempt
   protecting Phase-1's `moss-web` must be completed or recovered before maintenance.
   The wrapper deliberately cannot prove this by starting Ubuntu to inspect Linux.
   Every non-dry run requires both `-Force` and the exact, case-sensitive
   acknowledgement `no cutover attempt is running`. `-Force` alone refuses; it is
   never forwarded to WSL to bypass a sparse/move refusal.
2. Pull evidence bundles off the host and verify their copies before pruning any
   attempt. Follow [disk hygiene](../../docs/handoffs/g7-preadmission-runbook.md#host-disk-hygiene)
   and [bounded retention](../README.md). Arrange downtime and close editors,
   terminals, Docker/WSL clients and agent loops that can reopen a distro. Do not
   run another tool that invokes `wsl.exe -d Ubuntu` while this wrapper is active.
3. Run from a **Windows-local checkout**, not a `\\wsl$`/`\\wsl.localhost` path.
   Use elevated PowerShell under the Windows user who owns the distro and task;
   changing Windows accounts can select a different HKCU distro registration.
   First run the parser check below, then `-DryRun`. Inspect unknown-process
   refusals with the process owner; do not broaden the allowlist to make them pass.
4. Only after 2.1's review, select the action and pass the acknowledgement. Verify
   the timestamped log, task re-enablement and disk outcome. After maintenance,
   verify Phase-1 and vLLM/model readiness before creating any new attempt.

**Any `wsl --shutdown` stops all WSL distributions and their services, including
vLLM and Phase-1. Their restart is required; vLLM gets a new PID and must reload its
model. Never do this during an attempt.** The finally block re-enables keepalive,
so Ubuntu may restart immediately afterward. This script does not itself start
Phase-1 units or claim their readiness; use the release owner's recovery procedure.

## Commands (operator execution only)

```powershell
# Inventory/plan only; creates a log, changes no task/process/distro/disk state.
.\ops\windows\wsl-maintenance.ps1 -Action compact-check -DryRun

# Enable sparse reclamation; no WSL force override is used.
.\ops\windows\wsl-maintenance.ps1 -Action set-sparse -Force `
  -Acknowledgement 'no cutover attempt is running'

# Alternative: move to a NEW directory on an approved drive with enough room.
# D:\WSL\Ubuntu is an example, not a claim about this host's recovered location.
.\ops\windows\wsl-maintenance.ps1 -Action move -Destination 'D:\WSL\Ubuntu' -Force `
  -Acknowledgement 'no cutover attempt is running'
```

Parameters: `-Distro` defaults to `Ubuntu`; `-KeepaliveTasks` is a nonempty array
with defaults `MinerU-WSL-Keepalive` and `MinerU-Windows-Watchdog`. Both task names
must resolve uniquely before any task is changed. All selected tasks are disabled,
then their running instances stopped, before shutdown; any failure aborts shutdown.
`-LogDirectory` defaults to `%LOCALAPPDATA%\MOSS\maintenance`.
If C: is too full even for a small log, choose a writable directory on a healthy
Windows drive with `-LogDirectory`. Other actions are `set-sparse`, `move` (requires
`-Destination`) and `compact-check`.

`compact-check` **does not compact**: it checks offline state and exclusive read-only
access to the registered VHDX. Because keepalive is always re-enabled afterward,
a successful check does **not** reserve an offline window for a later manual
compaction command. Do not attach/compact the VHDX after return on that assumption.
Sparse mode is not proof of immediate Windows-space recovery either; logical file
length in the log is not allocated disk usage. See Microsoft's
[sparse-VHD description](https://devblogs.microsoft.com/commandline/windows-subsystem-for-linux-september-2023-update/#automatic-disk-space-clean-up-set-sparse-vhd).

## Process attribution and refusal boundary

The script reports every process whose command line contains `wsl.exe`, and any
`wsl.exe` process with unreadable arguments. To avoid retaining credentials in
command lines, records contain PID, parent/controller PID, process name and the
allowlist rule/status only. Raw command lines and native command output are not
written into the JSONL log.

The only allowlisted controller is `powershell.exe` or `pwsh.exe` with `-File`
pointing to an absolute repository path ending in:

```text
MOSS-Transcribe-Diarize[-wt-<worktree>]/ops/configure-windows-network.ps1
```

Both Windows and slash separators are accepted. The exact regex is `$ToolPattern`
in the script. A WSL launcher's **immediate parent** may establish that controller
attribution. The controller is stopped before its WSL child so it cannot loop and
restart Ubuntu. No generic `powershell`, `cmd`, Python, agent, `wsl.exe`, project-name
substring or arbitrary `-Command` text is sufficient. The wrapper and its ancestors
are never killed. Unknown processes cause refusal before any process in that scan
is killed; the task is still re-enabled in `finally` if already touched. Dry-run
also reports/refuses unknown launchers, without killing anything.

After task disable/stop and attributable-process cleanup, the script shuts down
WSL and requires the selected WSL-2 distro to read **Stopped**, with **zero `vmmem*`
processes**, continuously for 20 seconds (one-second sampling, 120-second wait
limit). Unrecognized/localized listing output refuses rather than guessing. A new
WSL launcher during either wait also refuses. The global MOSS maintenance mutex
prevents two copies of this wrapper from competing; it cannot prevent unrelated
software from launching WSL. Keep other tooling paused through verification.

Verification repeats the stopped interval and exclusive disk open after the action.
Sparse mode must set the VHDX's `SparseFile` attribute. Move must update the current
user's distro registration to the requested destination, leave a readable/exclusive
VHDX there, and remove the old VHDX path. The script never claims those checks prove
transcript integrity or service readiness.

The `finally` block attempts to re-enable and verify **every selected task** on
success or any ordinary exception after disabling begins—even tasks that were
initially disabled. Each task has its own error handling: one re-enable failure
does not prevent the attempt to re-enable the others. A failure produces a warning
naming the task and a nonzero exit. **Process kill, host crash or
PowerShell termination can prevent any finally block from running**; the operator
must then inspect/re-enable both tasks manually. Do not run concurrent maintenance.
Logs are timestamped `wsl-maintenance-<date>-<pid>.jsonl`; exit 0 means the selected
checks passed (or a dry-run plan completed), not that the host is qualified.

## Further validation — pending beyond dry-run refusal

Parse only, without invoking script functions or maintenance:

```powershell
pwsh -NoProfile -Command '$tokens = $null; $parseErrors = $null; [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "ops/windows/wsl-maintenance.ps1").Path, [ref]$tokens, [ref]$parseErrors) | Out-Null; if ($parseErrors.Count) { $parseErrors | Format-List; exit 1 }'
```

If `pwsh` is unavailable on Windows, use `powershell.exe -NoProfile -Command` with
the same parser expression. Then validate missing acknowledgement refusal, dry-run
non-mutation, unknown-launcher refusal, known-controller attribution, restoration
of both tasks on an induced action failure (including continuation after one
re-enable failure), and the full stopped interval during an approved maintenance
window. Validate actual sparse/move outcomes only on the release owner's
chosen action; this document does not authorize an extra move or recovery experiment.
