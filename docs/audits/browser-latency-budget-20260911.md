# Browser latency budget — 2026-09-11

**Ship the bounded polling improvement; do not claim a 1.5-second browser saving.**
Active polling changes 250 → 100 ms; non-active polling remains 2 seconds. A controlled
real-reader experiment isolates a median readiness-to-DOM improvement of 45.6 ms.
The known-speech live test does not show a material end-to-end improvement.

## Findings

**F1 — The original comparison did not establish a browser-only 1.5-second gap.**
`tests/e2e/verify_workspace.py` starts its row-4 clock before Playwright clicks Start,
then observes a locator from Python. The API probe instead subtracts the first decoded
segment's 0.84-second start. Neither is an independently aligned physical speech clock.
Capture is already running for preflight before Start. In addition, the two runs do not
share a decoder-load control. These measurements are useful separately, not subtractable.

**F2 — Polling helps, but rendering was already fast.**
Seven fixed server-readiness phases (10, 50, 90, 130, 170, 210, 240 ms) were replayed
against each real bundled reader, with controlled API responses and no decoder.
These are seven phase samples, not a population latency percentile.

| Controlled reader | 250 ms baseline | 100 ms patch |
|---|---:|---:|
| Ready → DOM median | 128.4 ms | 82.8 ms |
| Ready → DOM maximum sampled | 249.9 ms | 104.3 ms |
| Snapshot JSON → DOM | 0.8–0.9 ms | 0.8–0.9 ms |

The reader uses Preact signals. Snapshot and event requests run concurrently; signal
publication follows their completion. No extra render timer was found. `since_version`
continues from the applied snapshot; unchanged responses preserve active cadence.
An event needing a snapshot is deferred, with snapshot cursor reset to zero, rather than
dropped. Existing cursor/deferral tests remain green. Splitting the request pair or adding
server push has no demonstrated necessity for this measured improvement.

**F3 — Real capture has a batching and mixing cost.**
Constructed fixture: one second of preflight tone, silence until exactly 4.000 seconds,
then 11 seconds from `mono_javier_intro_50s/audio.wav` starting at 0.84 seconds.
Both microphone and shared-audio paths use the real browser capture code. Correlation
against captured PCM establishes the injected waveform onset; audio is retained only
in temporary local artifacts, not this report. Correlation is 0.9945 microphone and
0.9973 system. Browser AudioContext/render-clock alignment has roughly 8 ms quantum
resolution; this is not physical microphone hardware latency.

| Stage, validated fixture runs | Before | After |
|---|---:|---:|
| Descriptor frame size | 8,000 samples / 500 ms | unchanged |
| Upload cadence, microphone / system median | 503.2 / 503.8 ms | 503.3 / 503.9 ms |
| Onset → containing worklet callback, microphone / system | 9.3 / 46.9 ms | 9.2 / 57.1 ms |
| Callback → upload request, microphone / system | 0.8 / 0.6 ms | 0.7 / 0.6 ms |
| Encoding median | 0.4 ms | 0.4 ms |
| Frame HTTP round trip median | 6.3 ms | 7.4 ms |
| Upload → mixer frontier beyond onset, microphone / system, replay estimate | 551.8 / 952.2 ms | 568.1 / 936.3 ms |
| Snapshot request interval median, before first text | 258.4 ms | 106.6 ms |
| Matching-speech snapshot → DOM | 0.7 ms | 0.8 ms |
| Known onset → matching speech DOM, microphone / system | 3298.6 / 3288.2 ms | 3300.1 / 3283.9 ms |

The mixer estimates replay recorded request headers through `LiveCompatibilityMixer`
with the actual descriptor's 16,000-sample maximum mixed output. They are **not server
admission timestamps**: request arrival/processing is bounded only by the measured HTTP
round trip, and the replay excludes queue backpressure. Each lane's onset is a separate
capture-clock coordinate; do not add the lane columns together. The actual mixer seals
ordinary frames with successor timestamps, retaining roughly one-frame lookahead.
This explains why cheap encoding is not the entire capture budget.

For the matching speech's canonical span (span 2), decoder time was 149.6 → 153.5 ms;
queue wait was 77.9 → 108.9 ms. The remainder includes span-freeze/context wait, mixing,
identity work and polling. No shared server/browser monotonic-clock calibration was
installed, so this is not a falsely precise additive attribution of every millisecond.

`captureClient.makeV2Frame` requires exactly descriptor-sized frames. Changing only the
first frame would violate that contract. No frame size, lane, mixer, canonical-span,
identity or draft-lane setting was changed. The local stack's clean worktree was pinned to `b76b5b5c`; its service was not restarted.
The baseline browser bundle was built from `24197fdd`; the after bundle differed only
in polling cadence. The local stack's draft lane was off; this
does not measure the host's proposed draft-on configuration.

**F4 — First-any-text can be a misleading latency metric.**
The validated fixture's first preview in **both arms** was a model refusal (body removed by the content-boundary audit), not spoken audio. A content-free boolean prefix
check and a separate `known_speech_dom` clock now distinguish first-any-text from the
first appearance of the known spoken fixture prefix. Both runs ultimately completed with corpus speech.
The earlier unvalidated fixture observations of about 945 → 699 ms were therefore
rejected as speech-latency evidence. The later validated pair gives about 3.29 → 3.28 s.
This is a concrete decoder/preview content finding, not evidence that the polling patch
causes it. No decoder policy or acceptance predicate was weakened or changed. The subsequent
rebase included `2c285f4e`, which handles empty speechless outputs; it does not by itself
establish a remedy for this nonempty refusal. These captures do not measure that newer
server implementation.
The fixture's copied reference is only a harness prerequisite; it is not a WER result.

**F5 — Required row 4 rerun, retained without attributing provider recovery to the patch.**

| Original corpus, unchanged row-4 harness | Before | After |
|---|---:|---:|
| Python first-visible timer | 13.370 s | 3.322 s |
| Browser click → first DOM text | 13.059 s | 3.302 s |
| First canonical decode | 9.926 s | 0.244 s |
| Row 4 verdict | FAIL | PASS |
| Rename row 5 | PASS | PASS |

These row-4 timings mean **any nonempty text**, exactly as the existing harness defines
it. Their initial text was not phrase-validated. The decoder-time change dominates;
13.37 → 3.32 seconds is not a causal polling improvement. Historical row 4 was 3.825 s.
Known-fixture runs have separate identities and are not substitutions for this row.

## Decision and validation

**D1 — Keep the 100 ms active cadence.** It cheaply reduces the proven reader wait.
Idle/closing cadence, error backoff, cursor semantics, capture lifecycle, abort fencing
and transcript rendering are unchanged. At fast response times it permits about 10
snapshot/event pairs per second per active observer instead of 4; it does not create
additional decode work. Server request-capacity qualification remains distinct.

`phase2_acceptance_browser.py::product_regression` requires continued requests while
hidden during 2.5 seconds, not a maximum request count. The new deterministic test proves
100 ms background polling survives unchanged snapshots and stops after disposal. No
acceptance selector changed. Focused browser/preview tests: 14 passed. This is not a
claim that the entire host browser qualification ran locally.

Final suite after rebasing over `2c285f4e` and `e786a6e2`: **1,380 Python tests passed,
37 subtests passed, 2 existing skips; 196 frontend tests passed.** Generated assets
were rebuilt after the earlier summary-change rebase. Intermediate Python suite: 1,366;
initial pre-rebase suite: 1,355. Same skips/subtests throughout. Typecheck passed.
No local stack restart, database reset, host operation, or production-branch push.

Measurement tools, content-free traces and reproduction instructions:
`prototypes/streaming-diarization/browser-latency/NOTES.md`.
