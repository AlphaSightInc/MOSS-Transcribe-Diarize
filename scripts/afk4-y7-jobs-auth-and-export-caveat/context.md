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
- Transcript exports now add the exact human-readable caveat, "Speaker attribution is provisional
  and may be revised by the retrospective sweep after the session ends," before Markdown and text
  content and as `provisional_attribution_notice` in JSON whenever any turn is `confirmed` or
  `provisional`. Fully `final` exports omit it. Focused Vitest evidence passes 4/4, and frontend
  typecheck passes.
- Frontend bearer propagation is blocked on scope, not an API-adapter gap. `App.tsx` conditionally
  unmounts `ControlPanel` when file mode is selected; `ControlPanel` owns `captureBearer` in local
  state, and `FilePanel` calls `submitJob(selectedFile)` with no options. Thus no memory-only bearer
  survives the mode switch. The smallest correct repair needs an authority grant for `App.tsx` plus
  both components to lift and pass that state; an API-side/global workaround would either have no
  source or invent an unsafe token store. Do not claim the frontend requirement complete without that
  grant and a component integration test.
- Baseline to protect: pytest 2 failed / 1065 passed / 396 subtests; frontend 108/108.
  The 2 failures are permanent Phase 1 baselines — never "fix" them.

## Candidates (ranked; re-rank as you learn)

1. Evidence against a locally-run service, not only unit tests.
2. Blocked: frontend bearer propagation requires authority to modify `frontend/src/App.tsx` and
   `frontend/src/components/{ControlPanel.tsx,FilePanel.tsx}`. On grant, lift the current in-memory
   bearer to `App`, pass it into both mode panels, add the Authorization header through `jobs.ts`,
   and prove no persistent/query token path.

## Not yours

`live_auth.py` (read-only, reuse its seam) · `frontend/src/App.tsx` · `frontend/src/components/` ·
`live_service_runtime.py`
