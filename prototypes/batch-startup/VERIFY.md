# R4-5 verification

Run from `/private/tmp/moss-round4-20260920/batch` with no network, tunnel, or GPU lease.

```sh
git rev-parse HEAD^
git branch --show-current
MOSS_R4_NO_WRITE=1 prototypes/batch-startup/run.sh all
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/phase2/test_batch_startup_prototype_controls.py
MOSS_R4_NO_WRITE=1 prototypes/batch-startup/run-real-smoke.sh
```

Expected:

- Parent `89f833acd4c654dd702664a17ed19783a2999c95`; branch `round4/batch`.
- Deterministic verdict `SUPPORTED`; 10/10 cases supported; C1 has 61 calls and
  101/101 unique segments; C10 interrupts Live and leaves zero active rows.
- Violating controls: `2 xfailed` on unpatched base. XPASS is a failure until run B
  removes the xfail and proves the production implementation.
- Real runner: `SUPPORTED`, completed, non-empty transcript, zero remote requests.

Falsify if any deterministic case is not supported; a violating control does not xfail;
the real smoke is not completed/non-empty; branch/SHA differs; or any network/GPU/remote
decoder request is used.
