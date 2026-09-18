# WP14 commands and custody

All shell commands run from the WP14 worktree. `environment.sh` sets local TMPDIR,
Playwright browser install directory, npm cache and Python import path.
`run_harness.py` selects only the worktree-local Playwright Chromium executable.
The venv is shared read-only; PYTHONDONTWRITEBYTECODE=1 avoids dependency bytecode.

```
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp14-integrated-e2e
source evidence/mvpfix/wp14/environment.sh
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes -L 127.0.0.1:18114:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
# Separate shell, same cwd/environment:
"$WP14_PY" prototypes/streaming-diarization/draft-lane/run_local_stack.py --state runs/wp14/state --cert runs/wp14/cert.pem --key runs/wp14/key.pem --port 17874 --vllm-base-url http://127.0.0.1:18114/v1 --max-requests 400
curl -s http://127.0.0.1:18114/metrics | rg '^vllm:num_requests_(running|waiting)'
"$WP14_PY" evidence/mvpfix/wp14/run_harness.py tests/e2e/verify_workspace.py --base "$MOSS_BASE" --allow-local-self-signed --corpus evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s --output evidence/mvpfix/wp14/workspace-final
"$WP14_PY" tests/e2e/verify_demo_lanes.py --base "$MOSS_BASE" --allow-local-self-signed --case both --output evidence/mvpfix/wp14/lanes-initial.json
"$WP14_PY" evidence/mvpfix/wp14/run_harness.py prototypes/browser-stress/run.py 15,16 --headed --base "$MOSS_BASE" --output evidence/mvpfix/wp14/browser-corrected
"$WP14_PY" evidence/mvpfix/wp14/run_harness.py prototypes/browser-stress/run.py 16 --headed --base "$MOSS_BASE" --output evidence/mvpfix/wp14/browser-lease-rerun
"$WP14_PY" evidence/mvpfix/wp14/run_harness.py prototypes/browser-stress/run.py 16 --headed --lease-seconds 35 --base "$MOSS_BASE" --output evidence/mvpfix/wp14/browser-ui-final
"$WP14_PY" tests/e2e/stress_lifecycle.py
"$WP14_PY" tests/e2e/stress_reshare.py
"$WP14_PY" -m pytest -q -p no:cacheprovider -p evidence.mvpfix.wp14.local_scratch --basetemp=runs/wp14/pytest-final tests
npm --prefix frontend test -- --run --configLoader native --cache=false
npm --prefix frontend run typecheck
npm --prefix frontend run build -- --configLoader native
```

Do not repeat all commands blindly: request budget is per WP, not per process.
All attempts are retained, including setup/collection errors and failed or unmeasured
browser cases. The final verdict file names exactly which attempt supports each row.
No new service or decoder call is required for fresh-context verification; VERIFY.md
will instruct verification of the retained real-decoder evidence and local suites.

The user explicitly requires `/new` in this same pane before verification. Official
OpenAI documentation confirms this starts a fresh chat within the CLI:
https://learn.chatgpt.com/docs/developer-commands?surface=cli#start-a-new-chat-with-new
The self-handoff targets only this pane, MOSS:3.2 / %26, verified against TMUX_PANE.
No peer messages, external publication, push, merge or deployment.
