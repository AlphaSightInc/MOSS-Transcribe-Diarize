# R4-7 verification

Run from this clone with candidate parent
`89f833acd4c654dd702664a17ed19783a2999c95`.

```sh
test "$(git branch --show-current)" = round4/runtime
test "$(git rev-parse HEAD^)" = 89f833acd4c654dd702664a17ed19783a2999c95
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python -c \
  'from moss_transcribe_diarize.app import phase2; import sqlite3,_sqlite3; print(sqlite3.sqlite_version, phase2.REQUIRED_SQLITE_RUNTIME, _sqlite3.__file__); assert sqlite3.sqlite_version == phase2.REQUIRED_SQLITE_RUNTIME == "3.53.4"'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/runtime/capacity.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/runtime/backup_restore.py
bash prototypes/runtime/disk-exhaustion.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/phase2/test_owner_bound_file_meeting.py::test_201_minute_file_tail_is_saved_and_survives_app_reopen
MOSS_TEST_REAL_SQLITE=1 bash prototypes/runtime/backend-suite.sh
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: exact `3.53.4 3.53.4`; all three probes `SUPPORTED`; long-tail
1/1; backend 2,116/0/5/37; frontend 311/311; TypeScript/Vite clean; no mounted
image or owned process afterward. Any mismatch falsifies this receipt.
