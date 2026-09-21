# I2 fresh-clone verification

Run from a fresh clone of `round4/impl-i2`. No decoder, tunnel, or network access is
needed. `npm ci` must use the existing local cache.

```sh
git rev-parse HEAD
git status --short --branch
npm ci --offline --prefix frontend

py=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$py" -c \
  'import moss_transcribe_diarize as m; print(m.__file__)'

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$py" -m pytest -q -p no:cacheprovider \
  tests/test_terminal_label_capture.py \
  tests/test_live_lane_decode.py \
  tests/test_live_terminal_finalizer.py \
  tests/test_windowed_transcription.py \
  tests/phase2/test_retained_file_claim.py \
  tests/test_r4_gap_terminal_identity.py \
  tests/test_p_f2f6_violating_controls.py \
  tests/test_p_f4_validate_resume_violating_controls.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$py" \
  prototypes/s17-identity-rerun/run.py --plan-only \
  --out /private/tmp/impl-i2-fresh-s17-plan.json

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$py" -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build

git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets frontend
git diff --exit-code 0de56e1a -- \
  moss_transcribe_diarize/app/live_identity.py \
  moss_transcribe_diarize/app/live_identity_album.py \
  moss_transcribe_diarize/app/live_provider_bundle.py
git diff --name-only 0de56e1a -- moss_transcribe_diarize
git status --short --branch
```

Expected:

- import resolves inside the fresh clone;
- focused controls have zero failures, including both gap branches;
- S17 reports `capture.status=READY`, three raw/derived streams, 184 planned, zero spent;
- backend has zero failures, 5 skipped, 2 xfailed (only Jamie controls), 37 subtests;
- frontend is 312/312; typecheck and Vite build pass; build changes no assets;
- product diff lists only `live_transcript_convergence.py`, `live_lane_decode.py`,
  `terminal_label_capture.py`, `windowed_transcription.py`, and the authorized
  `phase2_file.py` seam;
- identity constants/files are byte-identical; final tree is clean.

Falsify I2 if contained `S02` is absent, same-label raw spans do not map to one native
partition, capture affects proposal bytes, the sink names the preparer, native/captured
partitions differ, Adam/Keyu controls change, any resume shape changes verdict, File
inference options are not bound, either gap branch fails, or any external request occurs.
