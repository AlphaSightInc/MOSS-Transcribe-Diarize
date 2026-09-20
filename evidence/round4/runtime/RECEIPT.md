# R4-7 supported runtime receipt

Verdict: **SUPPORTED** on candidate `89f833acd4c654dd702664a17ed19783a2999c95`.
This is a disposable macOS runtime receipt, not deployment or acoustic evidence.

## Runtime identity and linkage

- Interpreter: CPython `3.12.12`, Clang `21.0.0`, arm64 macOS 26.6.1.
- Executable: `/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python`.
- SQLite CLI/library: `3.53.4`, source `sqlite-autoconf-3530400`.
- Python observation: `sqlite3.sqlite_version == 3.53.4`.
- Product pin: `phase2.REQUIRED_SQLITE_RUNTIME == 3.53.4`.
- Extension: `runtime-prefix/python/lib/python3.12/lib-dynload/_sqlite3.cpython-312-darwin.so`.
- `otool -L`: `_sqlite3` loads
  `runtime-prefix/sqlite/lib/libsqlite3.dylib` (current version 9.6.0), plus
  `/usr/lib/libSystem.B.dylib`; no host SQLite path.
- Source SHA-256: SQLite archive
  `0e9483900e92cd5de8fd48d16bf9200145a61f7fd5be542a5ac81d8a9516eb9c`
  (3,283,177 B); CPython archive
  `487c908ddf4097a1b9ba859f25fe46d22ccaabfb335880faac305ac62bffb79b`
  (27,255,645 B).
- Relevant packages: aiosqlite 0.22.1; pytest 9.1.1; torch 2.14.0;
  torchaudio 2.11.0; onnxruntime 1.23.2; Playwright 1.63.0; uv 0.9.13.

No bypass: `moss_transcribe_diarize/app/phase2.py:23` was not edited; exact
enforcement at `:183-187` ran. `tests/conftest.py` has one explicit
`MOSS_TEST_REAL_SQLITE=1` branch that asserts real runtime equality and returns
without monkeypatching. No `sys.modules` replacement exists in this work.

## Commands and counts

```sh
bash prototypes/runtime/build-runtime.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv>/bin/python -c \
  'from moss_transcribe_diarize.app import phase2; import sqlite3; print(sqlite3.sqlite_version, phase2.REQUIRED_SQLITE_RUNTIME)'
# 3.53.4 3.53.4

MOSS_TEST_REAL_SQLITE=1 bash prototypes/runtime/backend-suite.sh
# 2116 passed, 5 skipped, 19 warnings, 37 subtests passed in 214.07s

npm --prefix frontend test -- --run
# 28 files, 311/311 tests passed in 2.99s
npm --prefix frontend run typecheck
# clean
npm --prefix frontend run build
# 34 modules; clean in 116ms
```

Frontend commands were completed before the lead's model-switch interruption and
repeated successfully during this restarted session's literal verification pass.

## Product-seam controls

### Tape capacity

`capacity.py` finalized the consumed manifest through
`live_manifest_finalizer.py:273-307`, constructed the production provider bundle,
started the Account app, and read `/api/live/descriptor`.

- Source manifest size: 3,351 B; candidate manifest size: 3,459 B.
- Frame: 8,000 PCM16 samples = 16,000 B.
- Rolling ring: 1,920,000 B.
- 200 minutes: `200 × 60 × 16,000 × 2 = 384,000,000 B` per meeting.
- Whole frames: 24,000; two-meeting finite allocation: 768,000,000 B.
- Finalized manifest, runtime descriptor, and app descriptor: all 384,000,000 B.
- Decoder requests: 0.

### Stopped backup/restore

`backup_restore.py` closed the owning SQLite store, copied the database plus any
present WAL/SHM sidecars and the complete Meeting-audio root, restored to a fresh
state directory, started the Account app, reopened the Meeting, and downloaded its
audio. Source, restored file, and downloaded audio MD5 are all
`b7d78ab885378363cc61181f731dc192`; status/transcript remain generation A.

### Disk exhaustion

`disk-exhaustion.sh` mounted a disposable 640 MiB APFS sparse bundle. The accepted
File job hit real `ENOSPC` (`errno 28`) after 645,922,816 B. The harness removed its
pressure file after the observed write failure so SQLite could record product truth.
The first and reopened Meeting are both `failed`, code `decode_failed`, reason
present, transcript absent; neither is `completed`. The image was detached.

### Beyond 200 minutes

```sh
MOSS_TEST_REAL_SQLITE=1 <venv>/bin/python -m pytest -q -p no:cacheprovider \
  tests/phase2/test_owner_bound_file_meeting.py::test_201_minute_file_tail_is_saved_and_survives_app_reopen
# 1 passed in 31.15s
```

The deterministic production File seam completed 101 windows for 12,060 seconds;
the final segment ends at 12,060 and survives app reopen. This is lifecycle/tail
evidence only, never acoustic evidence.

## Failed attempts retained

- The first project install omitted speaker and acceptance extras; collection
  exposed missing Torch, then Playwright. Installing the declared extras fixed
  collection without changing product code.
- The next suite ran 2,114 pass / 2 fail because generated editable-install
  metadata made nested wheel tests skip the wheel under test. Moving only that
  ignored metadata to the disposable prefix made both controls pass.
- The first literal verification run produced 2,115 pass / 1 fail because its
  draft `VERIFY.md` was at repository root. Repository policy requires
  `docs/verify/<wp>/`; after relocation the focused layout control and full
  2,116-test backend population passed unchanged.

## Future deploy and rollback artifact list — not performed

1. **Versions:** official SQLite 3.53.4 source and published SHA3-256; system
   `/usr/bin/python3.12`; aiosqlite 0.22.1; candidate wheel; `uv.lock` frozen
   acceptance export; Node runtime already named by staging.
2. **Files:** `ops/build-account-sqlite.sh:8-82`; immutable release produced by
   `ops/stage-account-candidate.sh:100-188`; trusted provider manifest with
   `max_tape_bytes=384000000`; candidate manifest; Account profile; web/admin/
   cutover/vLLM launchers and systemd unit bytes already bound by staging.
3. **Commands:** run candidate-owned `ops/build-account-sqlite.sh`; build a clean
   wheel from the frozen SHA; set `MOSS_CANDIDATE_WHEEL`; run candidate-owned
   `ops/stage-account-candidate.sh`. Do not activate, restart, or cut over here.
4. **Verification:** isolated `sqlite3.sqlite_version == 3.53.4`; `_sqlite3`
   resolves to scoped prefix; installed candidate/RECORD/dependency projections
   match; manifest admits 384,000,000 B; full suites match denominators; stopped
   backup is restorable; live vLLM PID/argv/start stay unchanged.
5. **Rollback:** before admission, leave prior `account-current` untouched or
   repoint to the prior manifested immutable release; restore the complete stopped
   DB+audio bundle as one generation only when rollback policy calls for data
   rollback. Never mix a newer DB with older audio or loosen the SQLite pin.

## Exact later-change seams and falsifier

No MOSS product-code repair is needed. A trusted-origin rollout would change only
the consumed provider manifest capacity, then exercise existing staging seams:
`ops/stage-account-provider-manifest.py:35-61`,
`ops/stage-account-candidate.sh:111-197`, and
`ops/account-web-launcher.sh:7-28`. Runtime enforcement/consumption remains
`phase2.py:23,183-187,1900-1920`,
`live_manifest_finalizer.py:273-307`, and
`live_service_runtime.py:675-688`.

Implementation/deployment falsifier: any staged process does not report exact
3.53.4 from the real module, any descriptor differs from 384,000,000 B per tape,
two 200-minute tapes exceed admitted host storage, a stopped restore mixes DB/audio
generations, an ENOSPC File outcome reopens completed/non-failed, or the 201-minute
tail disappears. Stop; do not edit the pin or shim SQLite.
