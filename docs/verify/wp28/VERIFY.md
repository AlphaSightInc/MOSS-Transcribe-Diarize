# WP28 literal fresh-context verification

Original user assignment: Fable (MOSS:2.1) assigned WP28: reduce file-album resolver
cost (historical 332 s / 30-minute file) without changing any identity decision.
Execute completely, actual `/new`, then <=60-line report in this pane. WP26 is
accepted and merged. No push/merge/deploy/GitHub; vLLM only via own port 18128.
This verification requires ZERO decoder calls; no tunnel or server is needed.

First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp28-file-resolver-perf`.
Modify nothing outside it. Branch `mvpfix/wp28-file-resolver-perf`; baseline
`d49fc50a99ec71867ddee8642f1e9b1f87e9a87e`; implementation `418258c6`.
Verification-doc commits after that implementation are expected. Do not rebase.

Read in order:
1. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md`
2. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP28-file-resolver-perf.md`
3. `evidence/mvpfix/wp28/NOTES.md`, then
   `prototypes/streaming-diarization/wp28-file-resolver-perf/NOTES.md`.

Q1: Can independent acoustic probes execute concurrently while every ordered
identity decision remains unchanged? P1: PCM interval -> normalized embedding ->
ordered mean -> serial album update/sweep. I1: same samples, interval inclusion,
normalization/reduction order, policy values, attributions and diagnostics.
U1: other hosts, different corpora and concurrent-file capacity are unmeasured.
F1: any complete-result byte mismatch, lost probe, changed live/default scheduling,
worker left after failure, new suite failure, or no fresh wall-time improvement.
T1: full suites detect integration regressions; retained real input plus serial
and parallel runs detect changed evidence/results and measure actual cost.

Before running, check branch/import custody and inspect the implementation diff:
`git diff d49fc50a 418258c6 -- moss_transcribe_diarize/app/file_identity_album.py moss_transcribe_diarize/app/live_provider_bundle.py moss_transcribe_diarize/app/speaker_identity.py tests/test_file_resolver_performance.py tests/test_live_provider_bundle.py`.
Expected: scheduling constructor argument default one; file album requests four;
one loaded CPU ONNX session; ordered pool.map; scoped pool cleanup. The live test
double accepts the new constructor argument AND asserts it remains one. No identity
threshold, admission value, QUALITY_BOUNDS, sentinel, readiness, frame or lifecycle
change. Exactly three production files, plus tests/docs/evidence.

`git status --short` should be clean except expected untracked
`evidence/mvpfix/wp28/context-transition.json`, written by the own-pane `/new`
transition. No peer pane was addressed. The implementation chat ID is recorded in
`environment.json`; the fresh script requires a DIFFERENT current CODEX_THREAD_ID.
A new shell is not a fresh chat. If no actual fresh context, do not claim the gate.

Execute literally:

```bash
bash prototypes/streaming-diarization/wp28-file-resolver-perf/verify.sh
```

It runs the ENTIRE Python suite with real equality fixtures enabled, full frontend
suite, serial remeasurement, production remeasurement, exact old-output comparisons,
probe-count equality, wall-time improvement, diff and verification-layout checks.
Expected ~12 minutes total; continue concise progress updates. All scratch is in
`.wp28runtime/` or `runs/wp28/`; shared node_modules is read through the existing
symlink, Vite uses the runner config loader. No npm install or asset rebuild.

Expected: 1929 Python passed, 2 existing unavailable-corpus skips, 37 subtests;
250 frontend passed / 28 files. Both WP28 real fixtures MUST run, never skip.
Initial corrected full gate already passed these counts before this document.
Fresh equality: 2/2 serial and 2/2 production comparisons against original baseline
bytes. Four perfect-vector cases (1/2 voices, 3/15 windows) in the suite; reverse
completion must preserve reduction order; failure must preserve abstention and
close workers. Per real run: 3/15 windows, 9/45 embedding calls, 107/575 ONNX probes,
391.32/2059.98 audio seconds, one session, 3 identities, 0 unattributed segments.
Raw window groups contain 110/590 segments (overlap included); this is not the
stitched 92/464 scored-segment population from WP19.

Initial measured serial -> production: 60.177873 -> 18.085652 s (3 windows),
313.204362 -> 92.432865 s (15), complete serialized results byte-identical.
Fresh timings need not equal these host timings. Report actual fresh before/after.
ONNX/features durations are aggregate worker seconds; resolver/embedding are wall.
Exact repeated intervals: zero within a window, 1/14 across overlapping windows.
No repeats skipped, no caches or evidence caps. Product four-worker process peak
1,431,027,712 bytes on Apple M3 Ultra; not a concurrent-capacity qualification.

Earlier failures were fixed and retained: missing pytest basetemp parent (launcher
now creates it); narrow live-provider fake constructor (now accepts scheduling and
asserts live stays serial). No failure waived. If new failures occur, keep logs
before rerunning and diagnose; never weaken equality assertions or policy.

Write `docs/verify/wp28/VERIFY-RESULT.md`: pass/fail, exact counts, fresh chat IDs,
real byte-equality denominators, fresh timing table, failed attempts, limitations
and deviations. Include transition evidence and fresh results in a LOCAL commit.
Stop every process you start; no tunnel/server was needed. Finish with <=60-line
report in this pane: branch/final SHA, prototype question/verdict, changed files,
tests/counts, before/after seconds for 3/15 windows, remaining limits/deviations.
Do not send messages to Fable or other peers; this pane is the requested report.
