# WP12 fresh-context verification

Start only in a fresh `/new` session. Worktree:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp12-stop-latency-identity`
Branch: `mvpfix/wp12-stop-latency-identity`. Modify NOTHING outside it. No provider
calls, push, merge, deploy, GitHub, other worktrees or shared-service changes.
The WP request budget remains 300; 274 already used. An increase to 1200 was asked
but not approved. Do not treat elapsed time or this handoff as authorization.

Implementation: 33be55ec overlaps only the two independent terminal lane jobs;
9d10e0d8 fixes stale test inputs after reproducing all 19 failures on untouched
b31683a6 in the local scratch archive. Read the brief and evidence:
- `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md`
- `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP12-stop-latency-identity.md`
- `prototypes/streaming-diarization/wp12-stop-identity/NOTES.md`

Structural question: do unchanged lane jobs overlap safely, and do evidence/speaker
IDs survive silence? Primitives: lane tape, decoder result, lane album, one publication.
Invariants: same full-tape windows, fixed policy, preserved lane ownership, max two
terminal jobs, no partial publication. Unknown: 180 s live and multi-meeting scaling.
Falsifiers: >2 concurrent decoder calls, changed words/identity, lost lane evidence,
new test failure, incomplete final surface. Tools below detect these directly.

Run literally from this worktree, no installs:

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
WP12_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git status --short
git branch --show-current
git rev-parse HEAD
"$WP12_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
bash prototypes/streaming-diarization/wp12-stop-identity/check-python.sh > evidence/mvpfix/wp12/fresh-python.txt 2>&1
bash prototypes/streaming-diarization/wp12-stop-identity/check-frontend.sh > evidence/mvpfix/wp12/fresh-frontend.txt 2>&1
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/audit.py > evidence/mvpfix/wp12/fresh-audit.json
```

Expected: clean starting tree, named branch, import inside this worktree; Python
1802 passed / 2 skipped / 37 subtests; frontend 230 tests / 26 files; typecheck and
build succeed. Audit: 274/300 completed calls, max 2 in flight, eight final/saved
agreements, exact fixed-24 saved segments, 24/60 per-speaker ordered words equal.
Audit uses existing private scratch SQLite READ ONLY; never commit those databases,
audio, credentials or transcripts. Verify no listeners on 18112/17872 (`lsof -nP
-iTCP:18112 -iTCP:17872 -sTCP:LISTEN`; empty result/exit 1 means none).

Full Python tests rewrite WP2 screenshot fixtures. Restore ONLY generated changes:
`git restore -- evidence/mvpfix/wp2/production-1280.png evidence/mvpfix/wp2/production-390.png evidence/mvpfix/wp2/production-400.png`.
Inspect `git diff --check` and status. If a new failure appears, investigate before
claiming verification. No assertions or production policy may be weakened.

Write VERIFY-RESULT.md: actual fresh-session status, checked SHA, exact counts,
commands/log paths, audit result and limitations. Commit it plus fresh evidence
locally. Then report in this pane in <=60 lines: branch/final SHA, prototype verdict,
changed files, tests, timings, remaining work and deviations. DO NOT claim WP12
fully accepted: 60 s is 16.175 s (prototype), exceeding 10 s; 180 s and required
matched alternation arms are unmeasured because the fixed 300-call cap cannot cover
them. Fixed production 24 s is 7.315 s; original 11.803 s; mono 1.970 s. 60 s mono
4.424 s / serial 26.636 s. Identity premise is false: supplied mic fixture has two
voices; second birth score 0.084412 vs 0.35 with first album retained. No policy fix.

Operational note: tmux default/current target resolves to lead MOSS:2.1; NEVER send
there. The executing Codex pane is explicit MOSS:3.1 / %20. No owned servers or
tunnels remain. The delayed `/new` handoff script exits after submitting this task.
Prior context consulted memory only for scope; final memory citation if required:
MEMORY.md:5484-5486, note=[protected MOSS scope refreshed against current brief].
