# WP6 resumed authority and provenance

2026-09-17 fresh session; initial branch mvpfix/wp6-capacity-baseline at
c3d159284ba2687db073237814a926c8a81ed759, clean. Production remains at base 37979e53;
Part 0 a20595a5 accepted by user, not re-litigated.

User authorization: own 18106 loopback SSH tunnel to existing vLLM; local stack;
1x120 -> 2x300 -> 4x600, then 8-session overload only after a clean 4x600.
Thirty-second resource/queue samples; pause after two consecutive foreign-load
samples; resume when clear. No vLLM restart/configuration; no 7861/7862 access.

Commands use COMMON.md Python with PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
`python prototypes/capacity-campaign/run.py --sessions N --seconds S`.
Local app port 17866; state, logs and audio under ignored .wp6-tmp.

Source gates read: docs/phase2-afk-charter.md G4; private issue 22 and 27
(gh issue view --repo aiSight-us/MOSS-Transcribe-Diarize). Origin issues are disabled;
failed read attempts made no writes. This baseline does not claim those deployed,
same-SHA release gates. No source-content cross-talk adjudication or fixed
six-case quality macro is inferred from owner denial or looped-clip WER.

Harness corrections: exact two-sample pause rule; wait at busy preflight; avoid
post-pause catch-up burst; detect interleaved foreign completions; require an
entire clear sample interval before resuming; single-session fairness marked N/A.
The first 2x300 attempt was deliberately interrupted to repair the resume condition;
its evidence and runner are preserved, and its calls count toward the total.

## 2026-09-18 fresh continuation (Fable, MOSS:2.1)

Starting branch mvpfix/wp6-capacity-baseline at 57907d76, clean. User explicitly
authorized a private manifest copy raised to the deployed bound, or 57,600,000 bytes
if unknown; one 4x600 rerun, then eight sessions only if clean. Shared manifest must
not be edited. Repo-only deployed-bound investigation; no host access for that task.
The campaign retains previously authorized read-only GPU sampling and own tunnel
18106/stack 17866. No push/merge/deploy, shared-service changes, or peer messages.
Fresh-context verification refers to the supplied 57907d76 evidence; new measurement
harness changes and results are checked in this continuation, not claimed to have
another context reset. Old VERIFY.md expected exactly four runs; that expectation
is superseded by the explicitly authorized additional run(s), not silently discarded.
