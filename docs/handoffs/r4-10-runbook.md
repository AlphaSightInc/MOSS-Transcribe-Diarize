# R4-10 master runbook — frozen, serial, budgeted

**State today: PLAN ONLY. Do not run a qualification row from this document until F0 passes.**

## Decision and structural contract

**Question.** Can the final R4 measurement be one reproducible population rather than four independently spending harnesses?

**Minimum primitives.** One frozen product SHA; harness-only execution copies; one decoder lease/proxy; an ordered ledger; and a receipt for every row.  Removing any primitive loses product custody, spending custody, or the ability to distinguish missing evidence from a product result.

**Invariants.** D29 caps all R4 decoder requests at 5,000; no more than two are in flight; only one lease holder/proxy exists at a time; D24 permits at most ten summary-provider calls; `--long` never runs; and every bundle summary retains `capacity_2x1800: REQUIRED-NOT-RUN`. Speakers stay muted; no unattended physical microphone opens.

**Falsifier.** The runbook is invalid if a row lacks a frozen product check, bounded request count, expected receipt, or reconciliation to the shared ledger. Stop rather than infer a PASS.

## F0 — frozen-SHA gate (0 decoder requests)

The current tree is **not frozen**: candidate `round4/integration` is `71f23c0c`, run B is `16fd908e`, and `terminal_label_capture.py` is absent from integration. The existing labels checkout is also dirty (`docs/verify/r4-10-labels/VERIFY-RESULT.md`). No R4-10 row is authorised from those current trees.

There is a second, narrower freeze blocker: feature harness `d8c5ab59` hard-codes `FROZEN_SHA = 71f23c0c`. It will correctly reject a later final product SHA. The feature owner must publish a **harness-only** execution revision that pins the accepted `FROZEN_SHA`; record that replacement SHA in the ledger. Do not hand-edit the copy during R4-10. Until that revision exists, do not open the shared F3 allocation: F3a/F3b are **INCOMPLETE, 0 spent**.

The lead first merges/accepts run B and the terminal-label observer, then records one `FROZEN_SHA`. The following must all succeed before any provider, proxy, stack, or browser starts:

```sh
CANDIDATE=/Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate
FROZEN_SHA=$(git -C "$CANDIDATE" rev-parse round4/integration)
test -z "$(git -C "$CANDIDATE" status --porcelain=v1)"
git -C "$CANDIDATE" merge-base --is-ancestor 16fd908e3fd4de6834c9cb0c27ac4630f9a4d146 "$FROZEN_SHA"
git -C "$CANDIDATE" merge-base --is-ancestor 1c6b0c81b0715bd2c5cb375f60a663cf3324ed0e "$FROZEN_SHA"
git -C "$CANDIDATE" cat-file -e "$FROZEN_SHA:moss_transcribe_diarize/app/terminal_label_capture.py"
RUN_ROOT=/private/tmp/moss-r4-10-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$RUN_ROOT"
git clone --no-local --single-branch --branch round4/integration "$CANDIDATE" "$RUN_ROOT/frozen-preflight"
git -C "$RUN_ROOT/frozen-preflight" checkout --detach "$FROZEN_SHA"
```

Run the product suites in `$RUN_ROOT/frozen-preflight` with the common runtime below. Retain SHA, branch, clean status, suite outputs, 17/17 asset parity, model path, manifest preflight, and `sqlite3.sqlite_version` in `$RUN_ROOT/frozen-preflight.json`. A stale branch, dirty product path, missing D27 reference/cut, absent capture module, or failed suite is **INCOMPLETE**; it spends zero requests.

Each row gets a fresh execution clone, not one of the plan clones. Construct it like this, setting `PLAN_SHA` to the recorded execution-harness SHA (the feature value is the new revision above):

```sh
git clone --no-local --single-branch --branch round4/integration "$CANDIDATE" "$RUN_ROOT/$NAME"
git -C "$RUN_ROOT/$NAME" checkout --detach "$FROZEN_SHA"
git -C "$RUN_ROOT/$NAME" checkout "$PLAN_SHA" -- "$HARNESS_PATH"
git -C "$RUN_ROOT/$NAME" diff --quiet "$FROZEN_SHA" -- moss_transcribe_diarize frontend
```

This keeps product code frozen while allowing plan harnesses: features `d8c5ab59:prototypes/feature-rows` (replace `d8c5ab59` with the required re-frozen harness revision), preterm `209052a4:prototypes/preterm-rerun`, labels `1c6b0c81:prototypes/s17-identity-rerun`, headed `9e9fa624:prototypes/headed-session`.

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
| F1 | `"$PY" prototypes/preterm-rerun/run.py --run --decoder-base-url "$DECODER_BASE" --budget 56 --port 18344 --model "$MODEL" --manifest "$MANIFEST" --out "$RUN_ROOT/preterm"` | `raw-events.jsonl`; for alternation and overlap, system/microphone each retain raw, canonical, published, corrected reference, cut geometry, and scored edits. This is the only L1 pre-terminal closure attempt. | 56 | 56 |
| F2 | `"$PY" prototypes/s17-identity-rerun/run.py --run --decoder-base-url "$DECODER_BASE" --budget 184 --port 18345 --model "$MODEL" --manifest "$MANIFEST" --out "$RUN_ROOT/s17"` | Root `terminal-labels.jsonl`, `decoder-requests.jsonl`, `run.json`; each of `single`, `gap`, `alternating` has `terminal-labels.jsonl` and `partition-receipt.json`. Capture is set only on this stack process. | 184 | 240 |
| F3a | `"$PY" tools/qualify/run.py --budget 2238 --decoder-upstream-port "$DECODER_UPSTREAM_PORT" --out "$RUN_ROOT/bundle"` | Bundle result/requests and all default gates, including `capacity_2x300`; every summary explicitly says `capacity_2x1800: REQUIRED-NOT-RUN`. Never append `--long`. | 2,238 | 2,478 |
| F3b | Against the isolated frozen `$FEATURE_BASE` and the **same F3 allocation/authority**: `"$PY" prototypes/feature-rows/run.py --base "$FEATURE_BASE" --allow-decoder --allow-provider` | `evidence/round4/features/run-*/receipts.json`, per-row `receipt.json`, browser results, URL artifacts, and summary receipt. The external-summary row is exactly 2 transcripts × 3 trials = 6 provider calls (cap 10); `workspace_row_9` remains SKIP. | 0 incremental — reconciled to F3a’s 2,238, never debited a second time | 2,478 |
| F4 | Only after the attended reference is complete: start the local-HF frozen stack below, then run its final headed-instrument command. | Runtime/provider/bootstrap/descriptor receipts plus `visible-word-headed.json`; keep source/reference custody paths. The microphone WAV is retained digital silence, not a physical microphone. | 0 (local HF) | 2,478 |

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

F3a and F3b are **one shared 2,238-request population**, per the feature plan; they are not 2,238 + another feature allocation. Before F3b, reconcile its planned decoder dispatches to F3a’s retained request IDs and ledger. If a feature action would dispatch outside that population, do not improvise a new budget: mark that action **INCOMPLETE** and stop its decoder use. The remaining D29 headroom is 2,522 requests; it is not authorisation for a new row.

## Zero-decoder work

F0, runtime/model/manifest checks, all suite and static controls, and the disabled-summary browser case 13 run with zero decoder requests; case 13 also requires zero provider posts. The external-summary row uses zero decoder requests but six capped provider calls. F4/S9 uses zero **remote** decoder requests because it loads the local HF snapshot. Do not confuse any of these with an acoustic quality PASS when their required receipt or human reference is absent.

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
| F1 |  | `209052a4` | 56 |  |  |  | 0 / 0 |  | n/a |  |  |
| F2 |  | `1c6b0c81` | 184 |  |  |  | 0 / 0 |  | n/a |  |  |
| F3a/F3b |  | feature re-freeze SHA | 2,238 shared |  |  |  | 6 /  |  | `REQUIRED-NOT-RUN` |  |  |
| F4 |  | `9e9fa624` | 0 | 0 / 0 / 0 |  | 0 | 0 / 0 |  | n/a |  |  |
