# context — y3-session-reattach

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Known state (verified 2026-08-16, `dev` @ 5b20a95)

- `lib/persistence.ts` exports `loadSessionId`/`saveSessionId`/`clearSessionId` and
  `storageKeys.sessionId`. **No production caller.** Only `state/ui.ts` uses the module, for the two
  panel-collapse booleans. Confirmed by grep.
- `persistence.ts:23-29` `browserStorage()` returns `window.localStorage`; charter §6 says
  `sessionStorage`. Reconcile deliberately, record why.
- `live_auth.py:26` `VIEWABLE_SESSION_STATUSES = frozenset({"active", "closing"})`.
- Measured hole (`evidence/phase1/x3-capture-health/iteration-10-terminal-readable.json`):
  capture credential gets the terminal reason (`true`), view credential does not (`false`).
- `tests/test_live_portal.py:398-409` documents the current contract and anticipates this change.
- Five of G6's six paths already pass through the real route and over real TLS (x3 review-01/02).

## Candidates (ranked; re-rank as you learn)

1. Decide and document the storage ruling (localStorage vs sessionStorage) — it gates everything else.
2. Wire session-id persistence into the capture lifecycle; clear it on clean stop and on terminal.
3. Reattach on load: resume from the correct cursor, no duplicate or lost turns.
   Be explicit that browser media cannot survive a reload — the status line must say so.
4. Widen `VIEWABLE_SESSION_STATUSES` (or the read path) so a viewer gets the terminal reason and stops.
   Read T-01 first. Update `test_live_portal.py` deliberately; do not delete it.
5. Re-runnable probes for both, through the real authenticated routes.

## Not yours

`App.tsx`, `api/jobs.ts` (y1) · `TranscriptPane.tsx`, `lib/transcriptExport.ts` (y2)
