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

Verdict: the server retains the typed reason. Whether a client can read it turns on exactly one
thing — whether the terminal cleanup released the access binding.

The runtime records `aborted` / `helper_failed` with the microphone failure code. On the current
tree the owning capture credential reads `capture_phase: failed` plus the microphone-denial line,
and no credential appears anywhere in the body. The probe then performs `release_session` itself —
the exact call the pre-branch `live_helper_failure._release_registries` and the stop/abort routes
made — and re-issues the same request: `403`, `session is not owned by this device`, no
`capture_phase`, no `status_line`, no failure code. The view credential receives `401` with only
`invalid bearer authority` either way, because view authority dies through the runtime lifecycle
resolver rather than through the binding. The successful terminal heartbeat returns raw helper
presence, not the server's `capture_phase` or plain-language status.

Rewritten during adversarial review (2026-08-14). The original probe asserted the `403` the
pre-fix tree returned, so once iteration 10 landed it crashed on `AssertionError` and could no
longer regenerate the artifact it is cited for. Re-running before-state evidence has to stay
possible, so the probe now reproduces the pre-branch mechanism itself and records both outcomes
side by side; the causal claim is stronger than the original snapshot of one status code.

Scope: deterministic local routes only. It does not exercise a browser permission prompt or a
production deployment.
