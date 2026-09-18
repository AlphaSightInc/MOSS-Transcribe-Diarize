# WP18 commands and confinement

All commands run in the WP18 worktree; no external mutations, shared services, GitHub,
push, merge, deploy, or other worktrees. Python imports verified in this checkout.

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp18runtime/tmp"
export XDG_CACHE_HOME="$PWD/.wp18runtime/cache"
export NUMBA_CACHE_DIR="$PWD/.wp18runtime/numba"
export npm_config_cache="$PWD/.wp18runtime/npm-cache"
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
"$PY" prototypes/streaming-diarization/wp18-file-identity/probe.py --decode
# Replay retained local decoder outputs without further GPU requests:
"$PY" prototypes/streaming-diarization/wp18-file-identity/probe.py
"$PY" -m pytest -q -p no:cacheprovider -p evidence.mvpfix.wp18.local_scratch --basetemp=.wp18runtime/pytest tests
npm --prefix frontend test -- --run --configLoader native
```

Own tunnel only, port 18118, serial requests; queue recorded before each of 3 requests.
Command: `ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o UpdateHostKeys=no -o StrictHostKeyChecking=yes -L 127.0.0.1:18118:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us`.
Initial attempt with UserKnownHostsFile=/dev/null failed strict host verification; zero
requests, no accepted unknown key. Second attempt uses existing known hosts read-only.

The full-suite scratch plugin derives from WP16's confinement-only plugin. It relocates
hardcoded /tmp test fixtures and shortens UNIX socket addresses, without product changes
or assertion changes. Frontend node_modules symlink is read-only dependency reuse.
