# Gemini Live fault and stress bench (throwaway tooling)

## Real runtime first-pass contract (2026-09-28)

**Structural question.** With the committed W3/growing-window runtime behind a faulting Google transport, which failures are contained within preview/window/final work, and which strand a session, lose its tape, exceed a bound, or hide the failure from the operator?

**Minimum primitives.** A pinned committed runtime snapshot, one paced public-audio session, one proxy fault interval with observed REST/WS counts, one terminal Account snapshot plus retained audio, and a per-session call/cost counter. The pinned tree separates a runtime defect from 6.3's in-progress L3 edits. A time-bounded fault interval is needed for mid-meeting recovery; a Stop-bound interval is needed for terminal failure. Every added control changes one of those conditions and does not alter the transcript API.

**Invariants.** Use only the pinned committed source; keep stack/proxy on 18520–18529 and away from other panes. Send only registered public audio/generated signals. Pace at 1.0x. A proxy decision must be logged and counted before any claim of fault coverage. For every run record frames, tape duration, finalization state, DOM/poll visibility, engine calls/errors/retries/anomalies/cost, and process resource samples. The cumulative new provider spend stays below $6 including retries. An absent witness is `UNMEASURED`, not a pass.

**Assumptions and unknowns.** c58595da is the newest 6.3-reported green committed source and includes W3; current 6.3 checkout is dirty with L3 edits, so source must be isolated. REST ordinal 1 may hit preview/window/final unpredictably; targeted phase faults need an observed request boundary. Live preview usage may be estimated, so cost is an upper-bound accounting input rather than a provider invoice. Runtime throughput and total scenario cost are unknown until a short calibrated run. A failed terminal attempt may not immediately imply `failed`; the public finalization state and lead-corrected duration-specific Stop bound decide. L3 dual-lane behavior is not yet committed, so this first pass exercises the selected committed source without claiming lane qualification.

**Falsifier.** A short real paced run with proxy sees no REST or WS traffic, exceeds the spend projection, or lacks engine counters/tape/status; stop the campaign and repair the harness path. A mid-meeting outage that recovers without observed fault counts is not evidence. A terminal failure left `running` after the deadline, an accepted-frame/tape duration gap over 1 s, an unbounded sampled queue, or a crashed stack is a product defect. A short local no-provider phase-injection prototype must show the planned on/off or Stop-bound transition before provider runs.

**Tool decision.** A `git archive` of c58595da in temporary runtime state prevents dirty-tree imports without mutating 6.3's checkout; the existing runtime venv and public manifest supply installed dependencies. Run the existing proxy/runner first on a short stop-early probe, inspect actual counters and proxy counts, then choose scenario order and duration from measured cost. Extend only the proxy/runner seam needed to place outage intervals at mid-meeting and Stop, using a no-provider local prototype before real calls. The scorecard consumes retained summaries; it does not infer a PASS from a started process or a fault plan alone.

**No-provider outage prototype and verdict.** A compressed audio-clock probe emitted exactly `mid_on` at 2.0 s, `mid_off` at 3.0 s, and `stop_on` just before the 4.0-s Stop action (`evidence/P64/phase-prototype.json`). More materially, an owned proxy on 18521 in front of a local HTTP server on 18522 returned 200, was killed, then yielded actual `ECONNREFUSED`, and returned 200 after restart; zero provider calls (`evidence/P64/proxy-outage-process-prototype.json`). Thus process death/restart can witness a true provider-connection outage and recovery without changing the product stack. This is the selected seam for 60-s mid-meeting and Stop-bound outages. The short probe does not establish product behavior.

The implemented `OutageWindow` was then exercised on a separate owned 18521 proxy while the real stack continued using 18520: `activate(audio_s=2.0)` confirmed refusal, the compressed timer recovered, and `close()` reported `{refusal_confirmed:true,recovered:true,error_type:null}`. The test killed only the prototype proxy after completion. This checks the actual runner controller without a Google call; the full 60-s product outage remains to run.

The terminal expectation reducer was checked with an exact-shape synthetic session: Stop `failed` in 10 s with four live/final rows and confirmed outage/recovery passed; changing it to `running` with zero rows failed. A WS fault with a rolling call and four rows passed the row-survival check. These establish that the new fault verdicts distinguish the required public failure states; real-session verdicts remain pending.

## Structural contract

**Question:** When Google delays, fails, or disconnects, does the local live session keep captured audio, bound its work, show a recoverable or terminal state, and finish Stop within its deadline? Can two concurrent sessions do this without admitting a third?

**Minimum primitives:** (1) one local TLS endpoint that passes REST bytes and Live WebSocket messages to Google; (2) an explicit fault decision per request/connection, recorded before effects; (3) paced two-lane fixture frames through the unchanged production HTTP API; (4) snapshots, browser DOM observations, server-process samples, saved-audio duration, and Gemini accounting; (5) an expectation reducer that writes pass/fail or `UNMEASURED` for each invariant. The proxy is a transport boundary, not a model. The driver is an audio clock, not a scorer. Each observation has a distinct failure it can reveal.

**Invariants:** Only public `common/corpus.py` audio or generated silence/music leaves the bench. Fault decisions do not modify a pass-through body or WebSocket message. Faults affect only a chosen REST request or Live connection, on loopback ports 18520–18529. The driver paces at 1.0x, retains sent-frame counts, and stops/aborts each created session. A failed Google operation may reduce transcript quality, but must not strand the local finalization state or lose retained audio. Counts and costs use call denominators; missing runtime diagnostics remain `UNMEASURED`.

**Assumptions/unknowns:** The branch `gemini/runtime` was unavailable for the initial stub run. The current registered `long60` is a 2,586-second complete-reference public Lex concatenation with five true speakers; `concurrent2` and each `faults-*` use 5-minute public clips. `silence10` is 10 minutes, `music5` is 5 minutes, `manyspk` is the public synthetic K=6 10-minute meeting, and `stop-early` is 5 seconds. The supported browser capture source is represented by the production session frame HTTP API (the earlier E2E harness source does not inject fake media). The saved meeting's `audio.duration_ms` is the current retained-MP3 witness; the exact Gemini runtime representation and its counter export are unknown. A 1-second duration tolerance is provisional and will be checked on the stub path before it becomes a gate.

**Falsifier:** In pass-through mode, three public, uncached direct-versus-proxy Gemini Transcribe calls differ in parsed words or normalized token usage (provider-generated request IDs and modality-list order excluded), or a Live connection cannot route through the same SDK `base_url`; then the proxy is unfit for product stress. In a loopback stub session, a 5-second Stop or 5-minute paced stream lacks a saved-audio duration, terminal state, or bounded queue observation; then the scenario runner is unfit. A runtime fault that crashes, hangs, drops retained audio, exceeds queue bound, or hides status falsifies the runtime claim rather than the harness.

**Tool decisions:** `google-genai==2.25.0` source shows `HttpOptions(base_url=...)` joins REST paths and constructs the Live `wss://.../ws/google.ai.generativelanguage...BidiGenerateContent` URI from the same host with an API key. This requires a local HTTPS/WSS endpoint and a trusted local test certificate; a plain HTTP listener cannot prove both. Use installed Starlette/Uvicorn, httpx, and websockets for one loopback endpoint rather than add a package. Use explicit JSON schedules and seeded per-kind probabilities so fault choices can be replayed. A local deterministic upstream first proves byte transparency without provider variability. Three short public real calls then test SDK routing and output parity within the $2 cap. The loopback MOSS stack tests session/retained-audio plumbing with no provider calls. Long/fault scenarios against Gemini runtime wait for the lead's availability notice.

## Expected outcomes

| Scenario | Main falsifiable expectations | Planned witness |
| --- | --- | --- |
| `long60` | 2,586 s paced; process survives; work queue never exceeds descriptor limit; retained audio covers sent duration; terminal finalization; word/label latency, RSS/CPU/fds/cost/reconnect timeline | frame ACKs, snapshots, DOM, saved `audio.duration_ms`, process samples, engine counters |
| `concurrent2` | Two sessions active together; third create returns 409 `live_capacity_full`; both finish independently without lost audio | three create responses; per-session frames, snapshots, audio |
| `faults-*` | Injected fault observed; server lives; queue bounded; audio complete; visible status or explicit failure; no `running` finalization after Stop deadline | proxy fault log; process/poll/DOM; saved audio and terminal snapshot |
| `silence10`, `music5`, `overlap`, `manyspk` | 1.0x input reaches server and closes; duration/queue/status accounting; no invented quality threshold | generated/public PCM, ACKs, snapshots, saved audio |
| `stop-early`, `abort-mid` | Stop/abort is bounded and visible; audio retained or explicitly unavailable with reason; no stuck session | terminal snapshot, saved meeting and audio state |

## Measurements and current verdict

**Proxy transport PASS.** Deterministic local upstream: 3/3 REST bodies byte-identical and 1/1 WebSocket message identical in pass-through; 14/14 scheduled faults observed, including real REST and WS transport resets. Per-kind probability 1.0 selected 50/50 REST 503 and 50/50 WS 1011 faults, with 100 logged rows. Heavy-tail draw probe: n=1,000 at 0.2 s base, 5 s cap, p50 0.302 s, p95 1.54 s, 7 capped. Receipts: `evidence/P64/proxy-local-probe-reset2.json`, `proxy-probability-probe.json`, `proxy-heavy-tail.json`.

**Real SDK routing PASS, cost $0.001414 batch total.** Three uncached public 4-second direct/proxy pairs (6 calls): parsed words identical 3/3, normalized modality counts/usage identical 3/3, 0 clamped and 0 dropped per call; raw `input_tokens_by_modality` list order differed 2/3. Each call cost $0.000202, six-call subtotal $0.001212. The additional environment-route probe made one 4-second call costing $0.000202 and one Live setup with 0 audio; proxy counted REST 1 and WS 1. Live setup usage is `UNMEASURED`. Receipts: `proxy-google-probe.json`, `proxy-env-route.json`; shared ledger P64 has seven provider calls. Public accept6 audio was used for word parity only, with no WER/DER scoring or reference comparison. The later H1 #3 reference update does not alter this receipt.

| Public 4-second call | Route | Words | Clamped/call | Dropped/call | Billed USD |
| --- | --- | ---: | ---: | ---: | ---: |
| Bill Ackman | direct | 10 | 0 | 0 | 0.000202 |
| Bill Ackman | explicit proxy | 10 | 0 | 0 | 0.000202 |
| Keyu Jin | direct | 10 | 0 | 0 | 0.000202 |
| Keyu Jin | explicit proxy | 10 | 0 | 0 | 0.000202 |
| Javier Milei | direct | 6 | 0 | 0 | 0.000202 |
| Javier Milei | explicit proxy | 6 | 0 | 0 | 0.000202 |
| Bill Ackman | environment proxy | 10 | 0 | 0 | 0.000202 |

Live setup: one WS connection, zero audio sent; clamped/dropped per-call rates and usage `UNMEASURED` for that setup. The table denominator is seven successful REST calls; aggregate clamped/call = 0/7 and dropped/call = 0/7.

**Stub session plumbing PASS at tested durations.** Full `stop-early`: 5.0 s/10 frames per lane, 5.0 s retained MP3, final/closed, maximum observed queue 2/16, 5 DOM samples. Full `concurrent2`: two 300-second sessions, each 600/600 frames per lane accepted and 300.0/300.0 s retained MP3, final/closed in 1.742/2.294 s after Stop; third create 409 `live_capacity_full`. Queue maximum 2/16; 299 DOM samples each, 297/298 polls, maximum sender lag 0.189/0.208 s. Across 61 process samples, peak RSS 813,616 KiB, CPU 103.7%, open fds 252; per-session p90 poll latency 8.254/8.269 ms and maximum snapshot size 45,801/45,152 bytes. Short `abort-mid`: 5.0 s retained, aborted. Short `silence10`: 5.0 s generated zero signal retained and terminal. Short runs are `PLUMBING_PASS`, not full named stress qualification. Receipt `evidence/P64/stress-concurrent2-full1/summary.json`. Stub engine counters and anomaly rates are `UNMEASURED`.

**Account counter seam verified by source inspection, not runtime execution.** Current runtime `GeminiLiveSnapshot.to_dict()` adds `engine_diagnostics`; `/api/live/sessions/{id}/snapshot` returns `view.visible.to_dict()` without stripping it. Runner records the field every poll and at terminal snapshot. It reports call-kind counts, error/retry codes, clamped/dropped totals and per-call rates, cost, sent provider audio, degraded-path activations, and window/preview lag. Exact-shape counter reducer check: 3 calls with 2/1 clamped/dropped yields 0.666667/0.333333 per call. Missing stub diagnostics stay `UNMEASURED`. Current phase-2 placeholder engine uses REST Transcribe; a Live WS words-source verdict is open. WS runtime fault status is `PENDING_WORDS_SOURCE` until Live is selected, then mandatory with `--words-source live`. WS proxy transport has been tested independently with local messages and a real SDK Live setup.

**Initial phase decision gate (historical; timing bound superseded below):** Local proxy and runner are ready for a later, lead-authorized Gemini runtime run. Long60 and full fault outcomes are `UNMEASURED` here. A runtime scenario fails if `engine_diagnostics` is absent from its terminal Account snapshot; the stub is exempt and reports engine numbers `UNMEASURED`. Sampled queue bounds mean 1-second snapshots can miss a shorter excursion; the descriptor bound and sender ACKs remain separate witnesses. The initial provisional Stop gate was terminal within 35 seconds from action start; the lead replaced it with 60 seconds plus 5% of sent duration, and and retained MP3 duration must be within 1 second of accepted system-lane duration. A failed injected request may still recover to `final`; `failed` and `unavailable` are also valid terminal finalization states.

## One-command local reproduction

From the Gemini-live worktree root, using its sibling venv:

```bash
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/stress/probe_proxy.py --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/proxy-local-new.json
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/stress/scenarios.py --scenario stop-early --launch-stub --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/stress-stop-early-new
```

The real short proxy probe is already complete; repeat only with an approved new spend:

```bash
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/stress/probe_google.py --env-route-only --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/proxy-env-route-new.json
```

## Later lead commands: Gemini runtime

Run only after the lead releases the runtime for phase 2. All ports below belong to P64; the runtime branch helper script uses P63 ports and is not used here. The proxy process must be started **without** `SSL_CERT_FILE` set to our temporary certificate, so its Google-facing client retains normal public CA trust. Set the two variables only on the product stack command; the SDK reads them at client creation for both REST and Live.

```bash
RT=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-runtime
BENCH=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live/prototypes/gemini-live/stress
EVID=/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64
STATE=$(mktemp -d "${TMPDIR:-/tmp}/p64-runtime.XXXXXX")
chmod 700 "$STATE"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1' -keyout "$STATE/key.pem" -out "$STATE/cert.pem" >/dev/null 2>&1
chmod 600 "$STATE/key.pem"
mkdir -p "$STATE/file-work" "$STATE/meeting-audio"
"$RT.venv/bin/python" "$BENCH/gemini_fault_proxy.py" --port 18520 --cert "$STATE/cert.pem" --key "$STATE/key.pem" --log "$EVID/runtime-faults.jsonl" >"$STATE/proxy.log" 2>&1 &
PROXY_PID=$!
cd "$RT"
MOSS_OPEN_WORKSPACE=1 PYTHONDONTWRITEBYTECODE=1 GOOGLE_GEMINI_BASE_URL=https://127.0.0.1:18520 SSL_CERT_FILE="$STATE/cert.pem" "$RT.venv/bin/python" -m moss_transcribe_diarize.app.phase2_web_cli --database "$STATE/phase2.sqlite" --control-socket "$STATE/control.sock" --tls-certfile "$STATE/cert.pem" --tls-keyfile "$STATE/key.pem" --file-work-root "$STATE/file-work" --meeting-audio-root "$STATE/meeting-audio" --live-provider-manifest "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json" --live-helper-lease-seconds 30 --live-engine gemini --host 127.0.0.1 --port 18524 >"$STATE/stack.log" 2>&1 &
STACK_PID=$!
```

Run each non-fault scenario, then each reachable REST fault. Every iteration writes a fresh summary and content-free timelines. `overlap` creates two simultaneous 300-second sessions, one per relative RMS ratio (0 dB and -10 dB). `concurrent2` creates two simultaneous full 300-second sessions and checks the third create. `long60` uses the registered 2,586-second complete-reference Lex concatenation; this stress runner checks transport and session behavior, not word-error or diarization accuracy. All 5-minute inputs use the three complete `lex_*` references, although this runner does not score WER/DER.

```bash
for SCENARIO in long60 concurrent2 silence10 music5 overlap manyspk stop-early abort-mid; do
  "$RT.venv/bin/python" "$BENCH/scenarios.py" --scenario "$SCENARIO" --base-url https://127.0.0.1:18524 --server-pid "$STACK_PID" --out "$EVID/runtime-$SCENARIO-$(date +%s)"
done
for FAULT in http_429 http_500 http_503 latency_fixed latency_heavy_tail connection_reset response_truncate malformed_json stall; do
  "$RT.venv/bin/python" "$BENCH/scenarios.py" --scenario "faults-$FAULT" --base-url https://127.0.0.1:18524 --proxy-url https://127.0.0.1:18520 --server-pid "$STACK_PID" --out "$EVID/runtime-faults-$FAULT-$(date +%s)"
done
```

The current product runtime makes no Live WS requests. These five commands remain runnable and report `PENDING_WORDS_SOURCE` if no WS injection occurs and the other session checks pass. If the Live words source wins, add `--words-source live`; a missing WS injection then fails. The proxy's WebSocket fault handling was already tested independently.

```bash
for FAULT in ws_close_1011 ws_close_1007 ws_goaway ws_connection_reset ws_stall; do
  "$RT.venv/bin/python" "$BENCH/scenarios.py" --scenario "faults-$FAULT" --base-url https://127.0.0.1:18524 --proxy-url https://127.0.0.1:18520 --server-pid "$STACK_PID" --out "$EVID/runtime-faults-$FAULT-$(date +%s)"
done
```

Test refusal last. `--down` deliberately leaves port 18520 unbound. The runner requires an actual connection refusal and a runtime error counter before it can pass.

```bash
kill "$PROXY_PID"; wait "$PROXY_PID" 2>/dev/null || true
"$RT.venv/bin/python" "$BENCH/gemini_fault_proxy.py" --down --port 18520 --cert "$STATE/cert.pem" --key "$STATE/key.pem" --log "$EVID/runtime-faults.jsonl" >"$STATE/proxy-down.log" 2>&1 &
PROXY_PID=$!
"$RT.venv/bin/python" "$BENCH/scenarios.py" --scenario faults-google_down --base-url https://127.0.0.1:18524 --proxy-url https://127.0.0.1:18520 --server-pid "$STACK_PID" --out "$EVID/runtime-faults-google_down-$(date +%s)"
kill "$STACK_PID" "$PROXY_PID"; wait "$STACK_PID" "$PROXY_PID" 2>/dev/null || true
```

Inspect `summary.json` for each named scenario. A result from the loopback stub or a shortened `--seconds` run is never a product-runtime verdict.

## Real committed runtime first pass (c58595da)

The product stack imports a clean `git archive` of c58595da, with `GOOGLE_GEMINI_BASE_URL=https://127.0.0.1:18520` and the proxy certificate trusted by `SSL_CERT_FILE`; the 6.3 worktree's uncommitted L3 files are outside this source. Proxy REST and Live WS routes were both observed. Full `stop-early` and `concurrent2` passed; the latter retained both 300-second MP3s and rejected a third create with `409 live_capacity_full`. Full REST 429 burst5 passed with 5 proxy injections, 33 runtime calls, 1 reported 429 error/retry, and 1/33 clamped, 0/33 dropped words. Short REST 503 and WS close1011 runs are plumbing evidence only. The 503 injected wire attempt was hidden by SDK retries from runtime error/retry counters; see the status `DEFECT:` line and the pinned SDK `_gaos` transport.

The registered `long60` fixture at corpus commit 581ce7e6 is 2,586.0 seconds with complete reference and five true speakers. Full paced run accepted 5,172/5,172 frames per lane, maintained sampled queue at 1/16, published rolling windows, and recovered four natural Live `go_away` events (5 preview calls). At the runner cutoff 76.553 seconds after Stop, finalization was still `running`, saved meeting `active`, and retained MP3 duration unavailable. The old runner marked **FAIL** under its superseded 35-second gate. It later reached `final` and saved an exact 2,586-second MP3; the corrected 189.3-second bound cannot be adjudicated from this early cutoff receipt. The runner cutoff counters were 264 calls, 4 clamped/264=.015152 and 1 dropped/264=.003788, 4 `go_away` errors/retries, and $0.604685; eventual terminal calls raised cost to $0.735155. Peak sampled RSS was 2,333,648 KiB during the late final pass (steady capture around 0.97 GiB), CPU 97.1%, open fds 236, and snapshot size 157,141 bytes. Poll p90 was 12.608 ms. First text p90 by minute stayed below 0.849 s; named-label p90 reached 13.302 s. Word/label latency is a visibility measure here, not an identity accuracy claim. Receipts: `evidence/P64/runtime-c585-long60-1/{summary.json,eventual-snapshot.json,eventual-saved-meeting.json}`; no WER or DER verdict is made from this stress run.

### Lead Stop-bound correction and prototype

Lead triage replaces the provisional 35-second Stop gate with `60 seconds + 5% of sent audio duration`, requiring an eventual terminal state rather than a persistent `running` state. A read-only reducer prototype over real receipts printed bounds of 75.0 s for 300 s, 90.0 s for 600 s, 90.2 s for the padded 604 s K6 fixture, and 189.3 s for registered 2,586 s long60. Concurrent2 (31.592/30.528 s), manyspk (55.061 s), and REST503 (26.744 s) are within their corrected bounds. Long60 and silence10 were still `running` when the old runner stopped at 76.553/75.973 s, so their corrected within-bound verdicts are **UNMEASURED from those cutoff receipts**; eventual snapshots prove completion and tape retention but lack an exact Stop-to-terminal elapsed time. The earlier `DEFECT:` lines for Stop timing are reclassified as metrics and superseded; the original receipts remain unchanged. The next pinned runtime runs must poll through the corrected duration-specific bound. Music-only `"2"` is a documented content limitation, not a new runtime defect. Hidden SDK retries remain a real telemetry defect (S-1). This prototype tests the exact pass/fail boundary and exposes why merely changing the scalar comparator would still stop observation too early.
