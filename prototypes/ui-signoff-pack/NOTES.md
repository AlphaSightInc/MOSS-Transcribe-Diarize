# WP24 prototype verdict

Question: does every requested reachable UI state render truthfully and legibly at three viewports?
Primitives: source envelope, viewport, rendered DOM/PNG. Removing any loses truth, constraint, or observation.
Invariants: real integrated assets; source provenance explicit; policy/threshold/frame protocol unchanged.
Unknowns: physical-device/OS-picker rendering, operator pixel acceptance, D3 shared-mode decision.
Falsifier: misleading copy, unnamed controls, AA failure, or clipped/overlapping useful content.
Tool decision: Chromium and computed styles measure presentation; real decoder supplies public transcripts;
source replay exposes intermediate states without burning decoder calls. Replay does not prove backend execution.

Measured initial verdict: NOT universally legible/truthful. 43 states × 3 viewports = 129 captures.
F1: selected History secondary text 4.22:1, below body-text AA 4.5:1.
F2: 14 failure variants and truncation overflow the 400px viewport; header status and title collide.
F3: speaker rename says “active meeting”, but the same dialog works on saved meetings.
No missing interactive accessible names; no positive tabindex in this population.
This falsifies the all-clear claim, not feasibility of a capture pack. Brief explicitly authorizes these repairs.

Harness failed attempts: initial font route omitted /fonts; corrected to served asset bytes. Initial color
parser mistook CSS color(srgb) channels for 0–255 and propagated covered gradients; corrected via browser
color conversion and opaque-background reset. Discarded initial contrast results. First fake share-picker
setup returned an unresolved Promise from evaluate; terminated that owned process and corrected the harness.

Real inputs: public Bill Ackman/Keyu Jin corpus, API-fed overlapping live capture; 39.329s wall time;
real 30s lease expiry; actual browser file upload, 12s public Bill clip, completed with 4 saved segments.
The bench is retained as the requested repeatable sign-off pack generator, not production machinery.

## Completed audit additions
F2 also occurred on desktop: status text extended under the intentionally overlapping transcript header.
Bounded it to existing 280/240px rail values. F5: real Stop contrast 4.12:1 → 6.50:1 using --danger.
F6: stale LiveTranscribe fallback changed to MOSS. Existing design token values and geometry tests preserved.
F4: early Share during pending microphone initialization is a real reachable behavior defect, deferred
outside WP24's copy/aria/CSS authority. Shared privacy copy deferred to D3.

Additional failed attempts: first geometry regression read before async selection (0 rows), corrected to
wait for selected card. Initial stop regression sampled native color during CSS transition; disabled
transition in the static color test, then 7/7 passed. First dialog check ran before modal opened; second
mistook Chromium's browser-chrome Tab stop for background focus. Waiting for modal/input and checking actual
background controls proves the native cycle and 3/3 Escape focus restoration. Browser acquisition tried
Share before mic finished twice, exposing F4; successful acquisition waits for its actual ready message.

Full-suite history: 1907 passed/2 skipped/37 subtests before new Stop regression;
then 1 failed (new stop-color test sampled transition), 1907 passed/2 skipped/37 subtests;
corrected test: 1908 passed/2 skipped/37 subtests. Final release suites are retained under checks/.
Latest frontend contains 250 tests. Fresh /new regeneration must compare the checklist, never nondeterministic
transcript pixels or timestamps. Core failures/notices/audio/history fixtures are explicitly labeled; they
are a disclosed limitation from the requested all-genuine-state interpretation, not backend acceptance.

## Fresh-session regeneration, 2026-09-18

Starting commit: 8d3a2850. User narrowed regeneration traffic to at most 100 requests; the existing
local-stack budget now enforces min(100, remaining cumulative allowance). No production policy changed.
One regeneration succeeded with 7 calls (56 cumulative), 52 states and 156 PNG/copy pairs; checklist
byte-identical. Zero measured contrast/name/horizontal-overflow/checked-overlap failures; keyboard 3/3.
8009 contrast occurrences passed; 616 gradient/opacity occurrences remain manual review, not passes.
315 clipping candidates are intentional ellipses; no non-ellipsis candidate or positive tabindex.

F7: root VERIFY.md and VERIFY-RESULT.md violated scripts/check_verify_layout.sh. Standalone check failed
for both paths before the move, passed afterward. Moved them to docs/verify/wp24/; no product repair.
Fresh complete-suite results and source-line finding inventory: docs/verify/wp24/VERIFY-RESULT.md.
