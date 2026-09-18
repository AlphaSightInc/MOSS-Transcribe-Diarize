# WP17 prototype verdicts

Question: do lane commits retain the causal unit needed for workspace recognition?
Minimum primitives: pending acoustic unit (what was heard), committed assignment
(who owns it), enrollment album (durable evidence), publication observation (what
can be matched now). None can replace another: one-second causal evidence is valid
for matching but too short for enrollment. Existing thresholds remain unchanged.
Falsifier: committed lane speakers retain both original observations without a fix.

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/streaming-diarization/wp17/recognition_probe.py`
uses the real coordinator/provider/album with fake encoder. Before: 2 prepared
observations -> 0 committed observations; 2 album entries; 2 embeddings. The lane
commit's eager reconcile consumes pending vectors before publication. Hypothesis
confirmed. Preserve the immutable observations at commit before reconcile; keep
album timing, lane namespaces, workspace bank, thresholds and encoder calls unchanged.
Scripted state output substitutes for interactive TUI for repeatable regression.
The throwaway probe is deleted and absorbed into tests/test_live_lane_decode.py.
Current one-command reproduction: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python -m pytest -q -p no:cacheprovider tests/test_live_lane_decode.py -k preserves_causal`.

Real baseline: WP7 case 3 enrolls but has no label in the next 12-second meeting;
unknown/deleted voice also receives no label. Saved bank exists. Real quality
baseline reproduces WP14 final exactly: alternating system 9/106, microphone
10/48; overlap system 13/106, microphone 10/48. Immediate results differ with
scheduling; retained snapshots are the denominators, never guessed words.

F1 verdict: lane-merging hypothesis falsified for the reported ten microphone
additions. Exact same PCM alone yields the same ten additions. Five are proven
reference omissions, corrected only in a dedicated harness fixture. Remaining
five stay counted. See evidence/mvpfix/wp17/reference-adjudication.md. Broader
quality acceptance still fails; no decoder/threshold tuning is justified here.

Retained measurement scripts are absorbed into this standing bench. The 24/48 s
probe prints identity/surface state each action and retains private raw traces.
Paired-versus-alone edit distance is a differential measurement, not ground truth.

Final measurements: 12/12 duration/control captures complete; 8/8 saved lane text
comparisons identical (628 words), 8/8 terminal windows identical; 3/20 matched
rolling windows differ. Recognition 4/4 lane routes 3.526–3.528 s. Total decoder
requests 431/600. See committed evidence/mvpfix/wp17/ for every count and limit.
Verdict: recognition ordering fix verified; reported lane-addition premise falsified
by lane-alone control; reference corrected narrowly; product quality acceptance FAIL.

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
