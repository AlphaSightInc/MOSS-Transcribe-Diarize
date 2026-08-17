# context — y1-file-mode

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Known state (verified 2026-08-16, `dev` @ 5b20a95)

- `frontend/src/App.tsx:68-96` — file picker sets a filename string, does nothing else.
- `grep -rn "api/jobs" frontend/src/` → **no hits**. Nothing in the new UI talks to the jobs pipeline.
- `/api/jobs` exists server-side and `/studio` already drives it. This is reintegration, not new backend work.
- `frontend/src/api/mossPoller.ts` already maps MOSS cursors onto the reference event model (T-02).
- Baseline: pytest `2 failed, 1063 passed, 2 skipped, 394 subtests`. Frontend typecheck clean, vitest 99/99.
  The 2 failures are permanent Phase 1 baselines (l15 pin, l2-stage0 untracked corpus) — never "fix" them.

## Candidates (ranked; re-rank as you learn)

1. Read `moss_transcribe_diarize/app/jobs.py` and the Studio page. Write down the actual job
   lifecycle — submit, poll, result shape — before touching the frontend.
2. Build `frontend/src/api/jobs.ts` as a thin adapter. Unit-test it against recorded route shapes.
3. Wire the file section to it; render results through the existing TranscriptPane seam.
4. Mode-switch state isolation (Live ↔ File) and its test.
5. Failure paths: unsupported type, server-side job failure, file cleared after selection.
6. End-to-end evidence against a locally-run service with a real audio file.

## Open questions

- Does `/api/jobs` return diarized turns in a shape the reference event model already covers, or is
  a translation needed? Answer from the code, record here.

## Not yours

`TranscriptPane.tsx` (y2) · `state/session.ts`, `persistence.ts`, `ControlPanel.tsx`, `live_auth.py` (y3)
