# WP6 verification — isolated-manifest continuation

Only this worktree/branch: MOSS-Transcribe-Diarize-wt-wp6-capacity-baseline,
mvpfix/wp6-capacity-baseline. Initial fresh-context commit 57907d76. Part 0 a20595a5
accepted; do not repeat its investigation. No decoder calls, host inspection,
shared-manifest writes, peer messages, push, merge or deployment for verification.

Read AGENTS.md, prototypes/capacity-campaign/NOTES.md, evidence/mvpfix/wp6/AUTHORITY.md,
REPORT.md, MANIFEST.md, WP12.md and 20260918-002944-4x600/STOP-ASSESSMENT.md.
Original VERIFY.md expected four historical attempts; their reductions matched before
this continuation's authorized run. Current expectation: five attempts, 13 sessions,
9 completed/4 interrupted (2 deliberate), 2,887 decoder starts/finishes. The original
300-second-cap 4x600 remains negative and unchanged.

New run: 1,275 starts/finishes; four 600-second MP3s; 2 final/completed, 2 interrupted
(helper lease expiry); 12/32 foreign samples and 3 pauses. Clean false; no eight-session
run. Births 2/2/unknown/unknown. Missing HTTP details/counters for the two errors are
acknowledged collector omissions, not invented data. Production diff empty.

## Full suites executed before updating this file

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <COMMON Python> -m pytest -q -p no:cacheprovider tests`:
with isolated short TMPDIR, 1701 passed, 1 failed, 2 skipped, 37 subtests. Only failure:
test_voiceprint_latency_measurement.py::test_name_latency_is_independent_of_observer_polling_delay
(the explicitly tolerated pre-WP4 fixture). Initial repository-local TMPDIR caused
three additional environment failures; see NOTES.md and both retained logs.
`npm --prefix frontend test -- --run`: 24 files/206 tests pass after prescribed symlink.
Do not repeat full suites unless changes or unresolved concerns justify it.

## Execute offline from this worktree

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR=/private/tmp
WP6_PYTHON=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
"$WP6_PYTHON" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
git branch --show-current
git rev-parse HEAD
git status --short
"$WP6_PYTHON" evidence/mvpfix/wp6/summarize.py > .wp6-tmp/fresh-summary.json
cmp evidence/mvpfix/wp6/SUMMARY.json .wp6-tmp/fresh-summary.json
"$WP6_PYTHON" evidence/mvpfix/wp6/recover_four.py > .wp6-tmp/fresh-recovered.json
cmp evidence/mvpfix/wp6/20260918-000221-4x600/recovered.json .wp6-tmp/fresh-recovered.json
"$WP6_PYTHON" evidence/mvpfix/wp6/recover_run.py evidence/mvpfix/wp6/20260918-002944-4x600 > .wp6-tmp/fresh-rerun.json
cmp evidence/mvpfix/wp6/20260918-002944-4x600/recovered.json .wp6-tmp/fresh-rerun.json
"$WP6_PYTHON" -m pytest -q -p no:cacheprovider tests/test_live_terminal_finalizer.py tests/test_live_terminal_tape.py tests/phase2/test_owner_bound_live_meeting.py::test_live_stage_bound_degrades_normal_stop_to_partial_without_losing_transcript
"$WP6_PYTHON" -c 'from pathlib import Path; paths=list(Path("prototypes/capacity-campaign").glob("*.py"))+[Path("evidence/mvpfix/wp6")/name for name in ("summarize.py","recover_four.py","recover_run.py")]; [compile(p.read_text(),str(p),"exec") for p in paths]; print(len(paths), "files compile")'
git diff 37979e53 -- moss_transcribe_diarize
git diff --check
lsof -nP -iTCP:18106 -iTCP:17866 -sTCP:LISTEN
```

Expected: assigned import/branch, all 3 comparisons match, 6 files compile,
42 passed/19 subtests (one existing Starlette warning), no production diff or
whitespace errors. lsof exits 1 with no output: no owned listeners.

Additional evidence check, same environment:
```sh
"$WP6_PYTHON" - <<'PY'
import json
from pathlib import Path
root=Path('evidence/mvpfix/wp6')
summary=json.loads((root/'SUMMARY.json').read_text())
assert len(summary['runs'])==5 and summary['total_decoder_calls']==2887
assert sum(r['decoder_completed'] for r in summary['runs'])==2887
assert max(r['maximum_own_inflight'] for r in summary['runs'])==2
run=root/'20260918-002944-4x600'
r=json.loads((run/'result.json').read_text())
assert not r['clean'] and r['foreign_load_detected']
assert all(s['acknowledged_frames']==2400 and s['foreign_probes']==2400 and s['wrong_owner_failures']==0 for s in r['session_results'])
d=[json.loads(x) for x in (run/'decoder.jsonl').read_text().splitlines()]
assert {x['ordinal'] for x in d if x['kind']=='start'}=={x['ordinal'] for x in d if x['kind']=='finish'}==set(range(1,1276))
a=json.loads((run/'recovered.json').read_text())['per_session']
assert [x['saved_meeting_status'] for x in a]==['completed','completed','interrupted','interrupted']
assert all(float(x['mp3_probe']['format']['duration'])==600 for x in a)
assert [x['identity_counts']['identities_born_count'] if x['identity_counts'] else None for x in a]==[2,2,None,None]
source=Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json'
assert source.read_bytes()==Path('.wp6-tmp/manifest-original.json').read_bytes()
assert source.stat().st_mtime_ns==1787665017563735525
assert json.loads((run/'descriptor.json').read_text())['bounds']['max_tape_bytes']==57600000
assert not list(root.glob('*-8x*'))
print('PASS: counts, ownership probes, decoder completion, saved durations, birth limits, shared manifest, overload gate')
PY
```

Falsifiers: missing decoder finishes, extra in-flight calls, altered historical raw
records/shared manifest/production source, false complete-audio claims, unknown birth
counts presented as numbers, unassigned buckets called people, or capacity called
clean despite contention/interruption. Evidence integrity is separate from capacity,
native deployment provenance and fixed-corpus quality.
Write VERIFY-RESULT.md distinguishing fresh verification of the starting artifacts
from same-continuation verification of newly edited harness/results. Commit locally.
Final WP6 report <=60 lines. No claim of another context reset for this continuation.
