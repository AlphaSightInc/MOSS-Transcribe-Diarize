# Fresh verification — I1 File ownership and cleanup

Run from a fresh clone of `round4/impl-i1`. Use no network and no decoder.

```sh
npm ci --prefix frontend --offline
PY=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.

"$PY" -c 'import sqlite3, moss_transcribe_diarize as m; print(sqlite3.sqlite_version); print(m.__file__)'
git diff --check 0de56e1a
git diff --name-only 0de56e1a -- moss_transcribe_diarize
! rg -n 'xfail' tests/phase2/test_p_f1f5_controls.py

"$PY" -m pytest -q -p no:cacheprovider tests/phase2/test_p_f1f5_controls.py
"$PY" -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build

git diff --exit-code HEAD -- frontend moss_transcribe_diarize/app/frontend_assets
git status --short
```

Expected:

- SQLite is `3.53.4`; import resolves inside the fresh clone.
- Product names are exactly `phase2.py` and `phase2_file.py`; diff-check is clean.
- I1 controls: 9 passed and no xfail marker.
- Backend: at least 2,176 passed, zero failed, 5 skipped, exactly 2 xfailed, 37 subtests.
- Frontend: 312/312; typecheck and build pass; build changes no tracked asset.
- Only ignored `frontend/node_modules` may exist after bootstrap; `git status --short` is empty.

Falsify I1 if any P1 control fails; any created Meeting remains active/taskless; staging or owner work leaks; active/unknown/sibling work is removed; reclaim probes history instead of seven retained owners; a protected constant changes; or any full gate fails.
