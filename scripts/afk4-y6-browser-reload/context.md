# context — y6-browser-reload

Living working memory. Update every iteration so it matches reality. History goes in progress.txt.

## Known state (verified 2026-08-18, dev @ 852d366)

- G6 is 5/6 certified. Only the reload path lacks a browser run.
- Reattach is implemented: `ControlPanel` stores `{sessionId, viewToken}` in tab-scoped storage,
  reload closes local media without sending Stop, startup resumes the snapshot/event poller, and the
  capture bearer stays in memory only. ADR-0004 records the security boundary.
- Terminal view authority permits snapshot/events and rejects stop/abort.
- `probe_g7_hidden_tab.py` is the working pattern: real Chrome via DevTools, real routes,
  deterministic provider, no inference. Its `--help` imports cleanly in pyenv 3.12.12.
- The G7 page is `capture_pipeline_page.html` at `/capture-harness`, not the shipped Preact
  `ControlPanel`; it cannot certify `sessionStorage` reattach or the real poller. Reuse only its
  local-server lifecycle and dependency-free CDP helpers. The shipped panel is served either by
  the built backend bundle or Vite, whose development `/api` proxy is fixed to `127.0.0.1:8090`.
- Chrome launches fine post-reboot (`--headless --dump-dom` exits 0). Playwright is in pyenv 3.12.12.
- Baseline to protect: pytest 2 failed / 1065 passed / 396 subtests; frontend 108/108.
  The 2 failures are permanent Phase 1 baselines — never "fix" them.

## Candidates (ranked; re-rank as you learn)

1. Add a probe bootstrap that serves the *actual* `ControlPanel` through a local Vite process and
   the deterministic production-route server at the proxy's owned port; retain G7's process/CDP
   cleanup discipline.
2. Minimum viable reload: start a deterministic session from the real Chrome context, reload the
   `ControlPanel`, then assert the same session id reattaches and the server received no Stop.
3. Cursor continuity across the reload — record pre/post rendered item identities and server event
   cursors, then prove neither duplication nor loss.
4. Negative case: capture bearer must NOT be present after reload; inspect only key names and
   redacted values in tab-scoped storage.
5. Negative case: reload after session end clears rather than reattaching.
6. Falsify every assertion against a deliberately broken input before committing.

## Not yours

`frontend/src/`, `moss_transcribe_diarize/app/` — read-only. Escalate defects, do not fix them.
