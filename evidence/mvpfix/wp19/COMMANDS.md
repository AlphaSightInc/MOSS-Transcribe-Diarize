# WP19 commands and checks

All commands run from the WP19 worktree. Python:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`.
Always `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`; `TMPDIR=$PWD/.wp19runtime/tmp`.

- Import custody: `python -c 'import moss_transcribe_diarize as m; print(m.__file__)'`.
  Detect wrong editable checkout; stop if import resolves outside WP19.
- Initial prototype: `python prototypes/streaming-diarization/wp19-file-identity-album/prototype.py`.
  Perfect recurring voices and pinned-encoder WP18 replay; a count mismatch stops implementation.
  Absorbed as `probe.py`; product now owns the measured resolver, state printer stays in bench.
- Real acceptance: `python prototypes/streaming-diarization/wp19-file-identity-album/accept_real.py --decode`.
  Uses own tunnel 18119, serial requests, 18 total. Decode metadata and all per-segment
  truth-overlap decisions retained; raw words/audio remain ignored. Wrong count blocks default.
- `python -m pytest -q -p no:cacheprovider tests/test_file_identity_album.py tests/test_live_identity_album.py tests/test_live_identity_sweep.py`.
  Detect identity/admission/sweep regressions; repair before default switch.
- A4: `WP19_SAVED_FIXTURE=$PWD/evidence/mvpfix/wp19/saved-file-fixture.json python -m pytest -q -p no:cacheprovider tests/phase2/test_file_album_acceptance.py`.
  Real file task/window stitching/archive/restart, fake decoder/vectors. Export fixture is synthetic.
- Lease: 20 separate pytest processes for
  `tests/phase2/test_owner_bound_live_meeting.py::test_helper_lease_loss_interrupts_without_client_terminal_request_and_never_resumes`.
  Detect load/scheduling dependence; keep callback under explicit timer control.
- Full Python: `python -m pytest -q -p no:cacheprovider -p evidence.mvpfix.wp19.local_scratch tests --basetemp=.wp19runtime/full-tests`.
  Detect integration regressions; no new failure waived. Scratch plugin from WP18 only relocates
  hardcoded fixture paths and Unix sockets inside this worktree; no product behavior changes.
- Frontend: `npm --prefix frontend test -- --run --configLoader native` and
  `npm --prefix frontend run typecheck`. Detect export/schema and TS errors; fix before acceptance.
- `git diff --check` and `bash scripts/check_verify_layout.sh`: detect malformed diff/layout.
- `lsof -nP -iTCP:18119 -sTCP:LISTEN`: detect abandoned owned tunnel; stop it before handoff.

Failed authoring attempts retained in test-summary.json: A4 used nonexistent server export
route (real exports are frontend serializers); new JSON export test counted strings in
both text and target keys (now validates parsed turn text). No production failures inferred.

Dependencies: frontend/node_modules symlink to shared installed dependencies, no npm install.
Initial frontend command omitted --configLoader native; later commands use native loader
so Vite does not bundle config through the shared node_modules directory. No source changes
outside WP19; all durable task artifacts live here. No frontend production code changed, so
asset regeneration is unnecessary; frontend tests/typecheck cover the new export fixture.
