# WP16 command record

All commands run in the WP16 worktree with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`.
Python: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`.
`TMPDIR=$PWD/.wp16runtime/tmp`, npm cache and test/cache files remain in `.wp16runtime`.
Shared frontend dependencies symlinked. No dependency installation. Initial default Vite
loader used the shared `.vite-temp` directory; final/fresh commands use `--configLoader native`.

- Preparation: `python prototypes/streaming-diarization/wp16-file-url-long/prepare.py`.
- Tunnel: `ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes -L 127.0.0.1:18116:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us`.
- Source: `python prototypes/streaming-diarization/wp16-file-url-long/sources.py` (17877 HTTPS, 17878 hung HTTP).
- Stack: `SSL_CERT_FILE=$PWD/.wp16runtime/ca.pem python prototypes/streaming-diarization/wp16-file-url-long/stack.py --state .wp16runtime/state --cert .wp16runtime/cert.pem --key .wp16runtime/key.pem --port 17876 --vllm-base-url http://127.0.0.1:18116/v1 --max-requests 200`.
- Certificates: COMMON's openssl invocation, output only to `.wp16runtime`; certifi roots plus loopback certificate compose `ca.pem` (no host trust changes).
- Measurements: `python prototypes/streaming-diarization/wp16-file-url-long/sample.py` (30 s RSS/shared queue).
- Browser: `python prototypes/streaming-diarization/wp16-file-url-long/probe.py long.wav`; short suite `empty.wav text.mp3 silence.wav two.wav truncated.mp3 direct missing html hang commons youtube`; remaining `long.mp3 long.m4a concurrent commons`.
- Browser surface recheck, no decodes: `python prototypes/streaming-diarization/wp16-file-url-long/surfaces.py`.
- Actual disk admission: `python prototypes/streaming-diarization/wp16-file-url-long/oversize.py`.
- Exact-zero correction prototype: `python prototypes/streaming-diarization/wp16-file-url-long/silence.py`.
- Reference scoring: `python prototypes/streaming-diarization/wp16-file-url-long/score.py` (existing ordered edit-distance oracle; no new scoring threshold).
- Full suite: `python -m pytest -q -p no:cacheprovider -p evidence.mvpfix.wp16.local_scratch --basetemp=.wp16runtime/pytest-final tests`.
- Frontend: `npm --prefix frontend test -- --run --configLoader native`.

The path-only pytest plugin redirects five existing hardcoded `/tmp` socket fixture families and an admin temp directory into this worktree; assertions/product methods remain unchanged. Relative socket paths avoid macOS's pathname length limit.
