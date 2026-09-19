# Fresh-context verification result

## Verdict

**FAIL**

Final SHA: `be6a5e2faa4ca1d74f05bc6fdaf6c43fc91e673a`

WP54b headed evidence remains **INCOMPLETE**. Its retained receipt is rejected because finalization was still `running` and the pre-correction matcher crossed source intervals. The corrected 8/8 deterministic instrument is implemented but has no corrected headed measurement.

## Commands

Run literally from the repository root:

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

Because `set -e` was active, execution stopped at the failing backend suite. The remaining frontend, typecheck, build, diff, decoder-receipt, and port commands were not executed.

## Results

- Branch check: PASS (`round3/scheduling`).
- Initial working tree check: PASS (clean).
- Import provenance: PASS (`/private/tmp/moss-round3-20260919/scheduling/moss_transcribe_diarize/__init__.py`).
- Backend: FAIL — `1 failed, 2066 passed, 5 skipped, 21 warnings, 37 subtests passed in 182.75s`.
- Failure: `tests/phase2/test_tls_preparation.py::test_verify_layout_current_tree`.
- Failure output: `FAIL: VERIFY.md belongs under docs/verify/<wp>/`.
- Frontend tests: NOT RUN.
- Frontend typecheck: NOT RUN.
- Frontend build: NOT RUN.
- `git diff --check`: NOT RUN.
- Owned-range diff: NOT RUN.
- Decoder receipt: NOT RUN.
- Ports 18311, 19311, 17831: NOT RUN.

## Unexpected working-tree change

None. The working tree remained clean after the verification command stopped.
