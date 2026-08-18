# context — y6-browser-reload

Living working memory. Update every iteration so it matches reality. History goes in progress.txt.

## Known state (verified 2026-08-18, dev @ 852d366)

- G6 has a first real-browser reload measurement; cursor continuity, terminal-reload cleanup, and
  assertion falsification remain before it can be certified.
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
- `probe_g6_browser_reload.py` now proves the real frontend bootstrap: a fresh headless Chrome
  profile mounts the shipped `ControlPanel` through local Vite and reaches the owned deterministic
  production descriptor through that `/api` proxy (`200`, `frame_samples=1000`); the page starts
  idle with no tab-scoped keys. Raw result:
  `evidence/phase1/y6-browser-reload/iteration-2-vite-bootstrap.json`. Vite receives `--base /`
  in the probe because its production `/static/` base is proxied to the backend; that keeps the
  source document/modules on Vite while leaving the production `/api` proxy intact.
- Use `.venv/bin/python` for this probe's production-route server. The standalone pyenv 3.12.12
  interpreter has an incompatible `transformers` install; this is unrelated to its Playwright
  availability and the probe uses the established dependency-free CDP client.
- Chrome launches fine post-reboot (`--headless --dump-dom` exits 0). Playwright is in pyenv 3.12.12.
- `probe_g6_browser_reload.py` now starts the actual `ControlPanel` in a fresh real Chrome profile
  from deterministic in-page fake MediaStreams, creates one live session, and performs a real
  navigation. Raw `iteration-3-live-reload.json` proves the same `session_id` reattached from the
  sole tab-scoped `{sessionId, viewToken}` record; the bearer was absent from storage and the input
  after reload; the reattached poller made read-only snapshot/events calls; no Stop reached the
  server; the session stayed active; and both pre/post server-authored status lines were readable.
  It explicitly does not cover a permission prompt, display capture, model inference, deployed host,
  cursor continuity, or terminal reload cleanup.
- A native Chrome fake-audio input was live but yielded 190 zero-RMS worklet frames in this
  environment; the probe uses the established synthetic MediaStream shape instead. This is a
  launcher/source limitation, not evidence of a product defect.
- Baseline to protect: pytest 2 failed / 1065 passed / 396 subtests; frontend 108/108.
  The 2 failures are permanent Phase 1 baselines — never "fix" them.

## Candidates (ranked; re-rank as you learn)

1. Cursor continuity across the reload — record pre/post rendered item identities and server event
   cursors, then prove neither duplication nor loss.
2. Negative case: reload after session end clears rather than reattaching.
3. Falsify every assertion against a deliberately broken input before committing.

## Not yours

`frontend/src/`, `moss_transcribe_diarize/app/` — read-only. Escalate defects, do not fix them.
