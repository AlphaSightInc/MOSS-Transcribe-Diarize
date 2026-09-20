# R4-7 supported runtime verdict

**SUPPORTED.** Candidate `89f833acd4c654dd702664a17ed19783a2999c95`
runs under disposable CPython 3.12.12 linked to the real SQLite 3.53.4 shared
library. `REQUIRED_SQLITE_RUNTIME` stayed unchanged and no `sqlite3` module was
replaced. Full backend and frontend populations match baseline.

## Question, primitives, and falsifier

- Question: can MOSS run under its declared runtime without test-time exception?
- Minimum primitives: interpreter/linkage, observed SQLite version, declared tape
  bytes, stopped DB+audio generation, and durable File outcome.
- Invariants: exact 3.53.4 pin; real `_sqlite3`; finite 200-minute-per-meeting
  tape; explicit storage failure; no shared host/service/GPU mutation.
- Unknown: this Mac receipt does not qualify the Linux host, speech quality, or
  a deployment. The Linux stage path remains a separate trusted-origin action.
- Falsifier carried forward: a staged process reports any SQLite other than
  3.53.4, a tape bound is not a whole wire-frame count, a cold restore mixes DB
  and audio generations, or ENOSPC reopens as `completed`/non-failure.

## Measured state

- Python 3.12.12; `_sqlite3` loads isolated
  `runtime-prefix/sqlite/lib/libsqlite3.dylib`; observed `3.53.4 3.53.4`.
- Backend: **2,116 passed, 0 failed, 5 skipped, 37 subtests passed** in 214.07 s.
- Frontend: **311/311** in 2.99 s; TypeScript clean; Vite clean in 116 ms.
- Tape: **384,000,000 B per meeting**, 24,000 × 16,000-byte wire frames;
  **768,000,000 B** for two meetings; finalizer, runtime, and app descriptor agree.
- Backup/restore: stopped store copied with complete audio root into fresh state;
  transcript/status and all three audio MD5 observations match one generation.
- Disk: APFS image raised real `ENOSPC` (`errno 28`) after 645,922,816 B;
  first and reopened Meeting are `failed/decode_failed`, never `completed`.
- Long tail: deterministic 201-minute File control passed 1/1 with 101 windows;
  tail ends at 12,060 s and survives app reopen.
- Decoder/GPU: **0 requests / 0 budget**. No tunnel or service.

## Failed attempts retained

1. `.[dev]` could not collect File tests because production imports `torch`;
   installed the declared runtime/acceptance extras in the disposable venv.
2. First full suite: 12 collection errors because Playwright is an acceptance
   dependency; installed declared `acceptance` extra.
3. Next full suite: 2,114 passed / 2 failed. Editable-install `.egg-info` in the
   clone plus mandated `PYTHONPATH=.` made nested pip skip the wheel under test.
   Relocating only that generated ignored metadata to the disposable prefix made
   both wheel controls pass 2/2; clean full rerun matched baseline.
4. Capacity probe first completed every gate but its report requested a nonexistent
   diagnostic key; report corrected to read the finalized manifest field.
5. First literal verification pass had 2,115 passed / 1 failed: root-level
   `VERIFY.md` violated the repository layout control. Moving it to
   `docs/verify/r4-7/` made the focused control and untouched full suite pass.

Fresh-context remainder: all verification commands passed in the restarted pane,
but a post-work `/new` session was unavailable. `VERIFY-RESULT.md` records this as
PASS-with-note; it does not claim independent context.

Full receipt and commands: `evidence/round4/runtime/RECEIPT.md`.
