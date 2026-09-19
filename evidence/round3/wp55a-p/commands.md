# WP55a-P command receipt

- Candidate: `a7a738cf9f9ff246f64c52c112e0bf597ba58241`
- One-command prototype: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/identity/file_policy_compare.py`
- Result: exit 2 by design; gate `FAIL`; no qualifying policy; decoder requests 0.
- Second full run: process observed active at elapsed `06:58`; completed on the next 30-second poll after 14.6 seconds. Exact wall duration is bounded to 412.6–432.6 seconds; the harness did not yet self-record monotonic duration.
- Unpatched violating control: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python /Users/gao/Documents/Codex/2026-09-19/moss-round2/fable-review-evidence/identity_repro.py`
- Unpatched CASE 1: pooled `S01`; published `['S00', 'S01']`; confirmed pooled-correct→unknown.
- Unpatched CASE 2: pooled `S01`; published `['S02', 'S01']`; confirmed confident cross-person move.

Timing is reported as a measured bound, not an invented exact value. All counts and policy denominators are exact in `file-policy-results.json`.
