# context — y7-jobs-auth-and-export-caveat

Living working memory. Update every iteration. History goes in progress.txt.

## Known state (verified 2026-08-18, dev @ 852d366)

- `POST /api/jobs` at `server.py:198` has no auth dependency. `grep middleware server.py` → nothing.
  `grep "api/jobs" tests/*.py | grep -i auth` → nothing. The route is open.
- Existing auth seam lives in `moss_transcribe_diarize/app/live_auth.py` and already backs the live
  routes. `LiveAccessRegistry.authorize(peer, bearer, action, session_id, now)` rejects an absent
  bearer with 401 and accepts the configured shared bearer as capture authority; `"create"` is the
  applicable existing capture action for an unscoped write. `server.py` constructs and stores that
  registry only when `live_enabled=True`; `web_cli.py` currently accepts the shared-token file only
  with `--live`. Reuse the registry and its comparison/revocation path; do not edit `live_auth.py`.
- The focused live suite confirms both paths: a no-shared-token app completes pairing and a
  shared-token app admits its bearer (`2 passed, 2 subtests`). This is seam evidence only, not job
  route coverage.
- `tests/test_live_api.py::LiveApiTest::test_job_routes_require_configured_shared_bearer` is now a
  focused RED test against the real in-process HTTP route stack. Missing and wrong bearers both
  reached normal handlers as `[200, 400, 404, 404]` for list/create/get/delete; the configured
  bearer completed `[200, 200, 200, 200]`. The upload is backed by a deterministic test runner, so
  the admitted control exercises the real multipart, enqueue, get, and delete paths without model
  loading.
- `transcriptExport.ts:23,92` carry `provisional_stale` as a json field only; md and txt have no
  human-readable caveat.
- `ControlPanel` holds the capture bearer only in its own component state. `FilePanel` currently
  calls `submitJob` without options and no owned file can pass that in-memory bearer across the mode
  boundary. The PRD permits `frontend/src/api/jobs.ts` but marks `frontend/src/components/` not ours:
  resolve this authority/scope conflict before claiming the frontend requirement complete.
- Baseline to protect: pytest 2 failed / 1065 passed / 396 subtests; frontend 108/108.
  The 2 failures are permanent Phase 1 baselines — never "fix" them.

## Candidates (ranked; re-rank as you learn)

1. Guard all four job routes through the existing registry, preserving `_admit_upload_request`, the
   408 receive-idle timeout, and chunked reads.
2. Resolve the frontend bearer-propagation scope conflict, then send the memory-only bearer from
   file mode without a query parameter or persistent storage.
3. Human-readable provisional caveat in md and txt as well as json; absent after finalization.
4. Evidence against a locally-run service, not only unit tests.

## Not yours

`live_auth.py` (read-only, reuse its seam) · `frontend/src/components/` · `live_service_runtime.py`
