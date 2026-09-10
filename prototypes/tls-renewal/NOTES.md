# Certificate rotation verdict — 2026-09-10

Question: can renewed TLS credentials become active without restarting or disturbing
recordings? Minimum primitives: a prepared SSL context, one context reference for new
handshakes, host-local SIGHUP. Invalid replacement must retain the working context;
established connections and process identity must survive.

Measured first on a throwaway Uvicorn server with two locally trusted test certificates:
serial 01 before rotation, 02 after, still 02 after a mismatched replacement key. An
HTTP request held across both signals completed. Same PID 84613, same listening socket.
Initial experiment exposed a fixture trust ambiguity (two self-signed certificates
with the same issuer name); distinct issuer names fixed the fixture without disabling
verification. Production trusted-DNS issuance is not established by this experiment.

Accepted: prepare replacement off the live context, then atomically select it in new
TLS handshakes. No process restart, timer in the application, database state, browser
control, or recording interruption. Absorbed into `app/tls_reload.py` and regression
`tests/phase2/test_tls_renewal.py`; throwaway implementation removed.

Run: `.venv/bin/python -m pytest -q tests/phase2/test_tls_renewal.py`.
