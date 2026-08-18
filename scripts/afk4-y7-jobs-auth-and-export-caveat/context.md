# context — y7-jobs-auth-and-export-caveat

Living working memory. Update every iteration. History goes in progress.txt.

## Known state (verified 2026-08-18, dev @ 852d366)

- `POST /api/jobs` at `server.py:198` has no auth dependency. `grep middleware server.py` → nothing.
  `grep "api/jobs" tests/*.py | grep -i auth` → nothing. The route is open.
- Existing auth seam lives in `moss_transcribe_diarize/app/live_auth.py` and already backs the live
  routes. Reuse it.
- `transcriptExport.ts:23,92` carry `provisional_stale` as a json field only; md and txt have no
  human-readable caveat.
- Frontend already holds the capture bearer in memory (never localStorage) — `ControlPanel`.
- Baseline to protect: pytest 2 failed / 1065 passed / 396 subtests; frontend 108/108.
  The 2 failures are permanent Phase 1 baselines — never "fix" them.

## Candidates (ranked; re-rank as you learn)

1. Read `live_auth.py` and how the live routes attach it. Reuse, do not reinvent.
2. RED test first: unauthenticated `POST /api/jobs` must be rejected. Watch it fail.
3. Guard all four job routes; keep `_admit_upload_request`, 408 idle timeout, chunked reads intact.
4. Send the in-memory bearer from the file-mode client; never a query param, never localStorage.
5. Human-readable provisional caveat in md and txt as well as json; absent after finalization.
6. Evidence against a locally-run service, not only unit tests.

## Not yours

`live_auth.py` (read-only, reuse its seam) · `frontend/src/components/` · `live_service_runtime.py`
