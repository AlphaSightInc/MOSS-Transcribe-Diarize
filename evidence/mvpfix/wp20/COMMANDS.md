# WP20 commands / custody

All shell commands run with cwd:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp20-lane-endpointing`.
Initial branch mvpfix/wp20-lane-endpointing, clean SHA de35ef365724caad47c407bd41c34e21182d20c7.
Python import was confirmed inside this tree. No other worktree writes permitted.

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/runs/wp20/tmp"
WP20_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -L 127.0.0.1:18120:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
# Separate process, same cwd/env:
"$WP20_PY" prototypes/streaming-diarization/wp20/stack.py --state runs/wp20/state --cert runs/wp20/cert.pem --key runs/wp20/key.pem --port 17880 --vllm-base-url http://127.0.0.1:18120/v1 --max-requests 280
"$WP20_PY" prototypes/streaming-diarization/wp20/capture.py
# Only after capture and local stack have stopped:
"$WP20_PY" prototypes/streaming-diarization/wp20/replay.py
"$WP20_PY" prototypes/streaming-diarization/wp20/analyze.py
```

Stack semaphore <=2; capture uses one meeting at a time. Replay serial.
WP20's specific 500 budget supersedes COMMON's 200; combined stack/replay ledger
is checked before each standalone request. No draft lane enabled. Existing
manifest and shared model assets read only. Runtime database, socket, scratch,
TLS, PCM and public transcripts stay under ignored runs/wp20/.
Frontend dependencies symlink the supplied node_modules; native config loader and
cache=false avoid writes through that symlink. No install.

Initial read-only path lookups found no live_vad.py (actual provider is
live_provider_bundle.WebRtcSpeechProvider), no live_inference.py or
live_decode_adapter.py (actual adapter is live_adapters.RunnerBoundedWavInference),
and WP12 verification lives at its worktree root, not docs/verify/wp12/.
An unauthenticated descriptor readiness probe returned the expected workspace
credential refusal; the actual measurement client bootstraps a private workspace.
No failed measurement hidden by those exploratory lookups.

Initial gates (before VERIFY.md): Python1874 passed/2 skipped/37 subtests,149.29s;
frontend244/27 files,2.71s; typecheck/build pass, asset diff empty. Commands use
`-p evidence.mvpfix.wp17.local_scratch --basetemp=runs/wp20/pytest-initial`,
`npm --prefix frontend test -- --run --configLoader native --cache=false`,
`npm --prefix frontend run typecheck`, `npm --prefix frontend run build -- --configLoader native`.
Full Python flags and verification repeat commands are in docs/verify/wp20/VERIFY.md.
Logs normalize only trailing whitespace; original bytes remain in runs/wp20/*.raw.
Owned server/tunnel closed; lsof for17880/18120 returned no output/exit1.
The required fresh transition uses `/new` in own pane %26, then the self-contained
VERIFY.md prompt. Official command behavior was checked at
https://learn.chatgpt.com/docs/developer-commands?surface=cli (new chat, same CLI).
