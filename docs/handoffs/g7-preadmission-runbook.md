# Attended G7 / preadmission

**Do not run yet.** Wait for the owner's explicit go and exact qualified, staged SHA.
Round 9 is not a passing prerequisite. This command repeats all automated qualification;
recorded exceptions do not bypass its gate checks. Preadmission leaves the candidate serving
but **does not admit it**.

## Host disk hygiene

Repository copies: [incident timeline](../evidence/round-reports/host-incident-status-20260912.md), [sparse-attempt result](../evidence/round-reports/host-sparse-result-20260912.md), and [report availability](../evidence/round-reports/README.md). These are historical records; later recovery entries supersede earlier failures.

**Round-13 incident, as reported by the release owner:** Ubuntu's `ext4.vhdx`
reached **570 GB**, filled Windows C: (4.4 MB free), prevented WSL from starting
and killed vLLM. Cutover stopped at `old_stopped`, leaving Phase-1 down. This
non-sparse VHDX grows on demand and does not automatically shrink when Linux files
are deleted: Linux free space and Windows free space are different budgets.

The [disk guards and retention implementation](../../ops/README.md), introduced in
`58a742c8`, now refuses staging or a new cutover below **20 GB WSL-root / 10 GB C:**
free, before touching Phase-1. `MOSS_MIN_ROOT_FREE_GB` and
`MOSS_MIN_WINDOWS_FREE_GB` override those defaults. If neither `/mnt/c` nor
PowerShell can report C: space, the guard prints `windows_c / unavailable` and
still checks Linux; that is not proof of Windows capacity.

**Shared GPU, measured 04:58 EDT on 2026-09-12:** MinerU's container engine runs
alongside MOSS on the Alienware's **RTX 4070 Ti SUPER**; combined use was **13,658
of 16,376 MiB**. vLLM is pinned to `--gpu-memory-utilization 0.30` (about **4.9 GB**),
so the load gates were measured under that contention. Recommend pausing MinerU
during client demos if latency matters; the operator decides. Nothing was changed.

**Pull evidence bundles off the host and verify the local copies before pruning
attempt directories, including before staging invokes automatic pruning.** From
the repository root in Ubuntu, inspect the plan, then prune only after that export:

```sh
python3 moss_transcribe_diarize/candidate_storage.py --dry-run
python3 moss_transcribe_diarize/candidate_storage.py --prune
```

`ops/stage-account-candidate.sh --dry-run` prints the same retention plan with its
invoking checkout protected. Default retention is the newest **two** attempts and
runtimes (`MOSS_RETAIN_CANDIDATES`), plus active/current/recovery items. Incomplete,
unreadable and `SAFE_STOPPED` attempts are protected; stale eligible staging and
qualification directories become removable after 24 hours. Output lists removals
and bytes. Pruning alone does not reclaim the VHDX's allocated Windows space.

### Windows-side recovery — maintenance only

**Never run `wsl --shutdown` during an attempt.** Every shutdown stops WSL services;
vLLM must restart with a **new PID** and reload its model, and Phase-1 must restart
and pass the service/readiness checks in the display-maintenance section below.
Finish recovery of any interrupted cutover with the engineer before another attempt.

On this host, **both `MinerU-WSL-Keepalive` and `MinerU-Windows-Watchdog`**
automatically restart Ubuntu, and can restart WslService, within **~20 seconds** of
`wsl --shutdown`. Temporarily disable both and stop their running instances so
shutdown holds; re-enable both afterward. In Windows PowerShell as the task owner (elevated if required), during the
agreed maintenance window:

```powershell
$RestartTasks = @('MinerU-WSL-Keepalive', 'MinerU-Windows-Watchdog')
Get-ScheduledTask -TaskName $RestartTasks | Disable-ScheduledTask
Get-ScheduledTask -TaskName $RestartTasks | Stop-ScheduledTask
wsl --shutdown
wsl --list --running
```

Confirm Ubuntu is stopped. Choose one recovery route with the engineer, using a
WSL version whose `wsl --help` supports the command:

- **Enable sparse reclamation:** `wsl --manage Ubuntu --set-sparse true`.
  [Microsoft documents sparse-VHD reclamation](https://devblogs.microsoft.com/commandline/windows-subsystem-for-linux-september-2023-update/#automatic-disk-space-clean-up-set-sparse-vhd).
  Do not assume it immediately returns all 570 GB: verify C: free space and actual
  disk allocation afterward. If WSL refuses the operation, stop for the engineer;
  do not bypass its refusal.
- **Move Ubuntu to a drive with room:** `wsl --manage Ubuntu --move D:\WSL\Ubuntu`.
  This host now uses `D:\wsl\Ubuntu` (move completed 2026-09-12). For any future move, choose a different destination with enough room for the existing VHDX. Use WSL's move
  command, not a manual move of an attached VHDX.

After the operation, re-enable both tasks with
`Get-ScheduledTask -TaskName $RestartTasks | Enable-ScheduledTask`, start Ubuntu, and verify
Phase-1, vLLM/model readiness and both disk budgets before creating an attempt.
Record the new vLLM PID as that attempt's baseline. These are operator instructions;
no shutdown, task change, relocation or reclamation was performed for this doc update.

**Recovered 2026-09-12:** `D:\wsl\Ubuntu\ext4.vhdx`, file length **612,482,678,784 bytes**; original C: LocalState copy removed. File length is not a measurement of allocated disk space.

## Host hygiene — canonical origin after WSL restart

**Final handback snapshot, 2026-09-12 08:46 EDT:** VHDX
`D:\wsl\Ubuntu\ext4.vhdx`, **612,482,678,784 bytes**; C: **622.06 GB free**,
D: **171.84 GB free**; vLLM baseline **PID 324**, model endpoint **200**.
Both MinerU tasks **enabled/running**; Phase-1 both views **open, zero work**,
tailnet **200**. `moss-canonical-host.service` is installed and reboot-verified.
Record a fresh baseline after any subsequent authorized restart.

Keep WSL hosts regeneration enabled. It maintains the machine's generated localhost,
hostname and IPv6 entries; disabling it is unnecessary for one MOSS alias.

Installed on this host: user unit `moss-canonical-host.service`, required and ordered
before **both** `moss-web.service` and `moss-live-web.service` through their
`~/.config/systemd/user/<unit>.d/10-canonical-host.conf` drop-ins. It runs
`sudo -n /usr/local/sbin/moss-canonical-host` (root-owned, mode 0755), using this
host's existing passwordless sudo. The helper appends
`127.0.0.1 ga0-alienware-rtx4070ti.tailnet.aisight.us` only when that mapping is
absent; it preserves every other hosts entry. Failure blocks the web startup.
The oneshot runs again when the web service starts; no candidate code changes.

After maintenance, check in Ubuntu:

```sh
getent ahostsv4 ga0-alienware-rtx4070ti.tailnet.aisight.us
journalctl --user -b -u moss-canonical-host.service --no-pager
systemctl --user is-active moss-web.service moss-live-web.service moss-vllm.service
```

**What you will see:** `127.0.0.1`, a successful hosts-unit run before the web
services, and three `active` lines. Then check both Phase-1 views and model readiness
as below. A new WSL boot means a new vLLM baseline; never restart during an attempt.

**Verified 2026-09-12:** both MinerU tasks disabled at 08:44:02 EDT; Ubuntu
remained stopped with no vmmem for 20 seconds. After restart, the hosts unit
completed automatically at 08:44:28 and the canonical name resolved to loopback.
Both tasks were re-enabled/running at 08:44:32 in the maintenance script's finally
block. Two helper invocations before reboot also left exactly one alias line.

The existing `moss-web.service` was **disabled** (live view enabled), so it required
`systemctl --user start moss-web.service` after reboot. Its enablement was not
changed. Include this start in maintenance recovery, then verify both views.
**What you will see:** both views open with zero work; do not infer batch readiness
from the live view alone.

WSL also warned `Invalid escaped character: 'k'` at `.wslconfig:6`, whose kernel
path uses single backslashes. Startup succeeded; configuration was not changed.
Have the engineer review that separate warning before further host maintenance.

**Reverse only during maintenance:** remove the two `10-canonical-host.conf`
drop-ins and `~/.config/systemd/user/moss-canonical-host.service`; run
`systemctl --user daemon-reload`; remove `/usr/local/sbin/moss-canonical-host`
with sudo. Remove only the exact alias line from `/etc/hosts` if reverting the
mapping too. WSL generation settings were not changed.
**What you will see:** subsequent web starts no longer invoke the helper; the
canonical loopback mapping is no longer guaranteed after a WSL restart.

## Choose a display before booking the attempt

**Read-only findings:** WSLg 1.0.66 is installed but `gyauo` has `guiApplications=false`.
No VcXsrv, X410, Xming, MobaXterm or PulseAudio matched the top-level Program Files,
Program Files (x86), local Programs, current-user Store-package or process checks.
Extended recursive/registry/listener queries stalled; portable or nested installations
are not excluded. Option A is not verified available.
**Recommend C on this host** — it needs no host display and no host microphone, and this server
has neither. Options A and B remain documented for a host-local canary; both additionally require
a capture device the Alienware does not currently have (see C for the enumeration). Between them,
prefer B unless an X server is subsequently located whose real microphone path works; an X server
alone supplies no audio.

**Options A and B only:** `query user` shows `gyauo` in disconnected session 2 (Explorer still
running); the console has no signed-in user. This does not establish usual habits. Log into/unlock
the local Windows desktop as `gyauo` before either option and keep it connected throughout G7.
**What you will see:** your usable Windows desktop; `query user` should show an active
session, not `Disc`. SSH access is not a substitute. Option C needs no Windows desktop session:
its browser is on your machine and its terminal is your SSH session.

### C. Attend from your own machine — recommended, no host display or host microphone

The attended browser is the **client** role and does not have to run on the server. The candidate
supplies an optional `measurements.pre_admission.chrome_cdp_endpoint`; when it is set the canary
attaches to a Chrome you already run, instead of launching one on the host. The cutover, its
qualification and the four Enter prompts stay on the Alienware over your SSH terminal; the
microphone, the Chrome share picker and both display surfaces are the ones in front of you.

This removes options A and B entirely when it applies: no WSLg, no `wsl --shutdown`, no X server,
no PulseAudio bridge, and **no change to the vLLM PID**. Read-only host finding, 2026-09-12: the
Alienware has no usable capture device — every physical jack (`Microphone`, `Jack Mic`, `Headset`)
reports UNPLUGGED, and the only ACTIVE capture endpoints are `Stereo Mix` (Realtek loopback, not a
microphone) plus virtual endpoints belonging to Virtual Desktop and Oculus. A host-local canary
therefore needs hardware added to the server first.

**1 — start a dedicated Chrome on your machine.** Use its own `--user-data-dir`, and treat that as a
gate requirement rather than a convenience. The host-local canary launched a throwaway profile for
every run; attaching to a browser instead means the profile is whatever you point it at. Your everyday
profile carries extensions that can interfere with `getDisplayMedia`, plus service workers and cached
state that could mask a first-run defect. A dedicated profile restores the isolation the host-local
path had. It is also mechanically necessary: Chrome silently ignores `--remote-debugging-port` when it
hands the command line to an already-running instance of the same profile.

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.moss-attended-chrome" \
  --enable-automation \
  --no-first-run --no-default-browser-check
```

`--enable-automation` is **required**, and not for convenience: Chrome returns its own command line
over DevTools only when it is set, and the canary reads that command line back to prove the browser
cannot manufacture this gate's evidence (next paragraph). Without it the canary refuses, because a
command line it cannot read is one it cannot clear. Expect Chrome's "controlled by automated test
software" infobar; that is the flag doing its job.

**Why the canary audits it.** A browser the canary launches is configured by the canary. Yours is not,
so it is checked rather than assumed. The canary refuses any attended browser started with
`--use-fake-device-for-media-stream`, `--use-file-for-fake-audio-capture`,
`--use-file-for-fake-video-capture`, `--use-fake-ui-for-media-stream`,
`--auto-select-desktop-capture-source`, `--auto-select-screen-capture-source`,
`--auto-select-tab-capture-source-by-title`, `--auto-accept-this-tab-capture`,
`--auto-accept-camera-and-microphone-capture` or `--auto-grant-captured-surface-control` — synthetic
capture devices, and automatic answers to the very permission and surface choices you are there to
make. Verified against real Chrome on 2026-09-12: an honest browser is accepted, each of those
switches is refused by name, and a browser without `--enable-automation` is refused as unauditable.
The cleared switch list is recorded in the evidence as `audited_absent_switches`.

**What you will see:** a separate Chrome window, and `curl -s http://127.0.0.1:9222/json/version`
returning that browser's version locally. DevTools binds loopback only; do not publish it.

**2 — open MOSS once in that window**, at
`https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`, and accept the certificate if Chrome
warns. There is no login: the page bootstraps a workspace by itself. What you are really doing here
is teaching *this profile* to trust the self-signed certificate, because a browser context without
that exception cannot load the origin at all.

**The session must not carry across cutovers.** Every cutover quarantines the candidate's database,
so a `__Host-moss_session` cookie minted against an earlier instance names a workspace the serving
one has never seen. The product then refuses to bootstrap over it — deliberately, since it will not
silently abandon work that may exist — and renders *"Workspace unavailable… Contact the operator."*
with **no bootstrap script**, so the page never reaches `signed-in` and the canary times out after
30 seconds. A launched throwaway profile never carried such a cookie; a persistent one does. The
canary therefore clears cookies for this origin only, in the attached context, before it navigates —
your other sites and the profile's certificate trust are untouched. Nothing is required of you, but
if you ever see that message, this is why.

**3 — forward the endpoint to the host** so DevTools control never crosses the network. From your
machine, in the terminal you will also run the cutover from:

```sh
ssh -R 127.0.0.1:9222:127.0.0.1:9222 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
```

That binds loopback on the Windows side. This host uses WSL2 mirrored networking, which carries the
forward into the distribution as well. **Verified end to end on 2026-09-12** from a Mac: a trivial
loopback server behind `ssh -R 127.0.0.1:PORT:127.0.0.1:PORT` answered both from Windows
(`curl.exe`) and from inside Ubuntu (`wsl.exe -d Ubuntu -- curl`), and stopped answering once the
forward was torn down. Still **re-verify before booking each attempt** — the forward is per-session —
in the Ubuntu terminal that will run the cutover:

```bash
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:9222/json/version
```

**What you will see:** the same Chrome version JSON you saw locally. If Ubuntu cannot reach it,
mirrored networking is not carrying the forward; stop and tell the engineer rather than exposing
the port on an interface. No attempt has been created at this point, so stopping costs nothing.

**4 — declare the endpoint in the host profile.** Add the key to the persistent acceptance profile
the canary reads (the cutover passes its configured `acceptance_profile`, not the per-attempt copy).
Staging preserves keys it does not manage, so this survives a restage.

```bash
python3 - <<'DECLARE'
import json, pathlib
p = pathlib.Path.home() / '.config/moss-transcribe-diarize/phase2-acceptance.json'
payload = json.loads(p.read_text())
payload['measurements']['pre_admission']['chrome_cdp_endpoint'] = 'http://127.0.0.1:9222'
p.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
print('declared', payload['measurements']['pre_admission']['chrome_cdp_endpoint'])
DECLARE
```

The canary refuses any endpoint that is not loopback `http`/`ws`, so the forward is the only
supported path. To go back to a host-local Chrome, delete the key; `chrome_binary` is then required
again and the behaviour is unchanged.

**What you will see during the run:** the canary opens two tabs in *your* Chrome; each scenario's
share picker is your own, and "Entire screen" means your screen. The Enter prompts appear in the
SSH terminal running the cutover. Owner API reads (Live descriptor, Meeting, MP3) are issued from
the host using session cookies synced from your browser, so they read **the same meeting you
attended, by its id**. Read that precisely: those reads travel the host's own network, TLS trust and
DNS, not your laptop's. A 200 on the owner MP3 therefore proves the server can produce the file, not
that the presenter's machine can fetch it — that is what the operator smoke test and
`scripts/demo-precheck.sh` establish, and both run from your machine. Run them; the canary does not
replace them. When the canary finishes it disconnects without closing your browser: both meeting tabs
stay open for the rehearsal.

**Limits:** this changes where the browser runs, not what the gate checks. Both scenarios, both
meters, the frame-sequence checks, two distinct speakers, the finalized Meeting and the playable
owner MP3 are all still required, and the evidence records `attended_browser` so the record states
which machine attended. Your machine must reach the production origin over the tailnet with normal
certificate verification — the origin serves a **self-signed** certificate, so the attending machine
must already trust it; a machine that does not will fail TLS rather than report a host fault.

The canary now also binds its observations to the production origin: it refuses if the page is not on
that origin after navigation, before Stop, or at the terminal phase, and it ignores frame posts from
any other origin. Both scenarios' surfaces, meters, frame sequences, speakers, Meeting and MP3 are
unchanged. The binding is checkpointed rather than continuous — a page that left and returned between
two checkpoints would not be caught — but every accepted frame is origin-filtered and the Meeting is
pinned to the single id those frames carry.

DevTools discovery is resolved by the canary itself rather than delegated: it reads
`/json/version` over the forward with redirects disabled and re-validates the websocket that response
nominates, so whatever answers the endpoint cannot steer the connection off loopback. Endpoint strings
that two URL parsers could read as two different hosts — backslashes, userinfo, control characters,
non-numeric ports — are refused outright rather than resolved by one parser's rules.

Two properties the host-local path gave for free, which you now supply by following step 1: a clean
browser profile (see above), and a browser that nothing else drives. The loopback check constrains
where *the canary* connects; it cannot stop a Chrome you started with `--remote-debugging-address`
pointed at a non-loopback interface. Do not do that. Note also that DevTools discovery resolves the
websocket target from the endpoint's own `/json/version` response, so the loopback guarantee extends
only as far as trusting the browser you started.

**Residual, stated plainly:** the switch audit closes command-line faking, but the gate measures audio
*signal*, not the physical provenance of a device. An operator who routes a virtual audio device as the
system microphone can still feed recorded speech to either path — this host's `Stereo Mix` endpoint
would do it — and that was equally true of the host-local canary. G7 is an attended gate resting on an
honest attester; it is not a control against the operator.

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
import json, pathlib, sys, urllib.parse
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
endpoint = g7.get('chrome_cdp_endpoint')
if endpoint:
    assert urllib.parse.urlsplit(endpoint).hostname in ('127.0.0.1', 'localhost', '::1')
else:
    assert pathlib.Path(g7['chrome_binary']).is_file()
print('Profiles and SHA match:', v['git_sha'])
print('Attended browser:', endpoint or g7['chrome_binary'])
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

Keep the microphone and a spoken-audio source ready.

**Option A/B (host-local Chrome):** be ready to sign into MOSS in the new Chrome window. Its
temporary profile starts logged out and the canary waits for sign-in with Playwright's default
30-second selector timeout, with no Enter pause — a real race.

**Option C (your own browser):** that race does not exist, because you signed in during step 2 of
Option C and your profile is persistent. Do confirm that tab is still signed in before you start,
and that the `ssh -R` forward is up — the canary contacts the endpoint only when G7 begins, but if
it is down at that moment the attempt is lost.

**Run it where a dropped connection cannot kill it.** The host has `tmux`; start the cutover inside
a session on the host rather than a bare SSH shell. It is still a real PTY, so attendance holds, and
it survives a laptop sleeping or a network blip during the two-hour qualification:

```bash
tmux new -s g7        # then run the command below inside it; reattach later with: tmux attach -t g7
```

```bash
ATTEMPT="$HOME/.local/state/moss-transcribe-diarize/cutover-attempts/preadmission-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'Attempt: %s\n' "$ATTEMPT"
"$CUTOVER" run --profile "$PROFILE" --attempt "$ATTEMPT" --terminal preadmission
```

**What you will see:** the printed attempt path, then qualification output. Copy the path.
Do not create the attempt directory: the CLI requires a new path and creates it at `0700`.
Keep it under this Linux state directory, on the candidate-state filesystem, not `/mnt/c`.
Do not detach, pipe stdin, or use `systemd-run`. Allow roughly an hour or more; no fixed ETA.

## 3b. What you can walk away from, and what you cannot

The single command runs two very different phases back to back.

**Phase A — automated qualification, budget about two hours, no input needed.** It repeats the whole
acceptance measurement across both layers. Measured on round 16: roughly 130 minutes of recorded
commands, about 63.9 minutes per collector — 24 serial quality sessions (~43 min per layer), a
four-session 600-second capacity campaign, an eight-session overload, and a second capacity campaign
inside G9. That time is measurement windows, not overhead, which is why it cannot be shortened.

You may leave, subject to three hazards:

1. **Your machine must not sleep and the session must not drop.** The cutover holds your terminal; a
   dropped SSH session sends SIGHUP mid-attempt and leaves an interrupted attempt needing section 7's
   restore. Use `caffeinate` on a Mac, and prefer running the cutover **inside `tmux` on the host** —
   still a real PTY, so the attendance check is satisfied, but it survives a dropped connection.
   Do not use `systemd-run`, a pipe, or `nohup`; those remove attendance rather than protect it.
2. **Be back before Phase B starts.** The first hard window opens the moment the canary clicks, and
   nobody there means `AttendedCanaryError`, automatic restoration, and the whole run again from the
   top. Watch section 4's journal for `attended_g7_started`; start checking around 90 minutes.
3. **Option C only:** the `ssh -R` forward must be alive when Phase B begins. It is contacted only
   then, so a drop during Phase A is harmless provided you re-establish it before returning.

**Phase B — attended G7, roughly 15 to 25 minutes, hands-on throughout.** The four Enter prompts are
plain `input()` with no timeout, so you set the pace between them, but these windows are fixed:

| window | limit | what must happen inside it |
|---|---|---|
| display selection | **300 s** | complete Chrome's share picker with audio enabled |
| both meters non-zero | **10 s** | both sources already audible when you press the first Enter |
| capture ready | **120 s** | after that first Enter |
| capture active | **120 s** | after the canary clicks Start capture |
| finalize | **600 s** | after Stop and finalize |

The 10-second meter check is the one that surprises people: make the microphone and the shared source
audible *before* pressing Enter, not after.

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
