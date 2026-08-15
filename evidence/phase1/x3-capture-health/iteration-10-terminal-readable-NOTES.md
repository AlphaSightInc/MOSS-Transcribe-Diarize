# Iteration 10 — terminal reason remains readable

Question: after terminal helper teardown, does the capture owner still receive one
server-authored microphone-permission status through the real `/snapshot` route, without a
credential in that response?

Run:

```bash
PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/iteration-10-terminal-readable-probe.py \
  --write evidence/phase1/x3-capture-health/iteration-10-terminal-readable.json
```

Verdict: PASS. The local paired capture credential received HTTP 200 with `capture_phase:
failed` and the server-owned microphone-access instruction after helper teardown. The view
credential received HTTP 401. The returned capture snapshot contained neither `view_token` nor
`device_token` fields. This is a deterministic local route proof, not a browser permission-prompt
or deployment test.
