# WP13 offline renewal experiment — 2026-09-18

Question: smallest renewal mechanism for both 7861 and 7862, without production mutation?
Primitives: DNS-01 issuer, certificate/key files, each listener's loaded certificate,
independent client trust. Removing any loses issuance, activation, or proof.
Invariants: dry-run has zero effects; no restarts; retry converges both listeners;
invalid replacement cannot replace the working TLS context. Host activation is unauthorized.
Unknown: live unit wiring, private credentials, installed timer, Chrome trust.

Hypothesis: reuse lego v5's due-renewal decision; compare the desired leaf with each
listener, reload only mismatches, then verify trust/expiry and exact leaf. Comparing
only old/new files misses retries after partial reload. No new renewal threshold:
lego owns scheduling; 21 days is the WP13 client alarm requirement.

Prototype run: `python3 ops/tls/PROTOTYPE.py` (throwaway, removed after absorption).
Seven printed states: dry-run preserved state; renewing files left 2 stale ports;
web-only reload left 1; reconciliation left 0; repeat left 0. Model evidence is
`evidence/mvpfix/wp13/prototype-state.jsonl`, not deployed proof.
Production-path measurement: with worktree TMPDIR and PYTHONPATH, run
`python tests/phase2/_tls_reload_probe.py`. Serial 01 → 02 → 02 after invalid pair;
held request survived; same listener, PID 23829. Captured JSON/stderr beside model output.

Verdict: locally supported. Reuse existing SIGHUP implementation; add a two-port
renewal operator command and independent verifier. Do not activate I10-D05 by inference.
Model comparison absorbed into `renew.py`; existing socket regression retained.
Public issuance, host installation, timer enablement and attended trust remain UNEXECUTED.

Live inventory refinement: the assumed web-unit/7861 mapping was false. Actual
7861 owner is moss-live-web.service (no ExecReload); moss-web.service serves 7860.
7862 is moss-internal.service with HUP reload and production lego paths. Renewal
service/timer are absent. Use the actual pair; refuse before issuer if either lacks
qualified reload. This falsifies immediate host applicability, not the local
two-listener primitive. 7861 needs an owner-approved runtime/certificate cutover.
