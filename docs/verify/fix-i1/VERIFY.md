# fix-i1 verification

Run from `/private/tmp/moss-round4-20260920/fix-i1` with no decoder, provider,
network, tunnel, GPU, or candidate write.

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1
PY=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
BASE=85aec978

git branch --show-current
git log --oneline -1
$PY -c 'import moss_transcribe_diarize as m, sqlite3; print(m.__file__); print(sqlite3.sqlite_version)'
$PY -m pytest -q -p no:cacheprovider tests/phase2/test_fix_i1_hardening.py
$PY -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
git diff --stat "$BASE" -- moss_transcribe_diarize
git diff -U0 "$BASE" -- moss_transcribe_diarize/app/phase2_file.py | grep '^@@'
git diff --name-only "$BASE" -- moss_transcribe_diarize
git grep -nE 'sk-or-v1-[A-Za-z0-9]{16,}|OPENROUTER_API_KEY=[A-Za-z0-9]'
git -C /Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate status --porcelain=v1 --untracked-files=all
cat /Users/gao/Documents/Codex/2026-09-20/moss-round4/status/GPU-LEASE.md
```

Expected: branch `round4/fix-i1`; import inside this clone; SQLite 3.53.4;
focused 8/8; backend 2,207 passed, 0 failed, 5 skipped, 2 xfailed, 37
subtests; frontend 312/312 plus typecheck/build; product diff only
`phase2_file.py`, with hunks only in `retained_work_owners`, `accept`, and
`accept_url`; empty secrets/candidate output; lease `FREE`.

Falsifier: any active ownerless Meeting after task creation/registration failure,
an unreadable retained entry aborting enumeration, sibling reclaim not proceeding,
success-path owner bytes changing, or any gate/count/scope mismatch.
