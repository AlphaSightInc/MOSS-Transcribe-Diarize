# WP5 browser stress bench (prototype retained as standing bench)

Question: which adversarial browser sequences break the base product's lifecycle and durability contracts?
Hypothesis: actions preserve one truthful meeting, terminal cleanup, and saved data across reload/restart.
Falsifier: an actual browser action produces a duplicate/orphan, silent failure, lost saved data, or inaccessible supported UI.

Primitives: browser capture; server session and explicit lease; durable meeting; UI projection. They are separate authorities.
Invariants: CONTEXT.md ownership/lifecycle definitions and ADR-0013 persistence; no policy, thresholds, frame schema, or sentinel changes.
Unknown: headless visibility is browser-dependent; synthetic microphone input is NOT microphone fidelity evidence.
Tools: real Chromium measures UI/transport; existing local stack and real vLLM measure terminal persistence; scratch DB rows only measure history layout.

All commands run from this worktree. Set `PY` to the interpreter specified in COMMON.md.
All temporary media, browser profiles, TLS keys, SQLite state and logs stay in ignored `runs/wp5/`.
No private transcripts/audio/credentials are committed. Screenshots mask content and form fields.

```sh
mkdir -p runs/wp5
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/runs/wp5"
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -L 127.0.0.1:18105:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
# Separate terminal; own tunnel must report running/waiting=0 before loading.
openssl req -x509 -newkey rsa:2048 -nodes -keyout runs/wp5/key.pem -out runs/wp5/cert.pem -days 2 -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1
"$PY" prototypes/browser-stress/stack.py --state runs/wp5/state --cert runs/wp5/cert.pem --key runs/wp5/key.pem --port 17865 > runs/wp5/server.log 2>&1 &
echo $! > runs/wp5/server.pid
"$PY" prototypes/browser-stress/run.py all --output evidence/mvpfix/wp5/new-run
```

`run.py 1,8,9` selects cases; output must be new. Cases 10/13/14 need completed records in the SAME browser profile, so run with producing cases 1/8.
The bench launches a fresh profile on every invocation. Case 12 explicitly inserts scratch failed-meeting fixtures to reach 60 rows.
Case 14 restarts ONLY the PID written above, preserving its local SQLite/audio roots, then stops its replacement process.
Stop the original stack (if case 14 did not) and tunnel afterwards. No shared-service control.

The wrapper limits real decoder submissions to 200 across restarts and two concurrent requests. Do not reset its counter to evade the campaign budget.
The UI's actual Stop wait remains 5 seconds; the browser waits for durable completion separately. This tests the shipped UI rather than replacing its Stop request with an API request.

Read `NOTES.md` for measured verdicts and limitations. Base attempt failures remain retained; later runs never overwrite them.
