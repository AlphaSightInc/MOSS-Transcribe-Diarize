# context — y6-browser-reload

Living working memory. Update every iteration so it matches reality. History goes in progress.txt.

## Known state (verified 2026-08-18, dev @ 852d366)

- G6 is 5/6 certified. Only the reload path lacks a browser run.
- Reattach is implemented: `ControlPanel` stores `{sessionId, viewToken}` in tab-scoped storage,
  reload closes local media without sending Stop, startup resumes the snapshot/event poller, and the
  capture bearer stays in memory only. ADR-0004 records the security boundary.
- Terminal view authority permits snapshot/events and rejects stop/abort.
- `probe_g7_hidden_tab.py` is the working pattern: real Chrome via DevTools, real routes,
  deterministic provider, no inference. It runs green on this host today.
- Chrome launches fine post-reboot (`--headless --dump-dom` exits 0). Playwright is in pyenv 3.12.12.
- Baseline to protect: pytest 2 failed / 1065 passed / 396 subtests; frontend 108/108.
  The 2 failures are permanent Phase 1 baselines — never "fix" them.

## Candidates (ranked; re-rank as you learn)

1. Read `probe_g7_hidden_tab.py` end to end. Reuse its server/Chrome/DevTools scaffolding rather
   than rebuilding it.
2. Minimum viable reload: start session, reload, assert same session_id resumed and no Stop seen.
3. Cursor continuity across the reload — no duplicated or lost items.
4. Negative case: capture bearer must NOT be present after reload.
5. Negative case: reload after session end clears rather than reattaching.
6. Falsify every assertion against a deliberately broken input before committing.

## Not yours

`frontend/src/`, `moss_transcribe_diarize/app/` — read-only. Escalate defects, do not fix them.
