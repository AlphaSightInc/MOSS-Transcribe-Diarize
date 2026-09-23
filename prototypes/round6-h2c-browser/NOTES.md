# H2-C offline diagnosis

- Structural question: Which browser-family H1 failures are explained by retained observations, and which require a new host measurement?
- Minimum primitives: frozen `phase2_acceptance` validators; H1 raw predicate records; content-free fidelity metrics; host pytest XML.
- Invariants: keep 2%/1% fidelity bounds, reference SHA, G9's 19 checks, and all acceptance populations fixed. No provider or decoder dispatch.
- Assumptions/unknowns: G9's 19 check bits and G1's intermediate surfaces may have been lost when measurement raised. The retained pane screenshots are absent.
- Falsifier: if the receipts include the G9 check map or G1 surface counts, identify the exact failure; if the fidelity screenshots or pinned reference comparison can be recovered, classify UI versus environment. Otherwise report the specific evidence gap and stop.
- Tools: the prescribed Python imports production validators; JSON/XML parsing supplies denominators without copying transcripts or secrets. A host rerun changes the decision only if it retains the missing content-free facts.
- One command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/round6-h2c-browser/run.py /Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/r6-h1-20260923T051306Z/20260923T051605Z-f7fe4ad/raw`
