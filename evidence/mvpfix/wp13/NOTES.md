# WP13 — preparation verdict and evidence

Base: `mvpfix/wp13-tls-hygiene` at `d8ee6f4109f277a22bfbca298da9ebdf85b218c8`.
All edited files and scratch state are in this worktree. Host/DNS read-only;
no issuance, installation, reload, restart, deployment, push, merge or GitHub writes.

## Structural result

See `ops/tls/NOTES.md`: offline model + real production reload sockets support
issuer/files/listeners/client-trust composition. Reconcile actual listeners, not
file-change alone, to recover partial activation. No extra fingerprints or policy
thresholds. Prototype model removed after absorption; socket regression reused.

Live read-only probes: 7861 self-signed, expires 2028-10-20 03:04:57 UTC (trust FAIL);
7862 trusted Let's Encrypt, expires 2026-12-09 21:32:04 UTC, 82.702532 days (PASS).
`live-7861.json` / `live-7862.json` retain full served chain metadata and exit status.
`host-readonly.json` / `host-ports-readonly.json` show actual service wiring:
7861 is moss-live-web.service without ExecReload; 7862 is moss-internal.service
with HUP and production lego files. moss-web.service is unrelated port 7860.
Lego 5.3.1 and private-file mode 0600 confirmed; credential contents not read.
Renewal unit/timer absent. Immediate host applicability is FALSIFIED until authorized
7861 cutover/qualified reload. Prepared script refuses before DNS on this host state.
I10-D05 activation authority and attended Chrome trust remain unresolved/unmeasured.

## Full-suite failures — justified file by file, not waived into PASS

Entire Python suite initially: **1808 passed, 19 failed, 2 skipped, 37 subtests passed**,
147.42 s. Full frontend: **239 passed / 239, 27 files / 27**, 2.44 s.
Focused final TLS + geometry + layout: **27 passed / 27**, 7.58 s.
Final full-suite rerun after live-unit correction: **1809 passed, 19 failed,
2 skipped, 37 subtests passed**, 150.86 s; identical base failure IDs.
Details recorded in `test-summary.json`.

A pristine archive of base d8ee6f41 was extracted under `.wp13runtime/base`, then the
same five files were run from that directory with `PYTHONPATH=.`. Import provenance
resolved to that archive. Qualified baseline: **128 passed, 19 failed, 9 subtests passed**,
8.50 s. The 19 failure node IDs exactly match the initial full run. Neither application
code nor these five test files differs from base. This is inherited integration debt;
WP13 does not rewrite decoder/identity/reader contracts to make unrelated tests pass.

| File | Failed | Observed failure reproduced at base |
|---|---:|---|
| `tests/phase2/test_draft_lane.py` | 1 | `multiple` canonical replacement expects 2 reader rows, receives 0. |
| `tests/phase2/test_runner_composition.py` | 1 | Zero PCM fixture expects 1 HTTP request, receives 0. |
| `tests/test_live_pipeline_seams.py` | 15 | Fixture paths return empty no-token results instead of reaching expected decoder outcome/token-cap/error assertions. |
| `tests/test_live_rolling_wiring.py` | 1 | Rolling fixture transcript empty instead of expected stock-market words. |
| `tests/test_live_service_replay.py` | 1 | Terminal replay reports `failed` where fixture expects `final`. |

The full-suite gate is **FAIL**, even though WP13-specific checks pass and all current
failures reproduce without WP13. This uses COMMON's file-by-file justification option;
it does not claim these failures are the explicitly tolerated voiceprint exception.
Final/fresh verification must expose any changed failure set, not silently whitelist it.

Reproduction commands (worktree-local TMPDIR and Python from COMMON):

```sh
python -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
python -m pytest -q -p no:cacheprovider tests/phase2/test_tls_preparation.py tests/phase2/test_tls_renewal.py tests/phase2/test_lane_consumer_geometry.py
# From the pristine .wp13runtime/base directory:
python -m pytest -q -p no:cacheprovider tests/phase2/test_draft_lane.py tests/phase2/test_runner_composition.py tests/test_live_pipeline_seams.py tests/test_live_rolling_wiring.py tests/test_live_service_replay.py
```

## Failed setup attempts retained

- Initial skill path `/Users/gao/.codex/skills/openai-docs/SKILL.md` absent; corrected
  to the available `.system/openai-docs/SKILL.md`. No workspace effect.
- First baseline invocation raced archive extraction: exit 4, no tests; discarded
  as evidence of product behavior. Corrected by awaiting extraction completion.
- Next baseline lacked frontend dependency symlink: **123 passed, 24 failed**, 6.15 s;
  5 additional draft-reader failures were Node module setup errors. Added the same
  read-only dependency symlink as the working tree, reran: **128 passed, 19 failed**.
- Initial script target assumed repository template moss-web.service was 7861.
  Read-only actual process/unit inventory disproved it before any host mutation;
  corrected to moss-live-web.service, added a refusal regression and runbook blocker.

Raw local outputs live under ignored `.wp13runtime/raw/`; exact node IDs, commands,
counts, timings and concise failure excerpts are retained in `test-summary.json`.
Hygiene inventory records relocation of the 3.40 MB WP3 per-chunk raw log and
retention of its small aggregate summary; the named WP1 log is under 1 MB.
No frontend source/assets, application policies, frame protocol or lifecycle altered.
