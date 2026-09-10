# Automatic qualification setup verdict

Question: can normal bootstrap replace manual login/cookie copying while retaining
independent owners and same-browser peers?

Measured with the real app, temporary SQLite 3.50.4 and HTTPS TestClient semantics:
three independent workspace/credential pairs; five successful peer authentication
round-trips; three mode-0600 credential files; exclusive-create refuses reuse.
No credential values printed. No direct database writes, audio or browser prompts.
TLS trust remains unmeasured here and is required by the deployed collector.

Verdict: absorb bootstrap and private-file logic into
`phase2_acceptance_setup.py`. Cutover owns the attempt directory and restore plan;
each evidence layer gets separate owners, and peer tabs share their owner's cookie.
Existing browser bench proves real Chrome coordination and foreign-history refusal.
