# FIX-3.1 fresh-context verification

Verify only; do not repair source. Work in this clone and write `docs/verify/fix-3.1/VERIFY-RESULT.md` with PASS/FAIL, tested SHA, exact counts, and any failure.

1. Confirm branch `round3/fix-scheduling`, `738cdfdd` is an ancestor, and tracked state is clean except the eventual `VERIFY-RESULT.md`.
2. Confirm Python import custody resolves inside this clone.
3. Run:
   - `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests`
   - `npm --prefix frontend test -- --run`
   - `npm --prefix frontend run typecheck`
   - `npm --prefix frontend run build`
4. Independently inspect the diff from `738cdfdd` for FIX-3.1 only: headed reference start preservation; ordered interval-bound visible-word credits; wrong/missing null clocks; exact 300 s muted headed replay harness; read-only per-owner scheduler clocks projected through existing operator status without policy or endpoint changes; healthy and violating controls.
5. Inspect `evidence/round3/fix-3.1/s9-headed.json` and request receipt. Require: 889 rows on API and DOM; every wrong/missing row has null first/stable fields; every finite latency is non-negative; finalization `final`; request starts=ends<=250; peak<=2. Confirm bucket-only refusal has a test.
6. Confirm ports 17851, 19251, 18251 are free and `/Users/gao/Documents/Codex/2026-09-19/moss-round3/status/GPU-LEASE.md` text is exact `FREE`.
7. `docs/verify/fix-3.1/VERIFY-RESULT.md` must be <=60 lines. Do not push, merge, deploy, message peers, or modify any other file.
