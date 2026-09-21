# R4-10 master runbook — frozen, serial, budgeted

**State today:** F1 is complete at 45 requests. F2/F3/F3s remain blocked until the
integrated ownership/capture change is accepted and a new product SHA passes F0. Do not
rerun F1 or launch another all-feature campaign.

## Decision and structural contract

**Question.** Can the final R4 measurement be one reproducible population rather than four independently spending harnesses?

**Minimum primitives.** One frozen product SHA; harness-only execution copies; one decoder lease/proxy; an ordered ledger; and a receipt for every row.  Removing any primitive loses product custody, spending custody, or the ability to distinguish missing evidence from a product result.

**Invariants.** D29 caps all R4 decoder requests at 5,000; no more than two are in flight; only one lease holder/proxy exists at a time; D24 permits at most ten summary-provider calls; `--long` never runs; and every bundle summary retains `capacity_2x1800: REQUIRED-NOT-RUN`. Speakers stay muted; no unattended physical microphone opens.

**Falsifier.** The runbook is invalid if a row lacks a frozen product check, bounded request count, expected receipt, or reconciliation to the shared ledger. Stop rather than infer a PASS.

## F0 — post-implementation freeze (0 decoder requests)

Record two identities after the integrated change lands: `PRODUCT_SHA` owns product code;
`HARNESS_SHA` may change only prototype/evidence/runbook paths. Never derive the product
freeze from the moving integration branch.

```sh
CANDIDATE=/Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate
: "${PRODUCT_SHA:?set PRODUCT_SHA to the accepted post-implementation SHA}"
HARNESS_SHA=$(git -C "$CANDIDATE" rev-parse round4/integration)
test -z "$(git -C "$CANDIDATE" status --porcelain=v1)"
git -C "$CANDIDATE" merge-base --is-ancestor 16fd908e3fd4de6834c9cb0c27ac4630f9a4d146 "$PRODUCT_SHA"
git -C "$CANDIDATE" cat-file -e "$PRODUCT_SHA:moss_transcribe_diarize/app/terminal_label_capture.py"
git -C "$CANDIDATE" diff --quiet "$PRODUCT_SHA..$HARNESS_SHA" -- moss_transcribe_diarize frontend
RUN_ROOT=/private/tmp/moss-r4-10-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$RUN_ROOT"
git clone --no-local --single-branch --branch round4/integration "$CANDIDATE" "$RUN_ROOT/frozen-preflight"
git -C "$RUN_ROOT/frozen-preflight" checkout --detach "$PRODUCT_SHA"
```

Run the product suites in `$RUN_ROOT/frozen-preflight` with the common runtime below.
Retain both SHAs, clean status, suite outputs, 17/17 asset parity, model path, manifest
preflight, and `sqlite3.sqlite_version` in `$RUN_ROOT/frozen-preflight.json`. Any failed
predicate is **INCOMPLETE** and spends zero requests.

Each row gets a fresh execution clone, not one of the plan clones. Construct it like this, setting `PLAN_SHA` to the recorded execution-harness SHA (the feature value is the new revision above):

```sh
git clone --no-local --single-branch --branch round4/integration "$CANDIDATE" "$RUN_ROOT/$NAME"
git -C "$RUN_ROOT/$NAME" checkout --detach "$PRODUCT_SHA"
git -C "$RUN_ROOT/$NAME" checkout "$PLAN_SHA" -- "$HARNESS_PATH"
git -C "$RUN_ROOT/$NAME" diff --quiet "$PRODUCT_SHA" -- moss_transcribe_diarize frontend
```

Use `npm ci --prefix frontend` in every fresh clone. Do not link another checkout's
`node_modules`; hidden host state is not a reproducible gate. Record the final harness SHA
for S17, the main bundle, the summary-only row, and headed S9 in the ledger.

## Common runtime, lease, and ledger setup (0 decoder requests)

```sh
test -d "$RUN_ROOT/frozen-preflight"
RUNTIME=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/activate
source "$RUNTIME"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
PY=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
MODEL=/Users/gao/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8
MANIFEST=/Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json
"$PY" -c 'import sqlite3; from moss_transcribe_diarize.app.phase2 import REQUIRED_SQLITE_RUNTIME; assert sqlite3.sqlite_version == REQUIRED_SQLITE_RUNTIME == "3.53.4"'
test -d "$MODEL"; "$PY" -m moss_transcribe_diarize.live_provider_preflight --manifest "$MANIFEST" --json
cd "$RUN_ROOT/frozen-preflight"
npm ci --prefix frontend
MOSS_TEST_REAL_SQLITE=1 bash prototypes/runtime/backend-suite.sh
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Create `$RUN_ROOT/results-ledger.md` from the template below before F1. Acquire the documented R4 lease only when it is `FREE`; declare one owner and one decoder proxy, pass that proxy to every remote row, record pre/post `vllm:num_requests_running|waiting = 0/0`, and release it after each row. Do not start a second tunnel/proxy. The local-HF S9 row has no remote decoder but is still sequenced after remote work.

## Ordered rows and one decoder budget

| Order | Row and exact command | Expected receipt / pass boundary | Planned remote decoder requests | Running total |
|---|---|---|---:|---:|
| F0 | Frozen gate and common setup above. | `frozen-preflight.json`; all SHA/runtime/model/manifest checks. | 0 | 0 |
| F1 | **Complete; do not rerun.** | Retained pre-terminal receipts; 45 actual requests. Two arms fail `immediate_wer` because their tail appears at Stop flush. | 45 actual | 45 actual |
| F2 | `"$PY" prototypes/s17-identity-rerun/run.py --run --decoder-base-url "$DECODER_BASE" --budget 184 --port 18345 --model "$MODEL" --manifest "$MANIFEST" --out "$RUN_ROOT/s17"` | Raw pre-normalization spans, raw→normalized mapping, partition decisions, request receipt, and per-case receipt. | 184 | 229 |
| F3 | `"$PY" tools/qualify/run.py --budget 2238 --decoder-upstream-port "$DECODER_UPSTREAM_PORT" --out "$RUN_ROOT/bundle"` | Main bundle: workspace, browser 1–16, voice bank, rename, exports, File/URL, identity, `capacity_2x300`; workspace row 9 SKIP with no provider key; `capacity_2x1800: REQUIRED-NOT-RUN`. | 2,238 | 2,467 |
| F3s | Summary-only harness against its isolated stack: 50 s + 180 s File Meetings once, then 2 transcripts × 3 provider trials. | Proxy delta exactly 3/3/0, peak ≤2; six provider attempts, cap 10; per-trial current/failed receipt. | 3 | 2,470 |
| F4 | Only after the attended reference is complete: run the local-HF headed instrument below. | Runtime/provider/bootstrap/descriptor receipts plus `visible-word-headed.json`; microphone WAV remains digital silence. | 0 remote | 2,470 |

### F4 exact local-HF stack launch (0 remote decoder requests)

Run this only in the fresh F4 execution clone after the human supplies the completed 531-row template at `$S9_COMPLETED`; it makes no external decoder/provider call. It defines the stack, WAVs, reference, receipts, and teardown explicitly.

```sh
S9_EXEC="$RUN_ROOT/s9-execution"; cd "$S9_EXEC"
S9_STATE=$(mktemp -d /private/tmp/moss-r4-s9.XXXXXX)
S9_OUT="$RUN_ROOT/s9"; mkdir -p "$S9_OUT"
S9_COMPLETED=/absolute/path/adam-180-human-confirmed-template.jsonl
ADAM_AUDIO=evidence/live-policy-sweep-20260825/corpus/interview_adam_frank_180s/audio.wav
"$PY" -c 'import json,sqlite3,sys; from moss_transcribe_diarize.app.phase2 import REQUIRED_SQLITE_RUNTIME; print(json.dumps({"python":sys.executable,"sqlite_runtime":sqlite3.sqlite_version,"required_sqlite_runtime":REQUIRED_SQLITE_RUNTIME}))' >"$S9_OUT/runtime.json"
"$PY" -m moss_transcribe_diarize.live_provider_preflight --manifest "$MANIFEST" --json >"$S9_OUT/provider-preflight.json"
cp evidence/round4/headed-session/s9-300-request-plan.json "$S9_OUT/"
ffmpeg -nostdin -hide_banner -loglevel error -i "$ADAM_AUDIO" -f lavfi -t 120 -i anullsrc=r=16000:cl=mono -filter_complex '[0:a][1:a]concat=n=2:v=0:a=1' -ac 1 -ar 16000 -c:a pcm_s16le "$S9_STATE/system-300.wav"
ffmpeg -nostdin -hide_banner -loglevel error -f lavfi -t 300 -i anullsrc=r=16000:cl=mono -ac 1 -ar 16000 -c:a pcm_s16le "$S9_STATE/microphone-300.wav"
"$PY" prototypes/headed-session/complete_s9_reference.py --completed-template "$S9_COMPLETED" --output "$S9_STATE/adam-180-confirmed-words.jsonl"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost -addext subjectAltName=DNS:localhost,IP:127.0.0.1 -keyout "$S9_STATE/key.pem" -out "$S9_STATE/cert.pem"
"$PY" -m moss_transcribe_diarize.app.phase2_web_cli --database "$S9_STATE/phase2.sqlite3" --control-socket "$S9_STATE/control.sock" --tls-certfile "$S9_STATE/cert.pem" --tls-keyfile "$S9_STATE/key.pem" --backend hf --model "$MODEL" --device cpu --dtype bf16 --file-work-root "$S9_STATE/file-work" --meeting-audio-root "$S9_STATE/meeting-audio" --live-provider-manifest "$MANIFEST" --live-helper-lease-seconds 30 --host 127.0.0.1 --port 18442 --llm-upstreams '[]' >"$S9_OUT/server.log" 2>&1 & S9_PID=$!
cleanup_s9() { if [ -n "${S9_PID:-}" ]; then kill "$S9_PID" 2>/dev/null || true; wait "$S9_PID" 2>/dev/null || true; fi; }
trap cleanup_s9 EXIT INT TERM
for S9_ATTEMPT in {1..80}; do curl -fksS -X POST -c "$S9_OUT/cookies.txt" https://127.0.0.1:18442/api/workspace/bootstrap >"$S9_OUT/bootstrap.json" && break; sleep 0.25; done
test -s "$S9_OUT/bootstrap.json"
curl -fksS -b "$S9_OUT/cookies.txt" https://127.0.0.1:18442/api/live/descriptor >"$S9_OUT/descriptor.json"
"$PY" tools/qualify/visible_word_headed.py --base https://127.0.0.1:18442 --system-wav "$S9_STATE/system-300.wav" --microphone-wav "$S9_STATE/microphone-300.wav" --reference "$S9_STATE/adam-180-confirmed-words.jsonl" --seconds 300 --output "$S9_OUT/visible-word-headed.json"
cleanup_s9; trap - EXIT INT TERM
```

If bootstrap/descriptor is not 200, any confirmed word end is null/`UNCONFIRMED`, or local-HF would fall back to a remote decoder, stop before the instrument and mark F4 **INCOMPLETE**. Retain only the listed receipts and source/reference custody paths under `$S9_OUT`, not audio or raw transcript copies.

Do not run the former all-feature F3b command. F3 already covers those surfaces. F3s is
the only distinct feature measurement and owns exactly three decoder requests. A proxy
delta other than 3/3/0, more than six provider attempts, or any duplicated browser/URL/
voice/export campaign is **INCOMPLETE**; stop instead of borrowing headroom.

## Zero-decoder work

F0, runtime/model/manifest checks, and static controls use zero decoder requests. Browser
case 13 is already in F3 and requires zero provider posts. F3s uses three decoder requests
to create its two Meetings, then six provider calls. Keep provider credentials out of F3;
F3s alone owns the official provider population. F4 uses zero **remote** requests.

## Attended or Aqua-only work — excluded from unattended rows

- Jamie snippet listening, boundary/spill adjudication.
- All 531 S9 word-end confirmations in `s9-adam-frank-180s-word-end-template.jsonl`.
- Physical microphone/system/both-source capture and echo-kit checks.
- Native hidden-tab cases 3/15: require an Aqua console session and a real `document.hidden`/`visibilitychange` observation.

Speakers remain muted throughout. Missing person, Aqua session, or completed reference makes the dependent result **UNMEASURED**, never PASS; no unattended microphone is opened.

## Stop rules

1. A row without every named receipt is **INCOMPLETE**, never PASS; retain the partial receipt and reason.
2. A budget-censored/rejected row is **INCOMPLETE**, never FAIL. Unreached later rows are UNMEASURED.
3. If ledger `accepted + completed + rejected` cannot reconcile to the decoder receipt, stop decoder work; all affected rows are INCOMPLETE.
4. At 5,000 planned or actual decoder requests, stop spending immediately. The 2×1800 row remains deferred even if headroom exists.
5. A missing `capacity_2x1800: REQUIRED-NOT-RUN`, a `--long` invocation, two concurrent lease holders/proxies, peak in-flight above two, provider calls above ten, unmuted speakers, or any unattended microphone is a runbook violation: stop and report, never convert results to PASS.

## Single results ledger template

| Order / row | Frozen SHA | Harness SHA | Planned decoder | Accepted / completed / rejected | Cumulative actual | Peak in-flight | Provider plan / actual | Required receipt paths | `capacity_2x1800` | Status (`PASS` / `FAIL` / `INCOMPLETE` / `UNMEASURED`) | Reason / next action |
|---|---|---|---:|---|---:|---:|---|---|---|---|---|
| F0 |  |  | 0 | 0 / 0 / 0 | 0 | 0 | 0 / 0 |  | n/a |  |  |
| F1 | `0de56e1a` | `209052a4` | 56 planned / 45 actual | 45 / 45 / 0 | 45 | ≤2 | 0 / 0 | retained preterm root | n/a | COMPLETE / FAIL | Stop-flush latency; do not rerun |
| F2 |  | final raw-capture harness SHA | 184 |  |  |  | 0 / 0 |  | n/a |  |  |
| F3 |  | final bundle harness SHA | 2,238 |  |  |  | bundle-owned |  | `REQUIRED-NOT-RUN` |  |  |
| F3s |  | final summary-only harness SHA | 3 |  |  |  | 6 /  |  | n/a |  |  |
| F4 |  | `9e9fa624` | 0 | 0 / 0 / 0 |  | 0 | 0 / 0 |  | n/a |  |  |

> **Pins (lead):** product `0de56e1a` (tag `round4-frozen-20260921`); harness rev `7f533f71` (product diff empty); terminal-label capture = reworked `62b29715` (the unmerged `1c6b0c81` encoded the pre-partition code).
