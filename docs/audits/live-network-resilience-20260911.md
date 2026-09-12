# Live Wi-Fi interruption resilience — 2026-09-11

**Both 3-second and 20-second origin outages survive.** Frame delivery, helper lease and
polling already recovered correctly. The demonstrated defect was a stale “Failed to
fetch” warning after recovery. The patch fixes that warning without changing retries,
frame sequence/epoch policy, lease duration, capture-lane contracts or acceptance selectors.

## Contract and experiment

The structural question: can capture, acknowledged audio, helper presence and the reader
recover independently while preserving the same meeting? The minimum primitives are a
queued frame with its original identity, an acknowledgement, a lease heartbeat and a
snapshot cursor. Successful delivery is the evidence of recovery; moving audio meters
alone cannot establish network health. Stop/terminal state must outrank a late recovery.

Falsifiers: changed/missing frame identities, lease expiry, a stuck reader, no playable
history audio, or recovery messages overwriting a terminal state. Tests use real capture
and model output. Playwright aborts **all requests to the application origin**, including
frames, heartbeat, snapshots and events, for the measured interval. The separate local
audio-source origin keeps playing, like speech continuing during a Wi-Fi interruption.
The test restores routing in `finally`; it never reloads or recreates a meeting to recover.
Each variant starts independently in a new tab before the interruption.

The initial harness exposed a cleanup observation wait, then a second-capture setup
“Invalid state” error before the 20-second outage. Those are explicitly excluded setup
attempts in the evidence manifest. Response observation is now bounded and per-case
results are retained before cleanup. Final before/after runs both execute both outages.

## Measurements

Baseline: existing port **17861**, clean `b76b5b5c` checkout, unchanged database/service.
After: separate port **17862**, implementation `ad059be5`, separate state/control socket,
using a copy of `scratchpad/localstack/run_local_stack.py`. Both use a **30-second helper
lease**, the real provider and `mono_javier_intro_50s`. Each run creates a fresh browser
workspace. No host operations and no resets of either database. The temporary 17862
instance was stopped after verification; its state is retained. Port 17861 was untouched.

| After-patch measurement | 3-second outage | 20-second outage |
|---|---:|---:|
| Actual interruption | 3.002 s | 20.001 s |
| Blocked origin requests | 24 | 134 |
| First successful microphone frame after restore | 0.127 s | 0.019 s |
| First successful shared-audio frame after restore | 0.185 s | 0.095 s |
| First successful snapshot after restore | 0.530 s | 3.631 s |
| Maximum successful-heartbeat response gap | 3.506 s | 20.510 s |
| Transcript DOM changes after restore | 5 | 3 |
| Downloaded, decoded audio | 13.500 s | 29.928 s |
| Terminal meeting / finalization | completed / final | completed / final |

**F1 — Audio continuity is preserved.** Both before and after have zero frame 409s,
continuous per-lane sequences, unchanged epochs and no missing 500-ms timestamp steps.
After: 27 microphone/27 system accepted frames for the short outage; 60/59 for the long
outage. Separate coverage files retain these counts and timestamp-step sets. Different
lane counts reflect their start/stop alignment, not a sequence gap. Downloads were
probed as seekable files and fully decoded with ffmpeg; history cards remain present.

**F2 — The lease and reader recover.** Both cases stay active throughout the outage;
heartbeats resume and the meetings complete normally. Measured gaps are browser response
times, not a fabricated exact server lease clock. The 20-second reader delay follows the
existing retry backoff; no reload is needed. No lease or polling-retry change is justified.

**F3 — Recovery feedback was missing.** Baseline requests and transcript updates recover,
but the status remains “Failed to fetch”. Error callbacks updated the message; successful
requests had no corresponding notification. The patch tracks previously failing capture
paths (each lane plus heartbeat) and notifies once they all succeed. The reader separately
notifies after a successful request pair, including an unchanged snapshot. The workspace
clears the warning only when capture and reader have both recovered:
“Connection restored. Recording microphone and shared audio.” During a fetch interruption
it says “Connection interrupted. Retrying automatically; keep this tab open.”

Late responses after close cannot emit capture recovery, and a late notification cannot
overwrite terminal or Stop UI. Session identity guards prevent an old client from clearing
a replacement client's warning. No new timers, decoder work, retries or lease extension.

## Row 13 and validation

`tests/e2e/verify_workspace.py --rows 13 --new-workspace` now runs both durations. It
records blocked route classes, phase continuity, frame sequences/epochs/timestamps,
heartbeat and polling recovery, transcript DOM changes, terminal/finalization state,
history presence, playable audio, and recovery feedback. Three seconds requires survival
and completed/final. Twenty seconds accepts that same result or explicit terminal UI plus
preserved partial history audio. Both measured cases take the **survival** branch; the
alternative was not empirically exercised and is not claimed qualified.

Three targeted tests failed before the UI fix. Afterward, five new regressions cover:
independent lane recovery, heartbeat recovery, no recovery after close, unchanged-snapshot
reader recovery with retained cursor, and workspace recovery/terminal precedence.
Full suite: **1,380 Python passed, 37 subtests passed, 2 existing skips; 201 frontend
passed; TypeScript passed.** No browser binary was added to required deterministic tests.

Reproduction against the existing stack (writes only a fresh test workspace):

```sh
.venv/bin/python tests/e2e/verify_workspace.py --base https://127.0.0.1:17861 \
  --rows 13 --new-workspace --corpus /path/to/mono_javier_intro_50s \
  --output /tmp/moss-network-outage-evidence
```

Content-free per-case results, response traces, coverage counts and provenance are under
`evidence/e2e-network-resilience-20260911/`. Cookies, audio and screenshots remain in the
private temporary output directories. One before/after pair per duration is a regression
measurement, not a statistical reliability claim. Immediate request drops do not cover
blackholed TCP, browser suspension, or lost responses after server admission. Existing
unit coverage separately checks identical frame replay after unconfirmed delivery.

Scratch paths in commands above are local inputs/output destinations, not bundled evidence; retained outputs from the original Mac run are MacStudio-local (not in repo).
