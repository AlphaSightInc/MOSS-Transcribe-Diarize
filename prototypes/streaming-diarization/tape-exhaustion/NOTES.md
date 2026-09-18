# WP29 — tape exhaustion

Question: can a longer-than-tape meeting finish truthfully without losing committed words?
Primitives: committed transcript, bounded retained PCM, terminal refinement, durable audio,
and lifecycle ownership. Each has a distinct lifetime; none substitutes for another.
Invariants: unchanged bounds/policies/protocol; failed tape cannot fail capture; unavailable
refinement keeps words; partial audio states its actual duration; Stop owns completion.
Unknown: repeated-session native memory until the two-session measurement completes.
Falsifier: any lost committed lane segment, generic finalizer defect, false complete audio,
armed terminal lease, nonempty publication queue, or unreadable durable result.
Tool decision: real HTTP/SQLite/MP3 + stub ASR isolates lifecycle from provider variability;
real public speech and ONNX RSS probe distinguish Python tape release from native residency.

## Prototype verdict before production changes

Supported fix. Nine sessions across eight scenarios, 90 seconds each, 60-second tape.
Both exhausted (Stop, accepted Stop then departure, silent microphone, two concurrent):
5/5 refinement `failed`, missing keyword-only `gaps`; all saved `completed` with words intact.
One exhausted lane (2/2): `final`, failed-lane words intact, INCORRECT zero gap accounting.
Mixed tape only (1/1): both lanes refine, audio remains independently partial.
Departure before Stop (1/1): `interrupted`, no refinement; correct lifecycle preserved.
All 9: 60.000000-second partial MP3; saved/live words equal; lease disarmed; queue empty;
all three tapes released. No notice describes unavailable refinement in the saved meeting.
Silent PCM is NOT compressed: all lane tapes grow equally even with a silent microphone.
Thus single-tape cases use explicitly isolated capacity overrides, not a false silence premise.
No production cap changes proposed.

Unit falsifiers before fix: 4 failed, 1 passed. Both-exhausted and all-zero lack `gaps`;
each one-lane failure reports zero gaps. Evidence: unit-red.txt and prototype.json.
Automated state dumps replace interactive TUI; the probe is absorbed into this regression bench.

Failed setup attempts retained: prototype-stop.txt disabled the rolling planner and exercised
`no_terminal_plan`, not the defect. prototype.txt then waited for HTTP Stop before manually
running the terminal scheduler, correctly receiving `stop_in_progress`. Corrected probe keeps
the planner and runs the held terminal work while the Stop request waits. Neither is a product bug.

## Implemented result

`fixed.json`: 9/9 preserve the expected durable outcome, words, audio duration and cleanup.
Five both-lane exhaustion sessions now report `unavailable`, with two actual lane gaps;
two single-lane sessions report `final`, one actual lane gap and preserve that lane's words;
mixed-only finalizes both lanes; pre-Stop departure remains interrupted. All nine reopen
with the exact saved document and notice, all MP3s are partial and exactly 60 seconds.
Seven completed sessions with unavailable refinement carry only this fixed notice:
"Final transcript refinement was unavailable for some audio. Previously committed words were kept."
Existing history renders that notice and "Download partial audio"; no frontend production
change or generated asset change is needed. Refusal accounting reports lane gap count,
not a fabricated whole-meeting gap count; both lanes missing the same interval count twice.

First focused patched suite: 56 passed, 2 failed. Both failures were missing notices for
single-lane exhaustion: publication is queued on `text_revision_applied` before the terminal
accounting event is appended. The notice now reads the settled runtime event stream under
its lock. This is covered by the HTTP tests; not hidden by testing a synthetic payload only.

Memory probe setup: the first attempt used WP22's tracemalloc instrumentation. Stopped after
90 audio seconds because tracing is unnecessary for the requested cheap current-RSS check;
retained its partial logs as `repeat-rss-traced-incomplete.*`. The replacement keeps production
VAD, ONNX identity, lane/rolling/terminal paths, both original public clips, the same runtime
and encoder for both meetings, and Python owner counts; removes allocation tracing only.
No caches of model outputs; no GPU; all PCM and synthetic content stay in ignored `.wp29/`.

## Full-suite failure adjudication

First full run: 1,932 passed, 2 skipped, 37 subtests (178.35 s). Frontend: 265/265
in 28 files; typecheck/build pass, generated assets unchanged. The portable HTTP
regression then passed 8/8 using synthetic PCM; standalone measured evidence uses
real public clips. This removes developer-local corpus dependence from tests.

Second full run: 1,931 passed, 1 failed, 2 skipped, 37 subtests (175.39 s).
File: `tests/test_live_service_runtime.py`, test
`test_transient_canonical_scheduler_serializes_and_exits_when_idle`.
The test signals `first` twice without ordering the second signal before the worker
queues `second`. The scheduler has one pending callback slot. If the worker queues
`second` first, the caller's second `first` signal replaces it, producing
first-start/first-end/first-start/first-end/second. That is exactly the retained failure.
`scheduler-ordering.txt` deterministically reaches this ordering on unchanged production
code, with zero workers afterward. Neither this test nor live_service_runtime.py differs
from the WP29 base f5fff0b2. Targeted rerun passes 1/1. This is a pre-existing test ordering
assumption, not tape exhaustion or worker leakage; no unrelated scheduler repair made.
The COMMON file-by-file justification allowance applies; all failed logs are retained.

## R2 — repeated-session current RSS (complete, growth remains unattributed)

One process, same runtime and ONNX encoder, two back-to-back 600-second stub-decoder
meetings, 57,600,000-byte per-tape capacity. Both finalize: 9,600,000 samples accepted
and committed each, 602 runner calls per meeting (all stubbed; ZERO GPU requests).
Real speech/VAD/identity/rolling/terminal runtime included; HTTP, SQLite and MP3 are
excluded from this memory bench. This does not reproduce WP22's real-service absolute
616 -> 1,149 MiB footprint and cannot certify that full service's memory behavior.

| Sample | Current RSS bytes | MiB |
|---|---:|---:|
| Cold baseline before first frame | 147259392 | 140.4375 |
| After first final | 624230400 | 595.3125 |
| After second final | 651165696 | 621.0000 |
| Second minus first | 26935296 | 25.6875 |

**Verdict: second-meeting RSS grows again; owner UNKNOWN. No memory fix.** The first
runtime session remains present; session_count advances from one to two. Every measured
per-session Python owner count AND byte estimate after final is identical across the
two sessions. All three tapes and all pending PCM buffers hold zero samples after each.
These per-owner estimates exclude native allocations and are not a complete process
heap attribution. They do not identify an obvious owner of the extra 25.6875 MiB; the
brief authorizes a fix only with both growth AND an obvious owner. No allocator tuning,
threshold change, third session or speculative lifecycle cleanup was introduced.

Elapsed capture-through-final: 439.037137 s first, 441.218970 s second, using accelerated
audio time and a manually drained scheduler. Not real-time throughput qualification.
The two successful measurements are the complete `repeat-rss.jsonl`; the earlier traced
partial attempt is separately named and excluded. Probe process exited zero. `audit.json`
checks measurement completeness and release, not a claim that memory growth passed.

Final full gate: 1,932 passed, 2 skipped, 37 subtests (178.94 s). No production source
changed after this run; the evidence auditor's output labels were clarified to distinguish
two finalized RSS sessions from a memory-boundedness claim. Frontend 265 passed/28 files,
typecheck/build exit 0. Both source import and WP27 merge base f5fff0b2 verified locally.

## Contract deviations and limits

Automated state traces instead of interactive TUI, absorbed into the bench. Single-lane
capacity faults are isolated because silent PCM does not shrink tapes. The measured
pre-Stop client departure remains interrupted intentionally; accepted Stop then departure
completes. One unrelated scheduler race in a repeated full suite was explicitly adjudicated
above; the following complete suite passed. No real ASR, attended browser, deployment or
unlimited-duration memory claim. No policy/bound/protocol changes; no new production constants.
Fresh `/new` results belong in `docs/verify/wp29/VERIFY-RESULT.md`, not this implementation log.
