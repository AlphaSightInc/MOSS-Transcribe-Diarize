# Headed visible-word session probe

## Verdict — RUNNABLE-HERE (full controlled path)

The Background tmux session can run this headed path. Under the disposable CPython 3.12.12/SQLite 3.53.4 runtime, the packaged HTTPS CLI served the authenticated candidate frontend and offline Live descriptor on loopback; the repaired `headless=False` instrument then drove the same `create_phase2_app` surface to a closed/final synthetic transcript with six API and six rendered-DOM state changes. It used exactly `--mute-audio`, submitted no microphone, played no audio, used no GPU, and made **zero** remote decoder/provider requests.

This is a wiring result, not a recognition claim: the rendered five-second control uses an explicit synthetic local decoder and finalizer. The production CLI control did not submit audio or lazily load the HF model. Consequently, local-HF acoustic recognition and a real 300-second per-word score remain **UNMEASURED**, but they are not blocked by session, SQLite, CLI, TLS, frontend, or offline-provider startup.

## Structural contract

- **Question.** Can the frozen candidate stack run under its exact SQLite contract and let the repaired headed instrument observe a rendered transcript here?
- **Minimum primitives.** Exact linked SQLite runtime; packaged loopback CLI plus authenticated descriptor; a synthetic local transcript through the production live-frame API; headed DOM observations. Omitting any one confuses runtime admission, stack startup, transcript transport, or rendering.
- **Invariants.** SQLite exactly 3.53.4; `headless=False`; Chromium args only `['--mute-audio']`; loopback HTTPS; zero remote/provider requests; no microphone, playback, GPU, tunnel, or candidate-tree write.
- **Assumptions / unknowns.** The synthetic transcript establishes no ASR quality or latency. The Adam reference has 531 unconfirmed word ends until a human aligns them. The public tool accepts only exactly 300-second WAV inputs.
- **Falsifier.** This verdict is false if the linked runtime reports a version other than 3.53.4, the packaged CLI cannot return authenticated HTTP 200 descriptor, the instrument does not end `closed`/`final` with a nonempty rendered DOM measurement, or any prohibited decoder/provider/audio/GPU action occurs.
- **Tool decision.** The CLI control isolates real configuration/startup without model inference. The synthetic local control is the smallest permitted transcript source that tests the browser/API/DOM path with no remote request; a real HF run is deferred to attended S9.

## Evidence

| Check | Result | Receipt |
|---|---|---|
| A1 headed launch/DOM | PASS — Background manager, Chrome headed with only `--mute-audio`, visible loopback DOM | `evidence/round4/headed-session/browser-probe.json` |
| A2 SQLite/runtime import | PASS — runtime and required SQLite both 3.53.4 | `runtime-short-stack-supported.json` |
| A3 offline Live bundle | PASS — CPU WebRTC/WeSpeaker preflight, zero network/decoder calls | `runtime-live-provider-preflight.json` |
| A4 packaged candidate CLI | PASS — loopback HTTPS, bootstrap/root/descriptor 200, signed-in frontend | `runtime-production-cli-startup-authenticated.json` |
| A5 headed rendered transcript | PASS — 3/3 synthetic reference words final-correct in API and rendered DOM; six DOM changes; `closed`/`final` | `runtime-short-stack-supported.json` |
| A6 S9 source/reference | READY FOR ATTENDANCE — retained Adam Frank 180 s, 8 source rows, 531 unconfirmed word rows | `s9-adam-frank-180s-*.jsonl` |

The historical host-Python receipt (`short-stack-runtime-receipt.json`) remains a clean refusal at SQLite 3.50.4. It is superseded by A2–A5, not bypassed.

## R4-10 attended S9 recipe

R4-11 first completes `s9-adam-frank-180s-word-end-template.jsonl` as specified in `docs/handoffs/s9-reference-alignment-packet.md`. Every one of the 531 rows must retain its text/ID and have a human-confirmed `word_end_sec`; any null or `UNCONFIRMED` row leaves per-word S9 **UNMEASURED**. That 180-second reference is the scored speech population inside the public tool's required 300-second session; the remaining 120 seconds are declared digital silence, never invented speech. Use a separate fully aligned 300-second source only if the decision requires a 300-second speech denominator.

```sh
cd /private/tmp/moss-round4-20260920/headed-session
source /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/activate
export PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1
S9_SHA=$(git rev-parse HEAD); S9_ID=$(date -u +%Y%m%dT%H%M%SZ)
S9_STATE=$(mktemp -d /private/tmp/moss-r4-s9.XXXXXX)
S9_OUT="evidence/round4/s9/$S9_SHA/$S9_ID"; mkdir -p "$S9_OUT"
RUNTIME_PY=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
MODEL=/Users/gao/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8
MANIFEST=/Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json
ADAM_AUDIO=evidence/live-policy-sweep-20260825/corpus/interview_adam_frank_180s/audio.wav
"$RUNTIME_PY" -c 'import json,sqlite3,sys; from moss_transcribe_diarize.app.phase2 import REQUIRED_SQLITE_RUNTIME; print(json.dumps({"python":sys.executable,"sqlite_runtime":sqlite3.sqlite_version,"required_sqlite_runtime":REQUIRED_SQLITE_RUNTIME}))' >"$S9_OUT/runtime.json"
"$RUNTIME_PY" -m moss_transcribe_diarize.live_provider_preflight --manifest "$MANIFEST" --json >"$S9_OUT/provider-preflight.json"
cp evidence/round4/headed-session/s9-300-request-plan.json "$S9_OUT/s9-300-request-plan.json"
ffmpeg -nostdin -hide_banner -loglevel error -i "$ADAM_AUDIO" -f lavfi -t 120 -i anullsrc=r=16000:cl=mono -filter_complex '[0:a][1:a]concat=n=2:v=0:a=1' -ac 1 -ar 16000 -c:a pcm_s16le "$S9_STATE/system-300.wav"
ffmpeg -nostdin -hide_banner -loglevel error -f lavfi -t 300 -i anullsrc=r=16000:cl=mono -ac 1 -ar 16000 -c:a pcm_s16le "$S9_STATE/microphone-300.wav"
"$RUNTIME_PY" prototypes/headed-session/complete_s9_reference.py --completed-template "$S9_STATE/adam-180-human-confirmed-template.jsonl" --output "$S9_STATE/adam-180-confirmed-words.jsonl"
REFERENCE="$S9_STATE/adam-180-confirmed-words.jsonl"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost -addext subjectAltName=DNS:localhost,IP:127.0.0.1 -keyout "$S9_STATE/key.pem" -out "$S9_STATE/cert.pem"
"$RUNTIME_PY" -m moss_transcribe_diarize.app.phase2_web_cli --database "$S9_STATE/phase2.sqlite3" --control-socket "$S9_STATE/control.sock" --tls-certfile "$S9_STATE/cert.pem" --tls-keyfile "$S9_STATE/key.pem" --backend hf --model "$MODEL" --device cpu --dtype bf16 --file-work-root "$S9_STATE/file-work" --meeting-audio-root "$S9_STATE/meeting-audio" --live-provider-manifest "$MANIFEST" --live-helper-lease-seconds 30 --host 127.0.0.1 --port 18442 --llm-upstreams '[]' >"$S9_OUT/server.log" 2>&1 & S9_PID=$!
for S9_ATTEMPT in {1..80}; do curl -fksS -X POST -c "$S9_OUT/cookies.txt" https://127.0.0.1:18442/api/workspace/bootstrap >"$S9_OUT/bootstrap.json" && break; sleep 0.25; done
test -s "$S9_OUT/bootstrap.json"
curl -fksS -b "$S9_OUT/cookies.txt" https://127.0.0.1:18442/api/live/descriptor >"$S9_OUT/descriptor.json"
"$RUNTIME_PY" tools/qualify/visible_word_headed.py --base https://127.0.0.1:18442 --system-wav "$S9_STATE/system-300.wav" --microphone-wav "$S9_STATE/microphone-300.wav" --reference "$REFERENCE" --seconds 300 --output "$S9_OUT/visible-word-headed.json"
kill "$S9_PID"; wait "$S9_PID" || true
```

Retain `runtime.json` (interpreter + SQLite), `provider-preflight.json`, `bootstrap.json`, `descriptor.json`, `server.log`, `visible-word-headed.json`, `s9-300-request-plan.json`, source/reference custody paths, and no raw transcript/audio copies under `$S9_OUT`. Stop before the instrument command if readiness is not 200, reference confirmation is incomplete, or a local-HF load would be replaced by a remote decoder.

**Requests.** The exact local-HF recipe plans **0 remote requests**. If authorization changes to a remote decoder, reserve **383**: `ceil((300 s × 2 lanes × 0.51 measured requests/lane-second) × 1.25 UNMEASURED policy headroom) = 383`; see `s9-300-request-plan.json`. No remote request was made here.

## Validation

- Follow-on controls: A2–A5 PASS; no owned server/browser process remained.
- Product backend (runtime): `2155 passed, 5 skipped, 8 xfailed`.
- Full-root backend collection (runtime): `2268 passed, 5 skipped, 8 xfailed, 3 failed`. The three failures are archival-prototype controls outside the product suite: L15 requires its historical product SHA `9089b332…` to equal current product code, and two L2 tests require absent `harness_cache.npz`; see `runtime-backend-full-suite-final.log`.
- Frontend: `312 passed (28 files)`; typecheck and production build PASS.
