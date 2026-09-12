# Attended G7 / preadmission

**Do not run yet.** Wait for the owner's explicit go and exact qualified, staged SHA.
Round 9 is not a passing prerequisite. This command repeats all automated qualification;
recorded exceptions do not bypass its gate checks. Preadmission leaves the candidate serving
but **does not admit it**.

## Choose a display before booking the attempt

**Read-only findings:** WSLg 1.0.66 is installed but `gyauo` has `guiApplications=false`.
No VcXsrv, X410, Xming, MobaXterm or PulseAudio matched the top-level Program Files,
Program Files (x86), local Programs, current-user Store-package or process checks.
Extended recursive/registry/listener queries stalled; portable or nested installations
are not excluded. Option A is not verified available.
**Recommend B on this host.** Prefer A if an existing X server is subsequently located,
provided its real microphone path works; an X server alone supplies no audio.

`query user` shows `gyauo` in disconnected session 2 (Explorer still running); the console
has no signed-in user. This does not establish usual habits. Log into/unlock the local
Windows desktop as `gyauo` before either option and keep it connected throughout G7.
**What you will see:** your usable Windows desktop; `query user` should show an active
session, not `Disc`. SSH access is not a substitute.

### A. Windows X server plus Windows audio — preserve running WSL services

Have the engineer start the installed X server on display 0 and permit its WSL connection.
In the Ubuntu terminal that will run the canary, set:

```bash
WINDOWS_HOST_IP='ADDRESS_CONFIRMED_BY_ENGINEER'
export DISPLAY="${WINDOWS_HOST_IP}:0"
export PULSE_SERVER="tcp:${WINDOWS_HOST_IP}:4713"
```

This host uses mirrored networking: Windows loopback `127.0.0.1` is an option if the servers
listen there; do not mistake the LAN router/default gateway for Windows. See
[Microsoft's networking guidance](https://learn.microsoft.com/en-us/windows/wsl/networking).

Have the engineer configure PulseAudio-for-Windows with TCP access **and a real recording
source mapped to the Windows microphone**, then demonstrate the microphone meter in Linux
Chrome. Playback-only PulseAudio is insufficient: the older
[X410 audio recipe](https://x410.dev/cookbook/wsl/enabling-sound-in-wsl-ubuntu-let-it-sing/)
explicitly disables recording with `record=0`; do not use that setting for G7. No working
WSLg-free microphone path was found here. Installation/configuration is separate setup work.

**What you will see:** Linux Chrome on Windows, plus a working microphone. You must still
verify tab audio and entire-screen audio in that Chrome instance. Neither an X display nor
PulseAudio playback proves Chrome will provide a shared-audio track. No WSL shutdown is
needed for A; keep the existing vLLM PID unchanged.

### B. Enable WSLg — recommended, with planned downtime

**Do this only in an agreed maintenance window BEFORE creating any preadmission attempt;
NEVER during one.** `wsl --shutdown` stops every running WSL distribution and every WSL
service, including `moss-vllm`, Phase-1 `moss-web` and `moss-live-web`. vLLM's process/PID
will change on restart; allow minutes for model reload (duration unmeasured).
The current PID `169937` is not the baseline after this planned restart.
[Microsoft documents the shutdown scope and setting](https://learn.microsoft.com/en-us/windows/wsl/wsl-config).

In Windows Terminal / PowerShell as `gyauo`, edit the existing file:

```powershell
notepad "$env:USERPROFILE\.wslconfig"
```

Change only `guiApplications=false` to `guiApplications=true` under the existing `[wsl2]`;
keep the custom kernel, memory and networking settings. Save, then run:

```powershell
wsl --shutdown
wsl.exe -d Ubuntu -u devcontainers
```

**What you will see:** existing WSL terminals/services disconnect, then a fresh Ubuntu
shell. Enabled user services can restart; `moss-web.service` is currently **disabled** for
automatic startup and needs the explicit start below. User lingering is enabled.

With the engineer confirming Phase-1 configuration and no attempt in progress, run in Ubuntu:

```bash
systemctl --user start moss-web.service
systemctl --user is-active moss-web.service moss-live-web.service moss-vllm.service
systemctl --user show moss-vllm.service -p MainPID
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/v1/models
python3 - <<'CHECK'
import json, pathlib, ssl, urllib.request
p = pathlib.Path.home() / '.config/moss-transcribe-diarize/moss-cutover.json'
for v in json.loads(p.read_text())['phase1']['runtime_views']:
    ctx = ssl.create_default_context(cafile=v['ca_file']) if v.get('ca_file') else None
    with urllib.request.urlopen(v['origin'] + '/api/runtime', context=ctx, timeout=10) as r:
        state = json.load(r)['phase1_creation']
    print(v['name'], state)
    assert state['state'] == 'open'
    assert all(state[k] == 0 for k in ('entrants', 'active_jobs', 'queued_jobs', 'active_live_sessions'))
CHECK
```

**What you will see:** three `active` lines; a new positive vLLM PID; `/v1/models` lists
`OpenMOSS-Team/MOSS-Transcribe-Diarize`; both `batch` and `live` are `open` with zero work.
Wait for model readiness; stop and ask the engineer if any check fails. Then verify WSLg
sockets below and real microphone/shared audio. Record the new PID in step 2 and preserve
it throughout the attended attempt. No shutdown or configuration change was performed by
this read-only review.

## 1. Open the operator terminal

On the Alienware, sign into Windows as `gyauo`. Keep the desktop unlocked. In Windows Terminal:

```powershell
wsl.exe -d Ubuntu -u devcontainers
```

In that Ubuntu terminal (the socket test applies to B; for A use its verified TCP display/audio):

```bash
whoami
tty
printenv DISPLAY WAYLAND_DISPLAY PULSE_SERVER XDG_RUNTIME_DIR
test -S /tmp/.X11-unix/X0 && test -S /mnt/wslg/PulseServer && echo 'Display/audio sockets present'
```

**What you will see:** `devcontainers`, a `/dev/pts/...` terminal, and working WSLg settings
(normally `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`, Pulse pointing at `/mnt/wslg/PulseServer`).
For B, stop if these are missing. For A, verify its TCP connections instead; WSLg sockets
and `WAYLAND_DISPLAY` are not required. Do not invent values to conceal missing servers.
[WSLg supplies these services and variables](https://github.com/microsoft/wslg).

## 2. Check the release and profiles

Replace the placeholder with the full SHA supplied by the engineer. Stop on any failed check.

```bash
SHA='PASTE_APPROVED_FULL_SHA'
ROOT="$HOME/.local/share/moss-transcribe-diarize"
RUNTIME="$ROOT/account-runtimes/$SHA"
CUTOVER="$RUNTIME/bin/mtd-phase2-cutover"
PROFILE="$HOME/.config/moss-transcribe-diarize/moss-cutover.json"
export PYTHONDONTWRITEBYTECODE=1
systemctl --user show moss-web.service moss-live-web.service moss-vllm.service -p Id -p ActiveState -p MainPID
VLLM_PID=$(systemctl --user show moss-vllm.service -p MainPID --value)
printf 'Preserve this vLLM PID: %s\n' "$VLLM_PID"
"$CUTOVER" run --help
"$CUTOVER" restore --help
python3 - "$SHA" <<'PY'
import json, pathlib, sys
home = pathlib.Path.home()
p = home / '.config/moss-transcribe-diarize/moss-cutover.json'
c = json.loads(p.read_text())
a = home / '.config/moss-transcribe-diarize/phase2-acceptance.json'
assert c['candidate']['acceptance_profile'] == str(a)
assert all(x.stat().st_mode & 0o777 == 0o600 for x in (p, a))
m = pathlib.Path(c['candidate_manifest'])
v = json.loads(m.read_text())
assert m.stat().st_mode & 0o777 == 0o600
assert v['git_sha'] == sys.argv[1]
assert v['release'] == str(home / '.local/share/moss-transcribe-diarize/account-runtimes' / sys.argv[1])
layers = json.loads(a.read_text())['measurements']
assert all(layers[k]['candidate_manifest'] == str(m) for k in ('deployed', 'pre_admission'))
g7 = layers['pre_admission']
assert g7['https_origin'] == 'https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861'
assert pathlib.Path(g7['chrome_binary']).is_file()
print('Profiles and SHA match:', v['git_sha'])
print('Chrome:', g7['chrome_binary'])
print('Staged env:', c['candidate']['account_profile_source'])
PY
if test -L "$ROOT/account-current"; then readlink -e "$ROOT/account-current"; else echo 'No Account activation symlink'; fi
```

**What you will see:** active Phase-1 web/live services; active vLLM with a positive PID recorded in `VLLM_PID`;
matching profiles at mode `0600`. G7 reads `measurements.pre_admission.https_origin` and
`chrome_binary`; it does not use the acceptance cookie files to sign Chrome in.
`account-current` may be absent before cutover—that is correct for the restored host.
Do not point it at the candidate manually. The staged env should remain
`~/.config/moss-transcribe-diarize/staged/moss-account.env`.

## 3. Start in the foreground

Keep the microphone and a spoken-audio source ready. Be ready to sign into MOSS in the new
Chrome window: its temporary browser profile starts logged out, and the installed canary
waits for sign-in with Playwright's default 30-second selector timeout, without an Enter pause.

```bash
ATTEMPT="$HOME/.local/state/moss-transcribe-diarize/cutover-attempts/preadmission-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'Attempt: %s\n' "$ATTEMPT"
"$CUTOVER" run --profile "$PROFILE" --attempt "$ATTEMPT" --terminal preadmission
```

**What you will see:** the printed attempt path, then qualification output. Copy the path.
Do not create the attempt directory: the CLI requires a new path and creates it at `0700`.
Keep it under this Linux state directory, on the candidate-state filesystem, not `/mnt/c`.
Do not detach, pipe stdin, or use `systemd-run`. Allow roughly an hour or more; no fixed ETA.

## 4. Watch progress in a second Ubuntu terminal

Paste the exact printed path; variables do not carry into another terminal.

```bash
ATTEMPT='PASTE_EXACT_ATTEMPT_PATH'
tail -F "$ATTEMPT/journal.jsonl"
```

**What you will see:** `qualification_started`, then—only if automated gates pass—
`attended_g7_started`. The journal is inside the attempt, mode `0600`.
Keep the first terminal available for prompts. A failure can instead lead to restoration.

## 5. Attend both Chrome scenarios

Use the Chrome window opened by the canary at
`https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`. Sign in when it opens.
The canary clicks microphone/share/start/stop; you handle permissions, the share picker,
audio and its Enter prompts.

- **Tab (`microphone_meeting_tab`):** select a tab in this Chrome instance playing another
  person's speech; enable shared audio. Keep your microphone audible. At the **first Enter**
  prompt, make both sources audible so both meters can be measured. The canary then starts
  capture. Keep both sources audible; press **Enter again only when both speakers appear**.
- **Entire screen (`microphone_entire_screen`):** repeat with **Entire screen**, shared audio
  enabled, and the same two Enter checkpoints. A window or tab is not a substitute. If the
  picker cannot provide entire-screen audio, stop and report it; do not claim G7.

**What you will see:** four Enter prompts total. Each selection must yield exactly one shared
audio track. The canary checks nonzero microphone/shared-audio meters, then two distinct
speakers, both lanes' descriptor-matching frames without sequence gaps, finalized Meeting
and playable owner MP3. Do not stop capture manually.

## 6. Read the terminal result

After the first terminal's command exits:

```bash
cat "$ATTEMPT/result.json"
tail -n 3 "$ATTEMPT/journal.jsonl"
readlink -e "$ROOT/account-current"
systemctl --user show moss-vllm.service -p ActiveState -p MainPID
test "$(systemctl --user show moss-vllm.service -p MainPID --value)" = "$VLLM_PID" && echo 'vLLM PID unchanged'
```

**What you will see:** success is `attended_g7_complete` (`g7=PASS`), then phase
`preadmission`, with `admitted=false`. Evidence is `attended-g7.json`; `account-current`
resolves to `$RUNTIME`, and vLLM matches the pre-attempt `VLLM_PID`.

Failure normally records `failure_observed`, `restore_started`, then `restored`
(`g7=UNCLAIMED`). Phase-1 resumes and the old symlink state returns, possibly absent.
`SAFE_STOPPED` means restoration could not be completed safely: stop and call the engineer.
A missing `result.json` is not success; the durable journal is authoritative. `REFUSED`
means the command refused to proceed; retain its printed reason and any attempt files.

## 7. Recover an interrupted attempt only

If the command disappeared **without a terminal journal phase**, first have the engineer
confirm the original cutover process is no longer running. In a terminal with the same
`CUTOVER` and exact `ATTEMPT` variables:

```bash
"$CUTOVER" restore --attempt "$ATTEMPT"
```

**What you will see:** `restored`, or an explicit refusal/`SAFE_STOPPED` requiring help.
There is no `--profile` argument for restore; it uses the attempt's stored snapshot/profile.
**Do not use this as later demo rollback:** `restore` refuses all terminal attempts, including
successful `preadmission`. Arrange any later rollback separately with the engineer.

Checked against installed candidate `433e67b25274e98eabc4d3523e5256525e7349f7`:
`mtd-phase2-cutover --help`, `run --help`, `restore --help`, installed
`app/phase2_cutover_cli.py`, `phase2_cutover.py` and `phase2_g7_canary.py`.
That SHA is verification context, not authorization to run it. No cutover, browser capture,
WSL restart or service change was performed during this review.
