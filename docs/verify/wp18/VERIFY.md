# WP18 — literal fresh-context verification

First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp18-file-identity`.
This is the fresh session after user-requested `/new` in MOSS:3.4; do not repeat `/new`.
Read AGENTS.md, `evidence/mvpfix/wp18/NOTES.md`, `COMMANDS.md`, and prototype NOTES.
Modify nothing outside this worktree. No push/merge/rebase/deploy/GitHub, peer messages,
GPU requests, tunnels or shared services. Only this document and retained files are needed.

Scope: identity wiring-only design is FALSIFIED, not fixed. COMMON.md explicitly says
stop a falsified fix and report. An independent requested truncation notice fix shipped.
Do not broaden into a new identity algorithm or silently lower any policy value.

Run literally from this worktree; record every result even if one fails:
```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp18runtime/tmp"
export XDG_CACHE_HOME="$PWD/.wp18runtime/cache"
export NUMBA_CACHE_DIR="$PWD/.wp18runtime/numba"
export npm_config_cache="$PWD/.wp18runtime/npm-cache"
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git status --short --branch
git rev-parse HEAD
"$PY" -c 'import moss_transcribe_diarize as m; from pathlib import Path; print(m.__file__); assert Path(m.__file__).resolve().is_relative_to(Path.cwd())'
"$PY" -m pytest -q -p no:cacheprovider -p evidence.mvpfix.wp18.local_scratch --basetemp=.wp18runtime/pytest-fresh tests > .wp18runtime/fresh-python.log 2>&1
npm --prefix frontend test -- --run --configLoader native > .wp18runtime/fresh-frontend.log 2>&1
"$PY" prototypes/streaming-diarization/wp18-file-identity/verify_evidence.py > .wp18runtime/fresh-evidence.log 2>&1
bash scripts/check_verify_layout.sh
git diff --check
git diff d769b010 --stat
git diff d769b010 -- moss_transcribe_diarize/app/phase2_audio.py moss_transcribe_diarize/app/phase2_file.py tests/phase2/test_file_digital_silence.py tests/phase2/test_file_failure_reasons.py tests/phase2/test_file_mp3_artifact.py tests/phase2/test_file_truncation_notice.py
lsof -nP -iTCP:18118 -sTCP:LISTEN
```
Expected initial state: clean branch `mvpfix/wp18-file-identity`; parent implementation
commit `82ab6d27`, plus this verification document commit. Python **1874 passed, 2 skipped,
37 subtests**, no failures; 21 existing warnings. Frontend **244 passed / 27 files**.
Evidence verifier: **6/6 exact resolver replay comparisons**, GPU calls zero. Fake cases
now yield resolver AND stitched counts **3/3 for one voice, 6/6 for two voices**. Real
six-minute before/enabled-provider counts **7/7**, versus **3** reference voices.
Full suites detect integration regressions; offline replay attacks whether the diagnosis
is reproducible. Any mismatch is failure to diagnose/report, not a waived exception.
No listener on 18118 is expected (lsof exit 1 with no output). No frontend source/assets
changed; typecheck/build are not necessary for these Python-only modifications.

Inspect product diff: only capture the measured FFmpeg warning as fixed safe notice,
preserve existing decoder output-cap metadata as notice, carry notices through File
completion, and adapt internal helper callers. All original silence assertions remain.
New real-FFmpeg + fake-decoder tests verify healthy/no-notice, truncated-media/notice,
and decoder-cap/notice through save/reopen. No raw stderr enters a saved notice.
No identity, bounds, sentinel, policy values, readiness, frame shape, window plan or
lifecycle authority changed. Design-doc addition records the unresolved measured defect.

Read test-summary.json: initial malformed test (3 failures), genuine red regressions
(2 fail/1 pass), 98 focused passes, first full-suite internal tuple callers (3 failures),
then 1874 full passes. Fake first probe's segments were clipped at ownership boundaries;
corrected probe keeps them inside every owned interval. Real measurements unchanged.
Read summary/decode/real JSON: 3 serial decoder requests, 19.603119876 s summed decoder
wall time, 3323 output tokens, 16.700404417 s enabled resolver. Safe public corpus only;
raw decoder/audio caches remain ignored scratch. Conditional 30-minute rerun not applicable:
repo-recorded production constructor is also disabled. Actual deployed process not inspected.
Original 31-identities/3-voices defect remains; no 31→3 claim, no identity success claim.
A revised file identity algorithm/composition needs separate authorization and prototyping.

Write `docs/verify/wp18/VERIFY-RESULT.md`: state fresh context after /new, tested SHA,
exact counts, each PASS/FAIL, and distinguish verification PASS from identity repair
FALSIFIED. Include remaining limits and contract deviations. Write compact
`evidence/mvpfix/wp18/fresh-summary.json`. Commit both locally; check clean status.
Then report <=60 lines in THIS pane: branch/final SHA, prototype verdict, files changed,
exact tests, before/after identity counts, decoder use/timing, truncation notice, blocker,
and deviations. No permission question; do not report before fresh verification finishes.

Preparation used memory only to preserve local-evidence versus deployment distinction;
all WP18 facts above were measured/read in this checkout. Preserve citation if reporting:
<oai-mem-citation>
<citation_entries>
MEMORY.md:5545-5548|note=[local evidence does not establish deployment acceptance]
</citation_entries>
<rollout_ids>
01a0a346-ad32-7180-aaa1-7f57555f2ad9
</rollout_ids>
</oai-mem-citation>
