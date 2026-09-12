# Attended G7 / preadmission

**Do not run yet.** Wait for the owner's explicit go and exact qualified, staged SHA.
Round 9 is not a passing prerequisite. This command repeats all automated qualification;
recorded exceptions do not bypass its gate checks. Preadmission leaves the candidate serving
but **does not admit it**.

**Current host blocker (read-only check, 2026-09-11):** Windows user `gyauo` has
`guiApplications=false` in `%USERPROFILE%\.wslconfig`. Ubuntu has no display variables,
X display socket or WSLg PulseAudio socket. Opening Windows Terminal does not fix this.
Have the engineer resolve display/audio and demonstrate real microphone plus both required
share surfaces before scheduling this run. Do not restart WSL or vLLM: PID **169937** must
remain unchanged. A working display alone does not prove entire-screen audio capture.

## 1. Open the operator terminal

On the Alienware, sign into Windows as `gyauo`. Keep the desktop unlocked. In Windows Terminal:

```powershell
wsl.exe -d Ubuntu -u devcontainers
```

In that Ubuntu terminal:

```bash
whoami
tty
printenv DISPLAY WAYLAND_DISPLAY PULSE_SERVER XDG_RUNTIME_DIR
test -S /tmp/.X11-unix/X0 && test -S /mnt/wslg/PulseServer && echo 'Display/audio sockets present'
```

**What you will see:** `devcontainers`, a `/dev/pts/...` terminal, and working WSLg settings
(normally `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`, Pulse pointing at `/mnt/wslg/PulseServer`).
Stop if these are missing. Do not invent environment values to conceal missing servers.
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

**What you will see:** active Phase-1 web/live services; active vLLM with PID `169937`;
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
```

**What you will see:** success is `attended_g7_complete` (`g7=PASS`), then phase
`preadmission`, with `admitted=false`. Evidence is `attended-g7.json`; `account-current`
resolves to `$RUNTIME`, and vLLM remains PID `169937`.

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
