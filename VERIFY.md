# WP4 rejected-predicate evidence verification

Verify the prototype stop only, NOT implementation acceptance. No fix exists.
Work only in /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp4-oracles-n1.
No services/provider calls required. From this worktree:

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
WP4_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
"$WP4_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
"$WP4_PY" prototypes/streaming-diarization/wp4-oracle-falsifiers/measure_oracle.py
"$WP4_PY" prototypes/streaming-diarization/wp4-oracle-falsifiers/measure_file_boundaries.py
"$WP4_PY" -m pytest -q -p no:cacheprovider --basetemp=evidence/mvpfix/wp4/.pytest-tmp tests/phase2/test_attended_g7_canary.py
```

Expected import: this worktree. Oracle: 2/2 small positives accepted; 4/4 corrupt
controls rejected; valid_public_corpus_overlap falsely rejected with 12 duplicates,
0 WER on both lanes, 106 system and 48 microphone words. Production G7 counts-only
control accepted: 2 scenarios, 0 transcript words supplied.
File fixtures: 8 records, 5 failed, 3 completed; completed rows have 0 segments.
Existing G7 baseline: 42 passed (original measured time 4.65 seconds).

Falsifiers: corpus overlap does not reproduce 12 false duplicates; reference inputs
lack correct tags/actual timings; G7 production validator rejects this fixture.
These fixtures do not measure real HTTP failures, no-speech behavior or ASR quality.
If run in a genuinely fresh /new session, write VERIFY-RESULT.md with exact counts
and provenance. Never label same-context execution fresh. COMMON requires /new
AFTER the fix; that stage was not reached because of the prototype stop.
