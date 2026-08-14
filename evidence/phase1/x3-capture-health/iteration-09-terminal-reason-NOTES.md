# Iteration 9 — terminal microphone-denial readback probe

Question: after a terminal helper heartbeat reports a microphone-permission denial, can either
session credential obtain the server-authored reason from the production `/snapshot` route?

Run:

```bash
PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/iteration-09-terminal-reason-probe.py \
  --write evidence/phase1/x3-capture-health/iteration-09-terminal-reason.json
```

The probe runs local `create_app`, pairs normally, creates a session, then posts a terminal
helper heartbeat with `browser_microphone_permission_denied`. It prints the heartbeat response,
the runtime's terminal record after teardown, and both post-terminal snapshot responses; no
credential is written to output.

Verdict: the server retains the typed reason, but does not make it client-readable after cleanup.
The runtime records `aborted` / `helper_failed` with the microphone failure code. The owning
capture credential then receives `403` with only `session is not owned by this device`; the
view credential receives `401` with only `invalid bearer authority`. The successful terminal
heartbeat returns raw helper presence, not the server's `capture_phase` or plain-language status.

Scope: deterministic local routes only. It does not exercise a browser permission prompt or a
production deployment. It is before-fix evidence, not acceptance evidence.
