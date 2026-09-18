# WP17 — lane quality and voiceprint recognition

Base integration/mvp-fix-20260917 @ 41cfebb9388830996e1666498f0ca3bf4cebbd5b.
Own branch mvpfix/wp17-lane-quality-voiceprint; own tunnel 18117, TLS service 17877.
State /private/tmp/wp17/state (short socket path), ignored transcript/audio scratch
runs/wp17/. No shared service or other checkout source changed.

## F1: reference mismatch, not ten invented lane words

Read reference-adjudication.md, retained-transcript-diffs.json, source-window.json.
Original final reproduced: alternation system 9/106 edits, microphone 10/48
additions; overlap system 13/106 edits, microphone 10/48 additions. Lane-alone
same-PCM decode gives identical ten mic additions. Unity gain reduces fillers but
not the missing five-word sentence tail. Correct only the five source-supported
words in a dedicated harness fixture; do not rewrite historical corpus evidence.
No quality threshold, attribution predicate or duplicate predicate relaxed.
The remaining immediate/system failures remain failures, not an acceptance claim.

## F2: causal evidence consumed before match publication

The actual lane coordinator eagerly reconciles committed vectors into its album.
This pops pending vectors; later match_observations reads zero. Mono delays that
reconcile and therefore retains its match observation. Fake encoder probe: prepared
2 -> committed 0, album 2, embeddings 2. Regression fails for either enrollment lane.
Capture original observations at accepted lane commit, before reconcile, bounded to
one snapshot version. Preserve distinct lane speaker IDs and shared workspace bank.
Re-reads do not re-embed. All thresholds and enrollment floors unchanged.
Focused regression/provider/bank tests: 70 passed; oracle tests: 20 passed.
Real WP7 recognition baseline: enrolled bank, no next-meeting name within 12 seconds.
After fix: measurement details in recognition-after/stress-results.json.

## Method and failed attempts

Prototype contract/verdict: prototypes/streaming-diarization/wp17/NOTES.md.
Scripted state probe instead of interactive TUI: reproducible transition evidence.
A malformed tool orchestration string failed before shell execution. Initial file
lookups used wrong module paths; corrected without changes. Initial read-only
SQLite open required immutable=1 to avoid journal access; no source DB writes.
The brief's -10 dB/half-active harness description differs from current source:
WP14 complete-window harness uses gain .03 and exact-zero inactive frames.
Own 600-call ceiling includes all standalone and server calls; no more than two
in flight. Server restarts deduct prior requests. No push/merge/deploy/GitHub.

## Suite gate and interpretation

Full Python: 1869 passed, 2 skipped, 37 subtests passed, 21 warnings in 139.15 s.
Both skips are absent operator-provisioned identity/accuracy corpora. Frontend:
242 passed / 27 files; typecheck/build pass, no asset change. Full commands retained
in COMMANDS.md. WP14's existing path-redirection test plugin copied to WP17 to keep
short socket fixture paths local; no assertions or production behavior altered.
One standalone re-score attempt used system Python 3.9 (dataclass slots unsupported)
and failed before scoring. Repeated with the mandated venv; result retained.

Real recognition is API snapshot latency, not browser DOM latency. All four routes
3.526–3.528 s; saved names retained. The baseline had no name during active capture
but did recognize at terminal album publication: the bug is live recognition timing,
not loss of the workspace bank. Deleting the first profile before the reverse-lane
case removes its links as designed; current DB link counts are not historical counts.

## Final duration isolation and budget

12/12 meetings complete: 24/48 seconds × alternation/overlap × paired/system
alone/microphone alone. All 8/8 saved lane comparisons have zero word edits against
identical lane PCM alone (628/628 compared words). All 8/8 terminal windows match.
120 paired producer windows retained: 92 have exactly matching control geometry;
28 differ in span geometry and are explicitly unmatched. Of the 92 matched windows,
89 match text exactly; 3 rolling windows differ. Do not claim universal intermediate
identity; diffs show the variation and terminal convergence. No partial-window
reference WER is invented. See duration-diffs.json and duration-summary.json.

Full-window after rerun: final/reopened mic 5/53=9.43396% on both cases, 0 attribution,
0 duplicates, 0 speaker-lane conflicts. System alternation 9/106=8.49057%; overlap
13/106=12.26415%. The standalone system decode also yields 13/106: the overlap final
failure does not require a per-lane merge. Immediate after: alternation system
15/106=14.15094%, mic 11/53=20.75472%; overlap system 33/106=31.13208%, mic
6/53=11.32075%. Immediate values depend on publication timing; both cases remain
FAIL under unchanged quality bounds. No assertion is weakened to make acceptance pass.

Decoder count 431/600 = 427 stack ledger rows + 4 standalone calls. Stack request
indices restart across its three processes; count rows, not last request index.
Own semaphore <=2; sampled GPU waiting counters zero. Stack PIDs 7504, 9630, 12992
and tunnel PID 6498 stopped. Ports 17877/18117: no listeners (cleanup.txt empty).
No deploy, shared-host restart, push, merge, GitHub or external messages.

Remaining: overall quality acceptance FAIL. Five source-unadjudicated filler/repeat
words remain counted on mic; system/reference errors and immediate snapshot errors
remain. Browser DOM recognition latency not measured; API four-route latency passed.
F1's per-lane-merging premise is falsified for this input; no speculative audio or
policy repair performed. Fresh-context verification follows VERIFY.md via /new.

## Fresh-context verification — 2026-09-18

Fresh session at 12b9e16337a2130584f94d68064ec07d847c7689, clean start. Literal
VERIFY.md executed: audit PASS; initial Python 1 failed, 1868 passed, 2 skipped,
37 subtests passed (143.76 s). Failure is test_verify_layout_current_tree:
root VERIFY.md introduced by 12b9e163 violates the existing docs/verify/<wp>/ rule.
Moved VERIFY.md unchanged to docs/verify/wp17/; VERIFY-RESULT.md lives alongside.
No source, tests, assertions, thresholds or policy altered. Full Python rerun:
1869 passed, 2 skipped, 21 warnings, 37 subtests passed in 140.20s (0:02:20), exit 0.
Frontend 242 passed / 27 files; typecheck/build passed, assets identical.
Fresh independent source check: 400000/400000 PCM samples equal at long-source
115–140 s; fixture adds only five leading words. Recount confirms 8/8 saved
lane pairs (628 words), 8/8 terminal windows, 3/20 rolling-window differences,
28 unmatched canonical windows. Evidence audit PASS is not quality acceptance:
0/2 full cases pass the unchanged immediate 16.6655% / final 9.5074% bars.
Retained recognition API routes pass <=4 s; browser DOM latency unmeasured.
Fresh decoder requests 0/100; historical 431/600. No service/tunnel started,
no push/merge/deploy or other-worktree writes. Full failed and passing logs in
evidence/mvpfix/wp17/fresh-*. Details: docs/verify/wp17/VERIFY-RESULT.md.
