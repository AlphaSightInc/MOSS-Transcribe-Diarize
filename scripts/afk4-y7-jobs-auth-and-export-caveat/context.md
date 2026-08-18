# context — y7-jobs-auth-and-export-caveat

Living working memory. Update every iteration. History goes in progress.txt.

## Known state (verified 2026-08-18, dev @ 852d366)

- Existing auth seam lives in `moss_transcribe_diarize/app/live_auth.py` and already backs the live
  routes. `LiveAccessRegistry.authorize(peer, bearer, action, session_id, now)` rejects an absent
  bearer with 401 and accepts the configured shared bearer as capture authority; `"create"` is the
  applicable existing capture action for an unscoped write. `server.py` constructs and stores that
  registry only when `live_enabled=True`; `web_cli.py` accepts the shared-token file only with
  `--live`. The default non-live CLI bind is loopback (`127.0.0.1`). Reuse the registry and its
  comparison/revocation path; do not edit `live_auth.py`.
- All four named job routes now call `_authorize_job_request` before handler work when a live access
  registry is configured. It builds the same peer/bearer inputs as live routes and calls
  `authorize(..., "create", None, ...)`; missing and wrong bearers return `[401, 401, 401, 401]`,
  while the configured bearer completes `[200, 200, 200, 200]` for create/list/get/delete. Auth is
  before `_admit_upload_request`, so rejected uploads do not read a body or reserve disk. The
  deterministic runner keeps the admitted control on real multipart/enqueue/get/delete paths.
- Focused validation: the job-route test passes; `tests/test_large_upload.py` remains `11 passed,
  2 skipped`; and the no-shared-token pairing/live path passes. This is in-process route evidence;
  the required locally-run service artifact remains open.
- `transcriptExport.ts:23,92` carry `provisional_stale` as a json field only; md and txt have no
  human-readable caveat.
- `ControlPanel` holds the capture bearer only in its own component state. `FilePanel` currently
  calls `submitJob` without options and no owned file can pass that in-memory bearer across the mode
  boundary. The PRD permits `frontend/src/api/jobs.ts` but marks `frontend/src/components/` not ours:
  resolve this authority/scope conflict before claiming the frontend requirement complete.
- Baseline to protect: pytest 2 failed / 1065 passed / 396 subtests; frontend 108/108.
  The 2 failures are permanent Phase 1 baselines — never "fix" them.

## Candidates (ranked; re-rank as you learn)

1. Resolve the frontend bearer-propagation scope conflict, then send the memory-only bearer from
   file mode without a query parameter or persistent storage.
2. Human-readable provisional caveat in md and txt as well as json; absent after finalization.
3. Evidence against a locally-run service, not only unit tests.

## Not yours

`live_auth.py` (read-only, reuse its seam) · `frontend/src/components/` · `live_service_runtime.py`
