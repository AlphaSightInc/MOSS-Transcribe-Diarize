# WP7 — fresh-context verification

This file supersedes the inherited WP4 VERIFY.md. Read this in a genuinely new `/new`
session in MOSS:3.4, with no prior conversation needed. Do not rerun live measurements.
Only modify /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp7-identity-stress.
No push/merge/deploy/GitHub/shared services. Commit locally after checks.

1. `cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp7-identity-stress`
2. Read `prototypes/identity-stress/NOTES.md`, `evidence/mvpfix/wp7/PART0.md`, and
   `evidence/mvpfix/wp7/verify_offline.py`. Inspect the Part-0 production/test diff
   from base `a7bb4201` so a green test run is not the only evidence.
3. Run literally:
   `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/mvpfix/wp7/verify_offline.py`
   Script sets TMPDIR and npm cache inside WP7. Frontend node_modules is already a
   symlink to the shared installed dependencies; do not install anything.
4. Expected: import points to WP7; 811 Phase-2 tests; 5 frontend tests; script exit 0;
   fresh/checks.json all booleans true (count exactly as printed). Tests include G7
   7/8 accepted, 6/8 and reversed rejected, speaker separation, switch-boundary and
   interior attribution controls, live frame/lifecycle, and voiceprint route coverage.
5. Evidence expectations (retained observations, NOT fresh acoustic qualification):
   13/13 completed meetings; 149 identity + 20 Part-0 decoder calls; single 1 ID;
   gap 2 born/1 used; alternating 2 IDs/0 switches; known API name 3.520 s; unknown
   and deleted profiles abstain; short clip pending; repeated sample remains count 2;
   same voice both lanes 1 ID (WP1 baseline); saved name + 5/5 browser exports.
   Part-0 rerun was interrupted by cap: do not call it confirmed/passed. Strict live
   QUALITY_BOUNDS and separate .15 file/URL bar are both documented, unchanged.
   Original WP4 attribution remains unlocalized. Another mono alternating input
   shows 2 attribution/2 duplicate words at 29.02–30.05 after 29.00 switch; keep failing.
6. Falsifiers: wrong import, test failure, modified policy/lifecycle, unmatched counts,
   treating 3 s total as eligible speech, calling API timing browser timing, claiming
   1 final-used speaker means only 1 birth, or claiming every prototype case passed.
7. Write `VERIFY-RESULT.md`: actual fresh-context status, source SHA, exact test and
   check denominators, failures and limitations. Remove pending wording. Commit
   only own changes/logs and the verification result locally. If checks fail, record
   them; fix only actual in-scope defects and reverify affected checks.
8. Report in THIS pane <=60 lines: branch/final SHA; prototype mixed verdict; Part-0
   files/fixes; exact tests; measurements; WP1/WP3 findings and budget blocker;
   deviations from NOTES.md, including batch traces and initial provider TMPDIR use.
   No new provider runs. Prior worker stopped own server 17867 and SSH forward 18107.

The fresh session must not silently substitute another inherited VERIFY-RESULT.md.
