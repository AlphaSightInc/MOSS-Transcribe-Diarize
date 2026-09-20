# R4-7 disposable runtime prototype

Question: can unmodified MOSS run with its exact SQLite 3.53.4 pin and preserve
the declared capacity, cold-copy, long-tail, and storage-failure contracts?

Each probe is one command from the repository root:

```sh
bash prototypes/runtime/build-runtime.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/runtime/capacity.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/runtime/backup_restore.py
bash prototypes/runtime/disk-exhaustion.sh
MOSS_TEST_REAL_SQLITE=1 bash prototypes/runtime/backend-suite.sh
```

All state is disposable. The probes make no decoder request, do not bind a
port, and do not modify the consumed provider manifest or any shared runtime.
