# WP11 commands and process custody
All commands run inside MOSS-Transcribe-Diarize-wt-wp11-export-labels.
`PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`
`export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/runs/wp11"`
Import check resolved this worktree's moss_transcribe_diarize/__init__.py.

- Prototype: `$PY evidence/mvpfix/wp11/prototype.py` (throwaway deleted; absorbed
  into tests/phase2/test_export_oracle.py; full state retained in prototype.log).
- Projection prototype: `$PY runs/wp11/projection-prototype.py` (deleted after
  exact regression test and actual browser verification; projection-prototype.log).
- Oracle tests: `$PY -m pytest -q -p no:cacheprovider tests/phase2/test_export_oracle.py`.
- Consumer tests: same plus `tests/phase2/test_owner_bound_live_meeting.py`.
- Full Python: `$PY -m pytest -q -p no:cacheprovider --basetemp=runs/wp11/pytest-final tests`.
- Confined full Python: add `-p evidence.mvpfix.wp11.local_scratch` and a fresh
  `--basetemp=runs/wp11/pytest-confined-final`; it only redirects fixture /tmp paths.
- Full frontend: `npm --prefix frontend test -- --run --configLoader native --cache=false`.
- Typecheck: `npm --prefix frontend run typecheck`.
- Shipped assets: `npm --prefix frontend run build -- --configLoader native`.
- Baseline reproduction: `git archive HEAD moss_transcribe_diarize tests frontend/src
  frontend/package.json frontend/vite.config.ts frontend/tsconfig.json
  evidence/mvpfix/wp2/fixtures.json pyproject.toml | tar -x -C runs/wp11/base`
  at original HEAD b31683a6, then from INSIDE that copy run pytest on the five files
  listed in NOTES.md; identical 19 failed node IDs (expected-failures.txt).

Live commands (no services remain):
```
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ControlMaster=no -o ControlPath=none -o UpdateHostKeys=no -o StrictHostKeyChecking=yes -L 127.0.0.1:18111:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
curl -fsS http://127.0.0.1:18111/metrics
openssl req -x509 -newkey rsa:2048 -nodes -keyout runs/wp5/key.pem -out runs/wp5/cert.pem -days 2 -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1
$PY prototypes/browser-stress/stack.py --state runs/wp5/state --cert runs/wp5/cert.pem --key runs/wp5/key.pem --port 17871 --vllm-base-url http://127.0.0.1:18111/v1 --max-requests 60
$PY prototypes/browser-stress/run.py 8,11,10,12 --base https://127.0.0.1:17871 --microphone-file /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_keyu_jin_60s/audio.wav --output evidence/mvpfix/wp11/integrated
```
First stack PID 5562 stopped after 10 calls for projection repair; replacement PID
12629 used `--max-requests 50` (remaining budget), retained cumulative WP5 counter.
Second/third output dirs: integrated-final / integrated-complete. 18 + 14 calls.
Final own stack 12629 and SSH 4666 terminated; lsof shows no listeners 17871/18111.
TLS, DB, audio, temporary baseline copy, browser profiles stay in ignored runs/.
SQLite semantic-only exact-version override is supplied by the authorized local
stack recipe; no production runtime qualification claimed.
