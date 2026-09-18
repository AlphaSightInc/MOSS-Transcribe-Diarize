# WP19 — literal fresh-context verification

First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp19-file-identity-album`.
This is the user-requested fresh session after `/new` in MOSS:3.4. Do NOT repeat `/new`.
Read AGENTS.md, evidence/mvpfix/wp19/NOTES.md and COMMANDS.md, and prototype NOTES.md.
Modify nothing outside this worktree. No push/merge/rebase/deploy/GitHub, peer messages,
GPU requests, tunnels, or shared-service changes. Finish verification and report in THIS pane.

Question: does the measured File-only album composition survive a fresh import/context?
Primitives: local voices, canonical album, retained vector ledger, speaker-only rewrite.
Invariants: unchanged words/times/window decoder/live policy/live behavior/saved schema.
Falsifiers: repeated perfect voices split; real replay differs; any full-suite failure;
changed text/time; claimed enroll/export path does not reach actual consumers.
Tools below each detect those failures. Do not merely inspect old pass counts.

Branch `mvpfix/wp19-file-identity-album`; implementation commits ad7575ae (lease fixture),
448a4cf32c0dc13981b7472a57f3badde320b776 (album + acceptance), then this verify-doc commit.
Initial worktree should be clean. All raw input and caches needed for offline replay are
inside ignored .wp19runtime. Public reference corpus and pinned encoder are read-only inputs.

Run literally from this worktree; record failures, do not hide them:
```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp19runtime/tmp"
export XDG_CACHE_HOME="$PWD/.wp19runtime/cache"
export NUMBA_CACHE_DIR="$PWD/.wp19runtime/numba"
export npm_config_cache="$PWD/.wp19runtime/npm-cache"
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git status --short --branch
git rev-parse HEAD
"$PY" -c 'import moss_transcribe_diarize as m; from pathlib import Path; print(m.__file__); assert Path(m.__file__).resolve().is_relative_to(Path.cwd())'
"$PY" -m pytest -q -p no:cacheprovider -p evidence.mvpfix.wp19.local_scratch tests --basetemp=.wp19runtime/fresh-tests > .wp19runtime/fresh-python.log 2>&1
npm --prefix frontend test -- --run --configLoader native > .wp19runtime/fresh-frontend.log 2>&1
npm --prefix frontend run typecheck > .wp19runtime/fresh-typecheck.log 2>&1
"$PY" prototypes/streaming-diarization/wp19-file-identity-album/probe.py --fake-only --output .wp19runtime/fresh-fakes > .wp19runtime/fresh-fakes.log 2>&1
"$PY" prototypes/streaming-diarization/wp19-file-identity-album/accept_real.py --minutes 6 --output .wp19runtime/fresh-replay > .wp19runtime/fresh-replay.log 2>&1
"$PY" prototypes/streaming-diarization/wp19-file-identity-album/verify_evidence.py > .wp19runtime/fresh-evidence.json
bash scripts/check_verify_layout.sh
git diff --check
git diff c2e45867 --stat
git diff c2e45867 -- moss_transcribe_diarize/app/file_identity_album.py moss_transcribe_diarize/app/runner_composition.py moss_transcribe_diarize/app/phase2_web_cli.py moss_transcribe_diarize/app/phase2.py moss_transcribe_diarize/app/phase2_speaker_identity.py tests/phase2/test_owner_bound_live_meeting.py
lsof -nP -iTCP:18119 -sTCP:LISTEN
```
Expected: Python **1889 passed, 2 skipped, 37 subtests**, 21 warnings; frontend **249 passed,
28 files**; typecheck exit 0. `local_scratch` only confines fixture paths/sockets inside
this tree; it never changes assertions or product behavior. Frontend source change is a
test only, no asset build required. lsof exit 1/no output means owned tunnel is stopped.
All commands may be batched independently where safe; communicate progress every <=60 s.

Fake replay: 1 voice x 3 windows -> 1 identity; 2 -> 2, preserved text/time. Real 6-minute
replay uses retained decoder outputs and local pinned ONNX; **zero new GPU calls**. Expect
3 identities, 0 abstentions, 84/92 correctly attributed segments, 322.11/338.04 correct
reference-overlap seconds. Time is measured afresh, not asserted equal to old timing.
Compare fresh-replay/accept-real-6.json with evidence/mvpfix/wp19/accept-real-6.json:
`identities`, `mapping`, `segments`, `correct_segments`, `rows`, `text_time_unchanged`
MUST be identical. The offline verifier independently recomputes all 6- and 30-minute
attribution rows from retained segments and public reference.jsonl, compares all fields,
and runs the legacy resolver on the SAME raw decoder outputs: 7 -> 3 and 31 -> 3,
text/time exactly equal, 20/20 lease records, exactly 18 original decoder requests.

A1/A2 are explicit tests in test_file_identity_album.py. A4: admission, provisional
replacement, ambiguity, retrospective relabeling and provider failure match existing live
modules/oracles. FileMeetingTasks + WindowedRunner + real WAV/MP3 archive save/reopen and
manual enrollment use fake perfect vectors/decoder; fileAlbumExports.test.ts consumes the
actual saved artifact through all five frontend serializers. It is not a real-browser
click campaign and is not a claim about acoustic enrollment accuracy. The separate MP3
prototype measured PCM/MP3 cosine .969589, 5 s eligible, .6 s refused.

Inspect change boundaries: manifest thresholds unchanged; no live identity module edits.
Account File vLLM defaults album, documented --file-identity legacy fallback for one release.
Live terminal previously shared File runner, so composition uses the same decoder with
legacy identity explicitly, tested in test_runner_composition. No window decode or saved
schema change; new enrollment reconstructs requested evidence from retained audio.
Existing single-window/HF path unchanged. The resolver cannot fix wrong local diarization.
A3 30 min = 420/464 correct segments, 1592.97/1684.98 overlap seconds, 0 abstentions.
A5 15-window resolver time **332.007926 s including embedding**; six-minute **62.894428 s**.
Original decoder use: 18 serial calls, 93.561772 s total, 21176 output tokens, own 18119.
No deployment or cross-corpus capacity/quality claim. No timing gate was specified.

Initial authoring failures: nonexistent HTTP export endpoint (1 fail/22 pass), then JSON
string-count test double-counted target keys (1 fail/248 pass). Corrected to actual frontend
exports and parsed turn text. No product failures waived. Lease now drives actual expiry
callback after capture+renewal via existing fake timer; configured 30 ms policy unchanged.
Initial repeat campaign passed 20/20 separate pytest processes.

If fresh checks fail, record evidence, fix only WP19-scoped defects, rerun affected checks
and full suites as needed. Do not declare A1–A5 passed on stale outputs. If all pass:
- Write docs/verify/wp19/VERIFY-RESULT.md: fresh context after /new, tested SHA, exact counts,
  PASS/FAIL per A1–A5, real replay equality, timing, limits/deviations.
- Write evidence/mvpfix/wp19/fresh-summary.json. Change summary.json fresh_context from
  pending to PASS and NOTES.md opening to include fresh verification pass.
- Commit those locally, verify clean state. Stop every process you started.
- Final report <=60 lines in this pane: branch/final SHA; prototype verdict; changed files;
  A1–A5 exact numbers; lease 20/20; costs; remaining attribution errors and scope limits;
  deviations; no push/merge/deploy/GitHub. Include a link to VERIFY-RESULT.md. No question.

Preparation consulted memory for worktree/evidence boundaries only; all WP19 facts were
read/measured here. Preserve this memory citation at the very end of the final report:
<oai-mem-citation>
<citation_entries>
MEMORY.md:5485-5486|note=[worktree isolation and local evidence boundaries]
</citation_entries>
<rollout_ids>
</rollout_ids>
</oai-mem-citation>
