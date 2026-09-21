# I1 implementation receipts

Runtime: CPython 3.12.12, SQLite 3.53.4. Decoder requests: 0. Network/tunnel: none.

## RED

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -m pytest -q -p no:cacheprovider --runxfail tests/phase2/test_p_f1f5_controls.py
```

Result: **4 failed**. Both URL retention arms stayed `active`; File pre-move staging survived; startup made 100 removal probes for seven retained directories.

## GREEN

- P1 controls after removing only their `xfail(strict=True)` markers: **4 passed**.
- All I1 controls, including added healthy controls: **9 passed**.
- Focused I1 plus retained-owner regressions: **48 passed**.
- 100,000 historical rows / seven retained directories: **seven probes**.
- Active, unknown, sibling, and outside owners survived; terminal owner was removed.
- Successful URL acceptance stayed active, registered, acquired, and Meeting-owned.

## Full gates

- Backend: **2,176 passed, 5 skipped, 2 xfailed, 37 subtests; 0 failed** in 198.34 s.
- Frontend: **312/312 passed**.
- TypeScript: clean.
- Vite: clean, 34 modules; no tracked asset change.
- Product diff from `0de56e1a`: only `moss_transcribe_diarize/app/phase2.py` and `moss_transcribe_diarize/app/phase2_file.py`.
