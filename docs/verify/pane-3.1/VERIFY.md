# Fresh-context verification

Verify this checkout as evidence, not as a repair task. Do not edit production,
tests, or evidence. Run literally from this repository root:

```sh
set -e
test "$(git branch --show-current)" = "round3/scheduling"
test -z "$(git status --short)"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
"$PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
"$PY" -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
git diff --check
git diff a7a738cf9f9ff246f64c52c112e0bf597ba58241..HEAD --unified=0 -- moss_transcribe_diarize/app/live_lane_decode.py
jq -s '{starts:map(select(.kind=="start"))|length,ends:map(select(.kind=="end"))|length,peak:(map(.peak)|max),active:.[-1].active}' evidence/round3/wp54b/decoder-requests.jsonl
for port in 18311 19311 17831; do ! nc -z 127.0.0.1 "$port"; done
```

Expected: import is inside this clone; backend 2,067 passed / 5 skipped /
37 subtests; frontend 288/288; typecheck/build/diff-check clean. The only
`live_lane_decode.py` production additions are lines 344-350 and 365-367.
Decoder receipt is 165 starts/165 ends, peak 1, final active 0; all three ports
are closed.

The verification verdict may be PASS only with the explicit qualification:
WP54b headed evidence remains INCOMPLETE. Its retained receipt is rejected
because finalization was still `running` and the pre-correction matcher crossed
source intervals. The corrected 8/8 deterministic instrument is implemented but
has no corrected headed measurement. Any test failure, changed owned range,
live process, budget mismatch, or claim that the rejected headed receipt passed
falsifies verification.

After running, create `docs/verify/pane-3.1/VERIFY-RESULT.md` with final SHA,
commands, exact counts, PASS/FAIL, the WP54b qualification, and any unexpected
working-tree change. The retained `VERIFY-RESULT-initial-fail.md` documents the
prior root-layout failure; do not overwrite it.
