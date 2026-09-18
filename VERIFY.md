# WP12 fresh-context verification

Start only in a fresh `/new` session. Worktree:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp12-stop-latency-identity`
Branch: `mvpfix/wp12-stop-latency-identity`. Modify NOTHING outside it. No push,
merge, deploy, GitHub, other worktrees or shared-service changes. The fresh-session
user explicitly raised the total budget to 1200 (max two in flight, own port 18112,
check vLLM running/waiting before each batch). Matched instrumentation now used
339 calls total. The verification commands below make no provider calls.

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

Expected: clean starting tree at a02a8491 before new instrumentation, named branch,
import inside this worktree; only bench/evidence/docs changed afterward. Python
1802 passed / 2 skipped / 37 subtests; frontend 230 tests / 26 files; typecheck and
build succeed. Audit: 339/1200 completed calls, max 2 in flight, 11 final/saved
agreements, exact fixed-24 and new matched-24 saved segments, 24/60 historical
per-speaker ordered words equal. Regenerate matched phase/embedding accounting:
`"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/analyze_embeddings.py > evidence/mvpfix/wp12/matched-embedding-audit.json`.
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
fully accepted: 60 s is 16.175 s (prototype), exceeding 10 s; 180 s and additional
matched alternation arms remain unmeasured. The new budget permits more calls,
but the user instructed stopping optimization if the cost is inherent. The new
matched 24 s arms show 11.328 s serial, 6.839 s concurrent, 1.881 s mono. Terminal
embedding is 43.53 audio-seconds / 2 calls / 12 intervals for lanes and zero for
mono; no complete terminal call duplicates a prior embedding input. Causal album
references already reused. See NOTES.md F1–F3 for the wait/embedding adjudication.
Earlier fixed production 24 s was 7.315 s; original 11.803 s; mono 1.970 s. 60 s mono
4.424 s / serial 26.636 s. Identity premise is false: supplied mic fixture has two
voices; second birth score 0.084412 vs 0.35 with first album retained. No policy fix.

Operational note: tmux default/current target resolves to lead MOSS:2.1; NEVER send
there. The executing Codex pane is explicit MOSS:3.1 / %20. No owned servers or
tunnels remain. The delayed `/new` handoff script exits after submitting this task.
Prior context consulted memory only for scope; final memory citation if required:
MEMORY.md:5484-5486, note=[protected MOSS scope refreshed against current brief].
