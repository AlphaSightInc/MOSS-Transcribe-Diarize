# H2-F2 overload failure retention

- Structural question: when the real pre-Stop inference reducer rejects overload events, which fixed check and content-free counters explain the failure?
- Minimum primitives: the captured product event list, per-session accepted/accounted sample frontier, the reducer's fixed ValueError check, and one append-only campaign artifact. No new policy or acceptance path.
- Invariants: original ValueError and predicate verdict remain; no transcripts, audio, credentials, or exception text from external services enter the record; session ids remain opaque; capacity artifacts stay separate.
- Assumptions/unknowns: H1 overload events were lost to the old artifact collision, so the failing counter and value are unknown. A new host run is required to identify them.
- Falsifier: a production-shaped invalid rolling counter raises ValueError but leaves no registered `overload/...` failure record, or a valid projection records failure / changes its result.
- Tools: prescribed Python and focused pytest prove RED/GREEN at the product reducer and campaign artifact seam; full backend and bundle catch unrelated regressions; no decoder request is needed. Docker is only a pre-check and cannot close the host gate.

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python -m pytest -q -p no:cacheprovider tests/phase2/test_h2f2_overload_retention.py`
