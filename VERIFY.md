# WP1 fresh-context verification — partial evidence only

First cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp1-lane-decode.
Modify nothing outside this worktree. No real decoder requests: 196/200 consumed.
Read prototypes/lane-decode-proto/NOTES.md. Production fix is NOT implemented.
This file cannot certify the uncompleted WP1 assignment.

1. Verify `git diff 37979e53 -- moss_transcribe_diarize tests` is empty. A nonempty
   diff falsifies the claim that only an isolated prototype/evidence was added.
2. Run:
   `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_live_coordinator.py tests/test_live_mixer.py tests/test_live_identity.py tests/test_live_transcript_convergence.py`
   Expected 70 passed. This checks unchanged production imports, NOT the overlay.
3. Read evidence/mvpfix/wp1/scores.json; independently recompute requests.jsonl
   count (196), monotonic unique request IDs (1..196), case count (9), saved/final
   equality count (9/9), and sample_count=40000 spans in spans.jsonl (80); median
   0.17043133299739566 s and max 0.9631550000049174 s. Mismatch falsifies report.
4. Confirm no listeners on loopback 17871/18101. Do not kill unknown processes.
5. Write VERIFY-RESULT.md with exact results and fresh-context provenance. State
   clearly: evidence verified/unverified; WP1 remains INCOMPLETE; no fix acceptance.
   If not actually entered via /new, say that rather than claiming fresh context.
6. Commit only verification output, then report <=60 lines in this pane: branch,
   SHA, partial prototype findings, 196/200 budget, unfinished fix/tests, no /new
   fix-verification claim. Required unblock: explicit larger decoder request budget
   (650 requested, not yet approved); exact cut references or acceptance of
   explicitly boundary-biased ordered reference edits.

COMMON.md requires /new after a completed fix. That stage has not been reached.
Do not convert this partial-evidence recipe into a claim that requirement passed.
