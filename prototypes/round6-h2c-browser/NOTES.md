# H2-C offline diagnosis

- Structural question: Which browser-family H1 failures are explained by retained observations, and which require a new host measurement?
- Minimum primitives: frozen `phase2_acceptance` validators; H1 raw predicate records; content-free fidelity metrics; host pytest XML.
- Invariants: keep 2%/1% fidelity bounds, reference SHA, G9's 19 checks, and all acceptance populations fixed. No provider or decoder dispatch.
- Assumptions/unknowns: G9's 19 check bits and G1's intermediate surfaces may have been lost when measurement raised. The retained pane screenshots are absent.
- Falsifier: if the receipts include the G9 check map or G1 surface counts, identify the exact failure; if the fidelity screenshots or pinned reference comparison can be recovered, classify UI versus environment. Otherwise report the specific evidence gap and stop.
- Tools: the prescribed Python imports production validators; JSON/XML parsing supplies denominators without copying transcripts or secrets. A host rerun changes the decision only if it retains the missing content-free facts.
- One command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/round6-h2c-browser/run.py /Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/r6-h1-20260923T051306Z/20260923T051605Z-f7fe4ad/raw`

## Addendum 1: Chrome launch contamination

- Structural question: does importing the WP5 browser prototype alter process-wide temporary-file placement for unrelated pytest cases?
- Minimum primitives: the existing import helper in `test_browser_stress_artifacts.py`, `os.environ`, and `tempfile.tempdir`; a deep-path Linux Chrome test probes the reported socket-path failure.
- Invariants: importing a prototype has no global temp-dir side effect; running its CLI still creates and selects its private WP5 scratch directory; browser tests use the same launch seam.
- Assumption: the lead's host A/B established the Chrome path-length mechanism (35-character TMPDIR passes; 125 fails). Local macOS Chrome cannot validate Linux socket behavior.
- Falsifier: the imported module leaves `TMPDIR` and `tempfile.tempdir` unchanged on frozen source, or the CLI loses its scratch setup after moving the configuration into `main`.
- Tools: the focused pytest catches the import-time leak; a long-path Docker invocation checks Linux launch and the 37 H1 launch cases. No decoder or provider request is needed.

## Verdict (lead, 2026-09-23)
- 37 host Chrome-launch failures: CONFIRMED root cause = import-time TMPDIR in `prototypes/browser-stress/run.py` under a deep checkout (host A/B 35 vs 125 chars); FIXED by moving the setup into `main()` (reviewed PASS).
- G9 `browser_final_summary`: failing check unidentifiable from H1 receipts; FIXED diagnostic retention (`summary-checks.json`, 19 booleans + validator result). G1 pre-admission / G10: PARKED to H2-E / H2-H.
