# Helper lifetime, background capture, and settled quality — 2026-09-11

**Acceptance lease starvation is fixed and measured. The real browser already
survives the requested 45-second hidden-tab test; no browser/server policy change
is warranted. The specific round-9 WER loss remains unassigned without its per-case
artifacts.** Bounds, identity policy and quality measurement logic are unchanged.

## F1 — Acceptance clients tied presence to foreground work

A helper lease means its capture owner is still present; it must not mean the
acceptance program happens to be sending frames now. Previously the replay adapter
sent heartbeats through its foreground operations, while the external campaign's
cached live creation did not start a lifetime heartbeat. A blocking file/URL wait
therefore allowed an otherwise owned live session to expire. The subsequent Stop
409 is consistent with that already-terminal session, not a Stop failure.

The two corrected wait tests fail on baseline 484d2324 with no heartbeats. The fix
starts an independent five-second heartbeat on live creation, shared with attached
replay adapters. One lock serializes explicit and periodic sends. Ambiguous replies
consume their sequence: the server accepts monotonic gaps, not a changed payload
reusing an admitted sequence. Frame retry rules remain untouched.

Stop/abort/cleanup/close retire owned helpers. Revocation retires every helper for
the revoked owner, so cleanup does not try to use deliberately revoked authority.
A new regression assertion caught that cleanup interaction before commit.

Real local measurement: **35.004 s with zero audio frames or caller activity**, seven
successful heartbeats, maximum gap **5.013 s**, session active under the unchanged
30-second lease. Own empty probe session then explicitly aborted. See
[probe and result](../../prototypes/streaming-diarization/acceptance-helper/NOTES.md).

## F2 — Browser heartbeat is already driven by the audio pipeline

`frontend/src/capture/captureClient.ts::onWorkletFrame` calls `queueHeartbeat`,
which schedules serialized heartbeat delivery based on audio-frame position.
A workspace `setInterval` does not drive helper presence. Network retry/deadline
timers still exist; this is not immunity to arbitrary browser/OS suspension.

The real headed-browser test kept the workspace **genuinely hidden for 45.012 s**:

| Observation | Measured |
|---|---:|
| Successful heartbeat responses while hidden | 90 |
| Successful frame responses while hidden | 180 |
| Maximum observed heartbeat gap | 0.506 s |
| Nominal 100 ms timer median interval while hidden | 999.55 ms |
| Capture / live session after hidden interval | active / active |
| Stop result | completed Meeting, final transcript |

Playwright normally forces focus emulation and disables background throttling.
The probe removed both in a **disposable driver copy**, asserted actual hidden
visibility and measured the timer throttling. The shared installation was not
modified. The observed 1 Hz timer establishes that this was not a synthetic
visibility event or a focus-emulated foreground page.

See [reproducible probe and limits](../../prototypes/streaming-diarization/background-capture/NOTES.md).
This establishes the requested 45-second behavior, not five-minute intensive
throttling, machine sleep, or arbitrary page suspension. Both live probes used the
existing local 17861 stack (b76b5b5c, 30-second lease), fresh workspaces, no restart
and no database reset. No host operations.

## F3 — Immediate is already a rolling transcript

The locally available round-9 handoff reports candidate **433e67b2**, pre-admission
12 quality sessions / 118 rolling completion events, immediate WER **.164900**,
settled **.167558**, final **.092333**, DER **.184595**, reference-speech DER **.156623**.
It reports all 12 quality sessions successfully finalized. These are handoff
measurements, not independently inspected round-9 traces.

`SurfaceCaptureService.stop` captures immediate only **after the whole paced
replay**. Rolling revisions have been applying during that replay. Scoring calls
`hypothesis_from_live_snapshot`, which chooses `effective_transcript` whenever
present. That effective surface includes accepted rolling revisions; the immutable
canonical commits retain the original text separately.

Consequently, immediate → settled measures **remaining work at the end**, not the
full benefit of rolling over base decoding. An increase of .002658 does not by
itself establish that rolling never ran or degraded the entire meeting. The proper
comparison for that claim is the same deployed session's committed/base text versus
its effective/rolled text, using the same reference and speaker projection.

Historical local evidence illustrates this distinction, but is **not round 9**:
`evidence/live-g4-recovery-20260825/deployed-10-10/pass-A/` snapshots for both
`discussion_jamie_dimon_180s` and `interview_adam_frank_180s` already show
`canonical_through_sample=2720000` (170 s) and `text_revision_version=17` at immediate.
Those values are unchanged at settled; Stop advances them to 180 s / revision 18.

## F4 — Ordering rejects the simple Stop/timing explanation; outcomes remain needed

Verified at candidate 433e67b2 as well as current code:

- The collector drains canonical work **and admitted rolling work**, rejects event
  gaps, refreshes its snapshot after observed completion, and raises on timeout.
- Runtime `_process_refinement_item` submits the revision under the runtime lock
  **before** recording its completion. Follow-up rolling admissions are recorded
  in the same locked completion section.
- The collector stores `pre_stop_settled` **before** recording its Stop-request time
  and invoking Stop. This capture cannot be caused by its own later Stop call.
- A failed rolling decode or refused revision can stop rolling without failing the
  live session. An empty queue therefore does **not** prove successful convergence.
  A rolling completion event also does not prove `applied=true`.
- Accepted text revisions enforce lifecycle, ownership and commitment boundaries;
  they do not consult a reference transcript or guarantee lower word error. Actual
  accepted text can degrade WER. Pending canonical tail work can also change WER
  between immediate and settled.

The candidate-to-current diff leaves these collector, projection, coordinator,
publication and refusal paths unchanged (runtime additions concern the draft lane;
finalizer additions concern window diagnostics). The quality capture/convergence
contract tests pass: **37 tests**.

Thus the code supports neither “settled happens after our Stop” nor “completion is
announced before publication.” It does permit rolling failure/refusal and text
regression. **Which happened in round 9 is unknown.** The separate lease-expired
file/URL probe sessions do not establish that the successfully finalized quality
sessions suffered the same failure.

The frozen bench's **.126365** used cached decoder answers and frozen speaker
timelines, with **122** completed windows and zero fresh provider calls. It is not
a prediction for fresh deployed text or identity. Round 9's reported **118**
completion events cannot be read as 118 successfully applied revisions without
their outcome fields. DER causes remain unmeasured here; no identity claim follows
from the frozen bench.

## D1 — Obtain existing per-case evidence before changing quality behavior

No quality fix proposed from aggregate means. The local search found the handoff
`scratchpad/issue10-round9.md`, not round-9 per-case retained files. Required next
read (no new qualification run necessary):

1. `quality/content-free-metrics.json`: per-case immediate/settled/final metrics,
   accepted/accounted samples, pending work, canonical frontier and revision version.
2. `quality/pass-<n>/<case>/terminal-diagnostics.json`: ordered rolling events with
   `outcome`, `applied`, `decode_failure`, `refusal`, `rolling_status`, window boundary,
   capture times and Stop-request time.
3. If revisions applied successfully: the matching replay snapshots/reference to
   compare base versus effective text and attribute inserted/deleted/substituted words.

These distinguish stalled/refused rolling, actual accepted-text degradation and
canonical-tail changes. They also directly falsify the ordering reading if any
settled capture precedes its required completion or follows an earlier Stop.

## Validation

`tests/phase2/test_acceptance_helper_lifetime.py` is entirely browser-free and adds
no environment skip. Focused acceptance regression set: **126 passed**. Full maintained suite (`.venv/bin/python -m pytest -q tests`): **1,384 passed,
37 subtests passed, two existing skips**, 81.59 seconds. An initial unscoped
`pytest -q` also collected archived prototype experiments; it was interrupted
after four failures and is not represented as a passing suite. No frontend source,
DOM, selector, generated bundle, server lease value, QUALITY_BOUNDS or identity
policy changes in this work.

Rebased onto **83039063**, preserving the newer resumable-Stop observation and
capacity-ledger fixes. Resolved only shared client bookkeeping/timeout composition;
no generated assets changed. Re-ran the full maintained suite on the combined
result: **1,411 passed, 37 subtests passed, two existing skips**, 90.24 seconds.
