# WP6 fresh-context verification after the authorized campaign

Run in a NEW conversation entered through `/new` in this agent's own pane MOSS:3.3
(%21). Never describe same-context analysis as fresh verification.

Only modify this worktree:
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp6-capacity-baseline
Branch: mvpfix/wp6-capacity-baseline. Do not message peers, push, merge, deploy,
restart shared services, or access product instances 7861/7862.

Read AGENTS.md, prototypes/capacity-campaign/NOTES.md,
evidence/mvpfix/wp6/AUTHORITY.md, and evidence/mvpfix/wp6/REPORT.md.
Part 0 at a20595a5 is explicitly accepted by the user. Do not repeat its test-order
investigation. This continuation changes measurement harness/evidence only.
No production repair is justified by a contaminated run or a harness interruption.

## Expected outcome

Four run directories; 9 sessions total, 7 completed and 2 deliberately interrupted;
1,612 decoder starts and finishes. The 4x600 run has 4 unavailable terminal outcomes,
4 completed saved transcripts and 4 partial audio files of 300 seconds each. Its
clean flag must stay false. No eight-session run. Two-session completed run includes
four pauses totaling 329.898415 s. Raw four-session timeout/abort errors are collector
errors, explained by recorded tape_unavailable events. No production diff or policy
repair is expected; the insufficient supplied retention declaration remains a reported
configuration limit. Current collector now recognizes unavailable and saves clock anchors.

## Execute from this worktree

```sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=.
export TMPDIR="$PWD/.wp6-tmp"
WP6_PYTHON=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
"$WP6_PYTHON" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
git branch --show-current
git rev-parse HEAD
git status --short
"$WP6_PYTHON" evidence/mvpfix/wp6/summarize.py > .wp6-tmp/fresh-summary.json
cmp evidence/mvpfix/wp6/SUMMARY.json .wp6-tmp/fresh-summary.json
"$WP6_PYTHON" evidence/mvpfix/wp6/recover_four.py > .wp6-tmp/fresh-recovered.json
cmp evidence/mvpfix/wp6/20260918-000221-4x600/recovered.json .wp6-tmp/fresh-recovered.json
"$WP6_PYTHON" -m pytest -q -p no:cacheprovider tests/test_live_terminal_finalizer.py tests/test_live_terminal_tape.py tests/phase2/test_owner_bound_live_meeting.py::test_live_stage_bound_degrades_normal_stop_to_partial_without_losing_transcript
"$WP6_PYTHON" -c 'from pathlib import Path; paths=list(Path("prototypes/capacity-campaign").glob("*.py"))+[Path("evidence/mvpfix/wp6/summarize.py"),Path("evidence/mvpfix/wp6/recover_four.py")]; [compile(p.read_text(),str(p),"exec") for p in paths]; print(len(paths), "files compile")'
git diff 37979e53 -- moss_transcribe_diarize
git diff --check
lsof -nP -iTCP:18106 -iTCP:17866 -sTCP:LISTEN
```

Expected: assigned import/branch; 4 files compile; 42 tests + 19 subtests pass; both cmp commands match; no production diff, whitespace
errors, or listeners on the two owned ports (lsof exit 1 with no output is normal).
Compare .wp6-tmp/fresh-summary.json against SUMMARY.json and the report. Recompute
counts from actions.jsonl/decoder.jsonl, not prose. Inspect runner-used.py for the
smoke/interrupted attempt and the recorded runner revision for later attempts.

Falsifiers to inspect independently:
- A decoder start/finish count differs from the report; own in-flight exceeds 2.
- A completed session lacks 4*seconds acknowledged lane frames, seconds*16000
  acknowledged audio samples, completed saved status, or zero wrong-owner responses.
  The original four-session collector lost its accepted/accounted API counters;
  only ack-derived counts and final canonical committed samples remain. Claiming those
  as captured API counters is a falsifier. The four unavailable outcomes are an
  expected negative result, not an integrity failure. Do not apply successful-capture
  assertions to the interrupted harness attempt; retain every call and its two
  durable interrupted statuses.
- A pause resumes despite ongoing foreign evidence under the corrected monitor;
  traffic during pauses exceeds requests already in flight. Record sample limits.
- A run is called clean despite foreign evidence, a failed stated gate, missing
  fairness applicability, or unmeasured release prerequisites being treated as pass.
- Eight-session overload ran without a clean four-session result.
- WER/retention/population or local-RSS limitations are omitted or overstated.

Do not make further decoder calls for verification. The authorized load is already
retained. Any new production defect must be evidenced, scoped per WP6, and reported;
never modify quality/identity/readiness/mixer/decoder policy to obtain a green result.

Write VERIFY-RESULT.md: fresh session identity if available, tested commit, exact
artifact/session/request counts, pass/fail for evidence integrity (separately naming original collector omissions), and capacity
verdict separately. Commit the result locally. Final report <=60 lines: branch +
final SHA, question/verdict, changes, exact results, limitations and deviations.
