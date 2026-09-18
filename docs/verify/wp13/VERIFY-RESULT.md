# WP13 — fresh-context verification result

**WP13 local preparation checks PASS; full Python suite FAIL; live :7861 trust FAIL.**
No issuance, installation, host reload/restart, timer activation, deployment, push,
merge, or attended proof. Executed `docs/verify/wp13/VERIFY.md` in this fresh session.

## F1 — Provenance and exact gates

- Branch: `mvpfix/wp13-tls-hygiene`.
- Tested SHA: `38b35eeac099f70470d5ac6378125eec3fb91394`; starting tree clean.
- Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp13-tls-hygiene`.
- Python: instructed `-wt-auto-mvp-0911/.venv/bin/python`; `PYTHONPATH=.` and
  `PYTHONDONTWRITEBYTECODE=1`; import resolved to this worktree's
  `moss_transcribe_diarize/__init__.py`. Temporary files stayed under `.wp13runtime/`.
- Existing `frontend/node_modules` points to the shared dev dependency directory;
  no dependency installation. Vite cache is checkout-local.
- Fresh TLS observations: 2026-09-18 04:59:41 UTC.

| Gate / literal command (Python = interpreter above) | Result | Exit | Time |
|---|---|---:|---:|
| `python -m pytest -q -p no:cacheprovider tests/phase2/test_tls_preparation.py tests/phase2/test_tls_renewal.py tests/phase2/test_lane_consumer_geometry.py` | PASS: 27 passed, no warnings | 0 | 7.50 s |
| `python -m pytest -q -p no:cacheprovider tests` | **FAIL: 1809 passed, 19 failed, 2 skipped, 37 subtests passed, 21 warnings** | 1 | 147.32 s |
| `npm --prefix frontend test -- --run` | PASS: 239 tests, 27 files | 0 | 2.48 s |
| `python ops/tls/renew.py --dry-run` | PASS: effects 0; prerequisites not checked | 0 | Not separately timed |
| `python ops/tls/verify.py ga0-alienware-rtx4070ti.tailnet.aisight.us 7861` | **FAIL: self-signed certificate** | 1 | Not separately timed |
| Same verifier, port `7862` | PASS: ordinary trust/hostname, same verified leaf, all served certificates >=21 days | 0 | Not separately timed |
| `bash scripts/check_verify_layout.sh` | PASS: no root verification files | 0 | Not separately timed |
| `git diff --exit-code -- evidence/mvpfix/wp2` | PASS: no evidence rewrite | 0 | Not separately timed |
| `git check-ignore evidence/mvpfix/wp3/raw/chunks.json` | PASS: regenerated raw log ignored | 0 | Not separately timed |
| `python prototypes/streaming-diarization/capture-guards/chunks.py` and literal base-row comparison | PASS: 17640/17640 numeric rows equal, zero decoder calls | 0 | Not separately timed |
| `git diff --check` | PASS | 0 | Not separately timed |

Full-suite failed node set equals `test-summary.json` -> `base-qualified.txt` ->
`failed_nodes`: **19 identical; 0 new; 0 missing**. Those failures were reproduced
at pristine base `d8ee6f4109f277a22bfbca298da9ebdf85b218c8` in retained preparation
evidence; this session compared that evidence, without rerunning the base archive.
They are not the permitted voiceprint exception and are not waived into PASS.

| Failed file | Count | Retained base failure explanation |
|---|---:|---|
| `tests/phase2/test_draft_lane.py` | 1 | `multiple` replacement expects 2 reader rows, receives 0 |
| `tests/phase2/test_runner_composition.py` | 1 | Zero PCM fixture expects 1 HTTP request, receives 0 |
| `tests/test_live_pipeline_seams.py` | 15 | Empty/no-token path misses expected decoder outcome/cap/error assertions |
| `tests/test_live_rolling_wiring.py` | 1 | Expected stock-market transcript absent |
| `tests/test_live_service_replay.py` | 1 | Terminal replay reports `failed`, expects `final` |

Warnings inspected: Python Starlette/httpx deprecation (1), tarfile extraction
default change (17), audioread `aifc`/`audioop`/`sunau` deprecations (3).
Frontend emitted three Node `--localstorage-file` invalid-path warnings and an npm
update notice; no update performed. Exact failed IDs, counts, timings, and exit
codes: `evidence/mvpfix/wp13/fresh/summary.json`. Raw logs remain ignored in
`.wp13runtime/raw/fresh-{focused,python,frontend}.txt`.

## F2 — Observed TLS chain and renewal boundary

Content-safe certificate metadata only; no HTTP content or credential values.
Both leaves name `ga0-alienware-rtx4070ti.tailnet.aisight.us`.

| Port | Served subject -> issuer | Expiry UTC |
|---|---|---|
| 7861 | Hostname -> same hostname (self-signed) | 2028-10-20 03:04:57 |
| 7862 | Hostname -> Let's Encrypt YE2 | 2026-12-09 21:32:04 |
| 7862 | Let's Encrypt YE2 -> ISRG Root YE | 2028-09-02 23:59:59 |
| 7862 | ISRG Root YE -> ISRG Root X2 | 2032-09-02 23:59:59 |
| 7862 | ISRG Root X2 -> ISRG Root X1 | 2032-09-02 23:59:59 |

7861: 1 served certificate, 762.920316 leaf days remaining, expiry check true,
trust false, overall false, exit 1. Long expiry does not repair missing trust.
7862: 4 served certificates, 82.689146 leaf days remaining, trust/hostname and
expiry checks true, identical verified/diagnostic leaf, overall true, exit 0.
Served root-cross-sign metadata is not a claim that the root itself was served.
Fresh chains match the previously recorded subject/issuer/serial/expiry values.
Raw certificate metadata and observation timestamps are in `fresh/live-7861.json`
and `fresh/live-7862.json`.

**Prototype question/verdict:** can issuer, certificate files, listeners, and client
trust compose a two-listener renewal that recovers partial activation? Locally
supported. Fresh focused tests exercised real socket rotation `01 -> 02`, retained
`02` after an invalid pair, and preserved an in-flight request. Mocked renewal
converged a stale 7862 after partial activation without redundant reload on repeat.
The original seven-state model is retained in `prototype-state.jsonl`; it was
absorbed into the command, not rerun as a separate throwaway prototype here.

Prepared mechanism: lego v5 DNS-01 through Netlify, lego's own due-renewal decision,
existing operation lock, valid certificate/key pair, exact desired-leaf comparison
per listener, SIGHUP only for mismatches, then independent trust/hostname/expiry
verification. No restart or new scheduling policy. Default/explicit dry-run is
offline with zero effects; it does not validate host prerequisites. Missing
qualified reload is refused before issuance, covered by the fresh focused gate.

**Host applicability remains blocked.** Retained host inventory identifies
`moss-live-web.service` on 7861 without ExecReload and `moss-internal.service` on
7862 with HUP reload and production lego paths. `moss-web.service` serves 7860;
renewal service/timer were absent. These unit facts were read from retained
`host-readonly.json` / `host-ports-readonly.json`, not freshly queried in this run.

**UNEXECUTED / authority:** I10-D05 remains pending. Owner must explicitly approve
DNS challenge writes, staging/production issuance where required, certificate and
script installation, 7861 admitted-runtime/certificate-path cutover, qualified
signal handler and unit changes, SIGHUP on both services, and timer activation.
Adding ExecReload alone is insufficient. If reload is not approved, an attended
restart/cutover needs separate approval. Actual due renewal and host recovery are
unmeasured. Attended Chrome trust/secure-context/microphone checks and overlap proof
require the operator; no certificate exceptions or automated attendance claimed.

## F3 — Hygiene and operator documentation

- Evidence-writing geometry test now saves screenshots through pytest `tmp_path`;
  390/400/1280 tests passed. Previously committed WP2 screenshots stayed unchanged.
- Regenerated WP3 raw log: 3,396,624 bytes, ignored; 17,640/17,640 rows match base
  directly, without hashes. Aggregate: 12,960 near-speech rows, 80 false suppressions,
  653 echo-suspect rows. This confirms reproducibility, not capture-policy acceptance.
  Named WP1 `fix-broad.txt` is 258,059 bytes; the >1 MB premise is false.
- Layout script and its rejection test passed; verification files live under
  `docs/verify/wp13/`. No root VERIFY copies. Raw test logs remain ignored.
- Read both updated operator documents: `docs/handoffs/e2e-smoke-for-operator.md`
  and `docs/handoffs/demo-script.md` expect cross-lane overlap, retire the
  never-overlap workaround for the per-lane build, and explicitly retain pending
  attended proof through live -> Stop -> saved -> reopen/export. Same-lane overlap
  and speakers-mode echo are distinct measurements.
- TLS runbook includes explicit unexecuted actions, 7861 unit/reload blocker,
  rollback, ordinary Chrome trust steps, and pending I10-D05 authority.

## F4 — Scope, deviations, and delivery

Only this result and four compact fresh evidence files were added. No application,
operator document, other work-package tracked file, or policy changed in this session.
Host/DNS use was read-only TLS observation. Local tests use disposable certificates
and mocked issuance commands; these do not constitute public issuance or activation.
All invoked test/verification command sessions exited; no persistent server or tunnel
was started. No push/merge/deploy/GitHub writes.

WP13-specific `docs/verify/wp13/` layout supersedes COMMON's generic root names as
explicitly instructed. One temporary `frontend/.npmrc` routed npm cache to
`.wp13runtime/npm-cache` to honor worktree-only writes; removed after testing.
An initial optional inventory read used nonexistent `hygiene-inventory.json`;
corrected to the existing `.md`, no product or verification failure.
An added metadata comparison initially assumed unwrapped prior JSON (`KeyError`);
corrected to its `result` wrapper and rerun successfully.
No other execution deviation; no typecheck/build requested by VERIFY.md.
This verification commit follows the tested SHA; final commit SHA and clean-tree
confirmation are reported after committing, avoiding a self-referential SHA here.
