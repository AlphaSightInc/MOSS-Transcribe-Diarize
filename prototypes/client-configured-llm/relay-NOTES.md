# Same-origin relay — measured design and integration

## Contract, before implementation

- **Q1:** Can HTTPS browser summaries use configured plain-HTTP tailnet models without
  mixed-content requests or transferring browser credentials to those models?
- **P1:** Smallest primitives: config-listed model→upstream mapping; authenticated request;
  nonempty completion; one browser-owned attempt. URL selection belongs to operator config,
  while fallback and summary lifecycle stay in the browser. Removing any boundary permits
  arbitrary routing, blank summaries, credential forwarding, or duplicate attempts.
- **I1:** External HTTPS payload/retry behavior remains unchanged; no transcript content in
  error/journal evidence; no URL from browser input; no redirects; fallback cannot restart
  an already generating attempt; only validated summaries are persisted.
- **U1:** Real model quality/availability and deployment remain unmeasured by this task.
  The brief reports upstream availability; no host or live model calls were made here.
- **X1:** A disallowed URL accepted, reasoning-only content treated as a summary, more than
  two relay calls, invalid lifecycle transition, leaked cookie, or broken external CORS
  path falsifies the proposed implementation.
- **T1:** An initial in-memory `httpx.MockTransport` prototype tested routing/content
  classification before product code. Production-route tests then bind that logic to
  real workspace authentication, while browser probes exercise built assets and storage.

## Measured results and absorbed prototype

The initial Python prototype accepted localhost, tailnet IP and tailnet DNS examples;
rejected external and localhost-suffix impostor hosts (five cases). Reasoning-only primary
output produced `empty_content`; fallback output was accepted. Both calls carried
`stream:false`, and a 9000-token request became 4096. The temporary prototype was absorbed
into `tests/phase2/test_llm_relay.py`; no standalone alternate relay implementation remains.

Server route tests use an in-process fake upstream and prove model routing, absent
credentials, config-only discovery, 401 without session, same-origin write enforcement,
startup URL rejection, default/clamped tokens, content-preserving success, content-free
failure, and refusal to follow redirects. Invalid requests never return their input.

The first real-browser relay probe failed to finish after primary failure: the browser
worker attempted `generating→generating`, which the real summary store rejects. Fixed by
remaining in the same generating attempt for fallback. The frontend harness now models
the actual store transition set, and the browser probe exercises the real store. A later
probe exposed an ambiguous accessible dropdown name from implicit label text plus options.
The selects now declare explicit accessible labels; the probe waits for that named dropdown
before inspecting it.

The relay probe uses real headless Chrome, served built assets, workspace cookie and
SQLite summary persistence; only the upstream transport is fake. It checks default relay
selection, config-only discovery, dropdown/no-key UI, exactly one fallback, model status,
no forwarded cookie and durable validated result. The existing external HTTPS CORS probe
checks eight browser/privacy/persistence invariants without changing its original assertions.

Reproduce:

```sh
PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/relay_browser_probe.py
PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/final_browser_probe.py
```

Only content-free counts/booleans are printed. Synthetic speech text and fake provider
content stay in temporary memory/SQLite, deleted by the probe. The external probe's
self-signed local test certificate is not production TLS qualification. Both probes
are muted; neither captures audio or invokes a live model.

Unscoped root `pytest` also discovers archived diarization prototypes with a historical
source-commit pin and absent archived corpus. Those three legacy failures are unrelated
to this relay and were left intact. The complete product suite is `pytest tests`, followed
by frontend, typecheck/build, and both browser probes. G9 predicate contract tests run in
that product suite; deployed G9 load/TLS qualification is outside this task.
