# PRD — y3-session-reattach

## Goal

**Close gate G6's two measured holes.** Five of its six failure paths already pass through the real
route and over a real TLS wire (`evidence/phase1/x3-capture-health/review-01-five-scenario-route.json`,
`review-02-live-uvicorn-wire.json`). Two do not.

### Hole 1 — reload mid-capture does not reattach

Charter §6 G6 requires: *"reload mid-capture reattaching from `sessionStorage`."*

The primitives exist and **nothing calls them.** `frontend/src/lib/persistence.ts` exports
`loadSessionId`, `saveSessionId`, `clearSessionId` and defines `storageKeys.sessionId`. The only
production consumer of that module is `frontend/src/state/ui.ts`, which reads the two panel-collapse
booleans. A library with no caller does not satisfy a failure path.

**Bar:** reloading the page mid-capture reattaches to the running session and resumes rendering its
transcript from the correct cursor — no duplicated turns, no lost turns, no orphaned server session.
A reload after the session ended must clear cleanly rather than reattach to a corpse. Decide and
document what happens to the *capture* (browser media cannot survive a reload — say so plainly in
the status line rather than pretending otherwise).

Note the storage-key ruling: `persistence.ts` currently returns `window.localStorage`. The charter
says `sessionStorage`. Reconcile deliberately and record why.

### Hole 2 — a viewer cannot learn why its session died

`moss_transcribe_diarize/app/live_auth.py:26`

```python
VIEWABLE_SESSION_STATUSES = frozenset({"active", "closing"})
```

Measured in `evidence/phase1/x3-capture-health/iteration-10-terminal-readable.json`:

```
snapshot_returns_server_authored_reason_to_capture_credential : true
snapshot_returns_server_authored_reason_to_view_credential    : false
```

The capture credential gets a readable reason; the view credential gets nothing and polls a corpse.

**Bar:** a view credential on a terminated session receives the server-authored terminal reason and
stops polling. T-01 accepted a **single trust domain**, so withholding the reason from a viewer buys
no isolation — but read T-01 before changing the status set, and do not widen what a view credential
can reach beyond its own session. `tests/test_live_portal.py:398-409` documents the current contract
and explicitly anticipates this change; update it deliberately rather than deleting it.

## Evidence

Commit raw artifacts under `evidence/phase1/y3-session-reattach/`: a re-runnable probe driving
reload-and-reattach against a locally-run service, and a probe showing a view credential reading a
terminal reason and stopping. Both must run against the real authenticated routes, not a unit call.

State plainly in your evidence what the runs do **not** cover — in particular whether a real browser
reload was exercised or only a simulated remount.

## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py y3-session-reattach` before
every iteration. You own `frontend/src/lib/persistence.ts`, `frontend/src/state/session.ts`,
`frontend/src/components/ControlPanel.tsx`, `moss_transcribe_diarize/app/live_auth.py`, plus your
own loop dir, `evidence/phase1/`, `docs/`, `tests/`. **`frontend/src/App.tsx` belongs to y1 and
`frontend/src/components/TranscriptPane.tsx` to y2** — read them, do not edit them.

## Hard constraints

- The GPU host `ga0-alienware-rtx4070ti` is **READ-ONLY**. Verify against a locally-run service you
  start yourself, on a port you own.
- Auth is a security seam. Do not weaken bearer comparison, revocation, or session ownership to make
  the viewer path work. If the change requires touching those, stop and escalate.
- Push **your own branch only**, to remote `private`. Never push `dev` or `main`. Never force-push.
- You may not close GitHub issues. Comment evidence; the orchestrator closes.
- Do not weaken a test to make a gate pass.
- Binding authority: `docs/phase1-afk-charter.md`, `.wayfinder/tickets/T-01-shared-token-trust-posture.md`,
  `docs/phase1-gate-status.md`, `AGENTS.md`.
