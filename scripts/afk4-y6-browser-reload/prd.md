# PRD — y6-browser-reload

## Goal

**Close gate G6 by certifying its last path in a real browser.** Five of six paths are already
certified through the real authenticated routes and over a real TLS socket
(`evidence/phase1/x3-capture-health/review-01-five-scenario-route.json`, `review-02-live-uvicorn-wire.json`).
The sixth — *reload mid-capture reattaching from tab-scoped storage* — is implemented and covered by
unit tests, and **no browser has ever exercised it**.

A jsdom test that remounts a component is not a reload. It cannot observe tab-scoped storage
semantics across a real navigation, media tracks being torn down by the browser, or the event cursor
after a genuine page load. Those are exactly the failure modes this path exists to survive.

**This needs no model and no operator.** The G7 probe
(`prototypes/browser-capture-feasibility/probe_g7_hidden_tab.py`) is the pattern to follow: real
Chrome, real production HTTP routes, a deterministic provider, synthetic sources, no inference. G6's
bar is *"a correct server-authored status line and no crash"* — it never requires transcript text.

**Bar.** A committed, re-runnable probe that, against a locally-run service you start yourself:

1. Starts a capture session in real Chrome with a fake media device.
2. Reloads the page mid-capture.
3. Proves the session is reattached: the same `session_id` is resumed, the event/snapshot cursor
   continues without duplicated or lost transcript items, and the server never saw a Stop.
4. Proves the capture bearer did **not** survive the reload — only `{sessionId, viewToken}` may be
   in tab-scoped storage (ADR-0004 is the binding record).
5. Proves a reload **after** the session ended clears cleanly instead of reattaching to a corpse.
6. Records the server-authored status line at each step.

**Write assertions that can fail.** Two of G7's assertions were tautologies that survived review for
weeks: contiguity of a route-assigned sequence is guaranteed by the route, and
`accepted_samples == next_sequence * frame_samples` is an identity. Before committing, run each
assertion against a deliberately broken input — a reload that drops storage, a stale cursor — and
show it returns false. An assertion never observed failing is not a gate.

## Evidence

Commit raw artifacts under `evidence/phase1/y6-browser-reload/`, including the probe. State plainly
what the run does **not** cover — at minimum: no real permission prompt, no display capture, no
deployed host, no model inference.

## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py y6-browser-reload` before
every iteration. You own `prototypes/browser-capture-feasibility/`,
`evidence/phase1/y6-browser-reload/`, plus your own loop dir, `docs/`, `tests/`.
`frontend/src/` and `moss_transcribe_diarize/app/` are **read-only for you** — if the probe proves a
product defect, record it and escalate; do not fix it here.

Playwright lives in the **pyenv 3.12.12** environment, not `.venv`.

## Hard constraints

- The GPU host `ga0-alienware-rtx4070ti` is **READ-ONLY**. Start your own service, on a port you own.
- Never automate the display-capture picker — charter §1. That is G3 and it is the operator's.
- Push **your own branch only**, to remote `private`. Never `dev` or `main`. Never force-push.
- You may not close GitHub issues. Comment evidence; the orchestrator closes.
- Do not weaken a test to make a gate pass.
- Binding authority: `docs/phase1-afk-charter.md`, `docs/adr/0004-browser-session-reattach.md`,
  `docs/phase1-gate-status.md`, `AGENTS.md`.
