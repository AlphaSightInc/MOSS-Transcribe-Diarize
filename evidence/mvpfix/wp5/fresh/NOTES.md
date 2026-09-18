# Fresh verification / visibility probe verdict

Existing browser contracts reproduced: 6 PASS / 2 known N1 FAIL of 8. Baseline remains 11 PASS / 2 FAIL / 1 BLOCKED of 14. Full counts, command, deviations and fresh-context provenance: [VERIFY-RESULT.md](../../../../VERIFY-RESULT.md).

One throwaway native-visibility prototype, retained as verification evidence: `visibility-probe.py`. Question: can headless Chromium actually become hidden through background flags and native CDP focus/lifecycle controls? Chrome 153.0.8010.53 yielded 0/5 hidden observations, zero visibilitychange events. Focus false is not visibility hidden. Lifecycle state hidden was rejected. Case 3 remains BLOCKED for this attempted configuration; other configurations unmeasured. No production design change or decoder call.

One command from repository root (existing output deliberately prevents silent retry):
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/runs/wp5" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/mvpfix/wp5/fresh/visibility-probe.py`
