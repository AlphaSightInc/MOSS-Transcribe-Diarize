# Concurrency prototype notes

## W2 lifecycle fairness repair — 2026-08-19

**VERDICT: PASS for the measurement rule; the iteration-27 `skew=30` is not a
scheduler finding.**

Question: did the tunnel matrix establish unfair dispatch, or did its
`canonical_processed`-only metric count VAD-dependent work after another session
had stopped being ready?

The prior log carried only publication events. Its two sessions completed 46 and
76 items, so the all-completions prefix calculation reported 30 despite no record
of which sessions were eligible when each item was selected. That cannot measure
the preregistered condition, which is explicitly limited to *continuously ready*
sessions. The production-route instrument now writes the compact, ordered
`canonical_queued` -> `canonical_started` -> `canonical_processed` lifecycle.
The evaluator fails closed if any stage is missing and evaluates pairwise skew only
inside a continuous jointly-ready interval.

The focused regression has two falsifiable traces: a fair alternation followed by
two peer-only items still passes at skew 1, while selecting the same session twice
while its peer remains queued fails at skew 2. This changes no gate value, matrix
row, duration, or model claim. It requires a fresh tunnel matrix; iteration 27
remains useful latency/backpressure evidence, but its old fairness number cannot
select a concurrency bound.

## Remote-vLLM tunnel matrix contract — 2026-08-18

**VERDICT: FROZEN before measurement; no W2, G4, or G5 result yet.**

Question: can the local production live routes use the already-proven read-only remote-vLLM seam
for the 1/2/4/8 matrix and selected 600-second soak without silently carrying over CPU/HF claims?

The one-command contract check prints every field and its SHA-256:

```bash
python3 prototypes/streaming-diarization/concurrency/validate_remote_vllm_tunnel_preregistration.py
```

The next runner must re-finalize a new evidence-owned manifest to its captured `HEAD`, derive all
geometry/calibration from the descriptor and provisional manifest, and refuse a preflight or closing
endpoint failure. It must record the contract/fixture/manifest hashes and the selected-model catalog
identity before and after the run. Its p95 is explicitly tunnel-inclusive; it cannot claim isolated-GPU
latency, GPU memory/utilisation/OOM, or vLLM active/queued counts. The 90-second source repeats in a
600-second soak, so the verdict must state that timing limit.

## Remote-vLLM tunnel matrix runner — 2026-08-18

**VERDICT: IMPLEMENTED, NOT YET MEASURED.**

`run_remote_vllm_tunnel_measurement.py` is a narrow W2 runner for the frozen contract. Its preflight
rejects an unhealthy tunnel, a missing selected model, a malformed or credential-bearing endpoint URL, missing
fixture/provisional inputs, and a malformed deployed descriptor before it starts any local route process. It
captures `HEAD` once, finalizes an ephemeral execution manifest outside the repository, materializes declared
relative assets only beside that temporary manifest, and copies only the finalized manifest plus asset hashes
to `OUTPUT`. It asks the production manifest reader to admit the execution bundle and refuses if the local
descriptor does not carry that exact revision or deployed geometry. This avoids committing or retaining the
79 MB ONNX asset in evidence while retaining the exact admitted manifest and hashes.

Iteration 26 repaired the first live attempt's relative-asset locality failure. The focused command
`.venv/bin/python -m pytest -q tests/test_remote_vllm_tunnel_measurement.py` passes **5/5**. Its new
counterfactual calls the real `LiveProviderBundleConfig.preflight()` before materialization and observes both
`identity-state` and `golden-input` absent; after materializing to a disposable execution directory it proves
neither absence failure remains. The intentionally minimal test manifest remains otherwise inadmissible, so
this is an asset-resolution proof only, not a replacement for the next real-bundle preflight or W2 matrix.

The runner uses the existing production local-route/vLLM seam, but gives every session a background helper
heartbeat at `lease / 4`, so a blocked remote transcription cannot make helper presence disappear. It records
the endpoint's canonical `/models` hash before and after the run, and a failed closing probe makes its verdict
non-qualifying rather than interpreting endpoint loss as slow inference. The runner has not selected a bound or
produced a G4/G5 result; its planned 90-second speech fixture repeats during a possible 600-second soak.

## Remote-vLLM local-route seam — 2026-08-18

**VERDICT: PASS for the route/decoder seam; explicitly NON-GATING for W2, G4, and G5.**

Question: can one loopback production live-route runtime send a real canonical decode to the
read-only remote vLLM endpoint without selecting a local HF model, while retaining helper presence
through the remote request and stopping cleanly?

One command (prints full state and writes the compact artifact):

```bash
.venv/bin/python prototypes/streaming-diarization/concurrency/proto_remote_vllm_route_seam.py \
  --manifest "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json" \
  --vllm-base-url http://127.0.0.1:18000/v1 \
  --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize \
  --live-helper-lease-seconds 30 \
  --output evidence/phase1/w2-local-concurrency/iteration-22-remote-vllm-route-seam-replay.json
```

The probe first rejected an insufficient general rule: one descriptor hard-cap (five frame pairs)
produced no canonical event in 120 seconds. It now submits two descriptor-derived hard-cap windows
(ten frame pairs), because the VAD must observe audio beyond a full span boundary before it may close
that span. No sample count is hard-coded. On the replay, `/v1/models`, bootstrap, session create,
all 20 frame posts, canonical event polling, and stop returned HTTP 200; one 40,000-sample canonical
result arrived. The helper heartbeat cadence is derived as one quarter of the explicit lease, not a
new timing threshold.

The artifact records `manifest_matches_head: false`: the available local manifest names
`cc8f778a...`, not the then-HEAD `53c63cb...`. It also has no GPU memory, utilisation, OOM/error,
or vLLM active/queued telemetry. Therefore it proves only the missing local-route-to-remote-vLLM
seam. A real W2 runner must re-finalize a run-owned manifest for its exact HEAD, preserve the frozen
1/2/4/8 matrix and its hashes, and keep all GPU-only metrics explicitly unclaimed.

## CPU/HF-local gate preregistration — 2026-08-18

**VERDICT: FROZEN, NOT RUN — a separately hash-pinned contract for the now-available local HF path.**

Question: at the descriptor geometry observed on the read-only deployed host, can one local CPU/HF
service sustain the measured one-to-eight-session screening matrix and selected 600-second bound while retaining fair,
session-local v2 backpressure and no cross-session text across overload and observer reconnect?

`cpu_hf_local_preregistration.json` is intentionally separate from the 2026-08-13 vLLM profile:
the old file remains the historical record for its controlled prototype, while this one freezes the
CPU/HF-local run before any result exists. Its validator prints the full contract and SHA-256 in one
command. The runner must use the real decoder, real human speech at wall-clock cadence, one local
service process, and descriptor-derived geometry; controlled collaborators cannot qualify it.

Frozen gates: per-session p95 transcript lag at most 10.0 s using linear Type-7; local process-tree
RSS growth at most 4 GiB from warmed idle; zero OOM/accelerator errors; continuously ready dispatch
skew at most one; retryable non-terminal v2 429 for a saturated session while its peer continues;
and marker isolation through overload plus observer reconnect. Raw arrays, not summaries, are
required. The CPU/HF-local latency column must always read **"CPU HF local decode, not the deployed
GPU bound"**. This profile explicitly cannot prove deployed GPU p95 latency, GPU memory, or GPU
utilisation.

The 10.0 s latency ceiling is intentionally wide headroom carried from ticket #3: four concurrent
CPU/HF sessions over a ten-minute soak are unmeasured, so lowering it based on the prior short run
would be post-hoc optimism. It is not a tight performance claim. The final verdict must report its
maximum per-session p95 beside the prior two-session CPU observation (0.248 s p95) and state the
headroom. Likewise, 4 GiB is a safety ceiling for the unmeasured soak; **zero OOM or accelerator
errors** is the tight memory criterion.

### W2 pre-measurement matrix correction — 2026-08-18

**VERDICT: RE-FROZEN, NOT RUN.** Before any CPU/HF result, the ticket-3 acceptance criteria were
rechecked. Its required reporting rows are 1/2/4/8 concurrent meetings, not only 2/4. The frozen
matrix therefore records all four short screens and keeps the one 600-second soak only for the largest
screening pass. An 8-session CPU failure is a useful recorded outcome; omitting the row is not.

The new profile also makes the boundary explicit: it records local CPU/HF decode real-time factor and
local process errors, but cannot establish deployed real-time factor, GPU OOM/accelerator errors, or
the vLLM active/queued series. The runner preserves those distinctions in its verdict.

The canonical dispatch event writer is deliberately off the runtime publication path: it serializes
the complete record after the publication lock, sends it to a dedicated writer thread, and syncs that
file every five seconds plus shutdown. Its cumulative enqueue, write, sync, and pending-record figures
are retained with every measurement phase, so the artifact exposes observer overhead.

### Unexpected-frame evidence compaction — 2026-08-18

**VERDICT: PASS — absorbed into the runner before the tunnel-backed W2 run.**

Question: can failure evidence retain counts and request/response diagnostics without retaining PCM
or one full result per repeat? The throwaway prototype ran against
`run-20260818T213600/run-state.json`: 1,584 failures contained 36,356,544 base64-PCM bytes inside the
59,992,997-byte artifact. They collapsed into two `(http_status, error_code, lane)` buckets:
`(429, canonical_queue_full, microphone)=1,464` and `(429, canonical_queue_full, system)=120`.

The absorbed runner records the total and every bucket count, plus the first and last three exemplars
per bucket. Each exemplar retains session ID, sequence, device epoch, timing/shape metadata, HTTP
status, typed error, retryability, bounded failure detail, PCM byte length, and a 16-character SHA-256
prefix. It never serializes `pcm_base64`; predicate-bearing latency, dispatch, RSS, queue-depth, and
429 arrays remain untouched.

### Historical CPU/HF artifact migration — 2026-08-18

**VERDICT: PASS — compacted diagnostic evidence, still non-gating.**

Question: can the already-committed 59,992,997-byte CPU/HF `run-state.json` be made reviewable without
changing any predicate-bearing result? The source is pinned as SHA-256
`a28f57e5b5266c429bb1df106417ee6448fed58fb94180c207788e5b4d8986dd`. Its legacy failure records did
not carry a root `session_id`; their final response snapshot did. The migration therefore derives the
exemplar ID only from `attempted[-1].response.json.snapshot.session_id`, after checking it exists on all
1,584 records. It then applies the absorbed runner's bucketing semantics.

The compacted artifact is 288,007 bytes (SHA-256
`996559a4912e1ab054adfebfd5fa137076744c8092474f672e924a0689d08bcb`). It retains the exact source
projection SHA-256 `3c8eaa6a557f3d40292c2a8456fe1289726929aa6921765b53a29b0a69b8e9d2`, all per-screen failure
counts, and only first/last-three safe exemplars per bucket. The regression rejects raw PCM, a changed
bucket total, absent exemplar session ID, a file at or above 1 MB, or any changed non-failure predicate.
This is artifact hygiene only: the CPU/HF result remains explicitly non-gating and cannot be reused for
G4/G5.

## Gate preregistration — 2026-08-13

**VERDICT: PASS — numeric gates and measurement semantics frozen before measurement.**

Machine-readable preregistration SHA-256:
`b6fbe1f5dc60c0f0a20128026eefa8bc369a456927fe267cf94aa2a8b2865d52`.

- Latency: maximum per-session p95 transcript lag must be at most `10.0 s` (linear Type-7).
- Memory: vLLM GPU-cache usage must stay at or below `0.95`; locally-started service and inference
  process-tree RSS may grow at most `4 GiB` above warmed idle; OOM/accelerator errors must be zero.
- Fairness: continuously ready sessions may differ by at most one completed dispatch.
- Selection: choose the largest of `1, 2, 4` that passes its same-count run and a 600-second soak.
  The eight-meeting run is overload evidence, not a relaxed normal-load latency gate.

Lag is measured from the real-time replay clock at a span's `end_sample` until the observer receives
the matching production `canonical_processed` event. This intentionally includes the 250 ms poll
interval. Queue depth is sampled per session. Raw vLLM active/queued series are mandatory; a missing
series does not become zero.

Host capability inspection found an Apple M3 Ultra with 256 GiB unified memory and usable Torch MPS,
but no local `vllm` executable/module, no cached MOSS model, and no responding local MOSS endpoint.
The running LM Studio endpoint advertises unrelated models. Therefore this preregistration passes,
but a real qualifying measurement remains unavailable until a local MOSS/vLLM path exists. A later
stub run may measure dispatcher mechanics only and cannot satisfy G4/G5.

## Controlled scheduler probe — 2026-08-13

**VERDICT: PARTIAL — fairness, marker isolation, and per-session capacity pass; required
non-terminal 429 semantics fail. This run does not qualify G4 or G5.**

`proto_controlled_dispatcher.py` replayed the hash-pinned 59.584 s human-speech fixture in real
0.5 s wall-clock frames through `LiveServiceRuntime` and its production round-robin drain. Decode,
identity, speech observations, and scheduler release were controlled, and no vLLM metrics existed.

- At 1, 2, 4, and 8 meetings, every session completed four dispatches. Maximum prefix dispatch
  skew was respectively `0, 1, 1, 1`, within the frozen `<=1` fairness gate.
- All session markers remained isolated, including a replacement runtime session. This does not
  exercise HTTP reconnect or resumable transport.
- Holding decode filled one session to exactly 16 pending items while its peer still accepted a
  frame, proving the queue instance and capacity are session-local on this path.
- The first overflow raised raw `InferenceArbiterBackpressure` and marked the saturated session
  terminal. Only the following retry raised typed transport pacing that maps to HTTP 429. Therefore
  this path does not yet provide the required first-response, non-terminal 429 behavior.

Raw result: `evidence/phase1/t3/iteration-4-controlled-dispatcher.json`.

Iteration 5 repaired the production v2 HTTP path exposed by this historical run. Canonical-queue
capacity is now checked under the per-session runtime lock before mono admission: the first refusal
is a retryable typed 429, leaves the mono session non-terminal and unconsumed, does not block a peer,
and an identical retained-v2-frame retry succeeds after one dispatch frees capacity. The regression
uses the real HTTP transport, v2 ingress, mixer, runtime, arbiter, and manual scheduler; its decoder
and speech observations remain controlled, so it proves queue transactionality rather than G4/G5.
Raw result: `evidence/phase1/t3/iteration-5-v2-backpressure.txt`.

## Local ARM64 vLLM smoke — 2026-08-13

**VERDICT: PARTIAL, NON-GATING — engine and MOSS registration pass; serving and metrics remain
blocked by the shared Docker VM.**

The official `vllm/vllm-openai-cpu:latest-arm64` image (digest
`sha256:e6745d7ba6610f637c6f22fc06cd730342e50245b6c46767235600483adfbbde`) runs vLLM `0.27.1`
and registers both `MossAudioModel` and `MossTranscribeDiarizeForConditionalGeneration`. This
retires the claim that no local vLLM engine is available.

The real startup attempt did not reach `/health`, `/v1/models`, or `/metrics`. Docker Desktop's
shared ARM64 VM exposes only 8.2 GB and already hosts unrelated workloads; its API became
unresponsive before checkpoint weights downloaded. The agent did not restart or reconfigure
Docker because doing so would disrupt those workloads. No decoder request or required vLLM metric
was measured, so G4/G5 remain unsatisfied. Raw result:
`evidence/phase1/t3/iteration-6-local-vllm-smoke.txt`.

## Resource-isolation recheck — 2026-08-13

**VERDICT: BLOCKED, NON-GATING — no safe isolated local runtime is currently available.**

Docker recovered after iteration 6, but it is still the host's only installed Linux container
runtime. Its shared VM remains limited to 8.2 GB; 16 unrelated containers leave only 665 MB
available and its 1 GiB swap is effectively exhausted. Host Python has no vLLM module, and the
MOSS Hugging Face cache contains only the 2.3 KiB configuration blob rather than model weights.

No service was started and no shared workload was changed. A qualifying run still needs an
operator-approved Docker maintenance window or another resource-isolated local runtime. Raw
result: `evidence/phase1/t3/iteration-7-resource-isolation-audit.txt`.

## Three-strike stop gate — 2026-08-13

**VERDICT: BLOCKED — supervisor input required; no safe autonomous candidate remains.**

Iteration 8 independently found the same local-runtime blocker as iterations 6 and 7: Docker is
the only installed Linux runtime, its shared 8.2 GB VM still carries 16 unrelated containers,
host Python has no vLLM, and the MOSS cache contains no model weights. The charter's
three-consecutive-blocked-iterations rule therefore fired. Issue #3 was updated with the exact
blocker and a request for an operator-approved Docker maintenance/resize window or another
resource-isolated local runtime.

No dispatcher bound was guessed or implemented. The controlled results remain non-gating, and the
real G4/G5 measurement remains a prerequisite. Raw result:
`evidence/phase1/t3/iteration-8-stop-gate.txt`.

## Remote-vLLM unique-marker inventory — 2026-08-18

**VERDICT: PASS — the existing hash-pinned W2 source contains eight usable, distinct marker clips.**

Question: can the read-only production vLLM endpoint recognize one distinct marker from each of eight
bounded clips in the exact W2 fixture, without that marker occurring in any other candidate clip?

`proto_unique_marker_inventory.py` queried `OpenMOSS-Team/MOSS-Transcribe-Diarize` through the local
`/v1` tunnel. It used fixture manifest SHA-256
`8e5eed2421482ab626e322a6242eb5ab57b43a091034bfc61bab7aef8d869155` and source WAV SHA-256
`a42507d9f5cbaf62407751793735a4a1edf6fefe6c2625d7c02863f5016b6eea`. All eight markers were present
in their own direct transcription and absent from every other candidate: `New York`, `payments team`,
`huge thanks`, `show notes`, `investment advice`, `entertainment purposes`, `feels appropriate`, and
`dressed up`. Raw transcripts, clip bounds, timing, and both hashes are in
`evidence/phase1/w2-local-concurrency/iteration-29-unique-marker-inventory.json`.

The exclusivity condition is material: `cool technology` was rejected because the preceding bounded
`payments` clip also transcribed it. This probe does not test cross-session isolation, reconnect,
fairness, G4, or G5. Next, configure those eight audited clips in the W2 fixture, fail closed whenever
a phase lacks one unique marker per session, and add the missing overload isolation/reconnect evaluation
before the frozen matrix is replayed.

## Remote-vLLM integrity-oracle absorption — 2026-08-18

**VERDICT: PASS — fixture capacity and the fail-closed overload oracle are ready for one fresh frozen run.**

Question: does the actual eight-marker fixture now support every W2 phase without repeated-marker false
positives, and will the harness reject a missing unique clip, a foreign canonical transcript, or an
unobserved reconnect instead of treating them as isolation evidence?

The fixture now contains eight separately bounded clips, all read from configuration by
`proto_unique_marker_inventory.py`. The real read-only endpoint re-inventoried that exact manifest
(`d893248526fc29845817c06affb9d665d0cde6600e7a16c35945a695e8bb9aee`): all eight expected markers
were present in their own clip and absent from every other clip. Raw output:
`evidence/phase1/w2-local-concurrency/iteration-31-unique-marker-fixture.json`.

The measurement runner now assigns the first N distinct configured clips to an N-session phase and refuses
any undersupplied or duplicate-marker phase before capture. Its instrumented canonical event log retains
the rendered transcript for submitted spans, without retaining PCM. During overload it sends the peer's
entire bounded clip, waits for both owned markers through reconnect polling, and requires the reconnect's
snapshot plus replayed canonical events to resolve only to their session's text. Focused route/runner tests
passed 10/10; their falsified cases cover an undersupplied phase, a duplicate marker, and a foreign marker
in both canonical and reconnect-replayed evidence. Raw JUnit:
`evidence/phase1/w2-local-concurrency/iteration-31-integrity-oracle.xml`.

This is harness and fixture evidence only. It establishes neither G4 nor G5; rerun the unchanged
preregistered remote-vLLM matrix in a fresh evidence directory.

## Writer/evaluator drain boundary — 2026-08-18

**VERDICT: PASS — a writer-owned drain barrier is required before evaluating lifecycle evidence.**

Question: can the production asynchronous canonical-event writer make a complete, fair lifecycle evaluate as
incomplete when the runner reads the event file before the writer drains?

One command (prints full before-drain and after-drain state):

```bash
.venv/bin/python prototypes/streaming-diarization/concurrency/proto_writer_evaluator_boundary.py \
  --output evidence/phase1/w2-local-concurrency/iteration-33-writer-evaluator-boundary.json
```

The probe exercised the production `_CanonicalEventLogWriter` and the production
`_canonical_lifecycle_fairness` evaluator, without a service or scheduler. In all three trials it enqueued a
complete two-session, eight-item lifecycle (48 records). The writer had already recorded write activity, but
the immediate file read saw 0 records and failed closed for absent queued/started/processed evidence. After
the writer's non-closing `drain()` barrier, all 48 records were readable and the evaluator passed (8 contended
dispatch observations, maximum skew 1). Artifact SHA-256:
`31fe21ec4c1eeab9711ccfc8d9a83ee6e7794f021c46464fcade73fe6934e975`.

Iteration 35 implemented that measured boundary: the runner asks its loopback route for a bounded writer-owned
drain before every normal or overload lifecycle read, and it refuses to evaluate if the writer does not
acknowledge inside the caller's existing stop deadline. The writer remains open for later phases. This changes
no fairness, stop-drain, latency, or scheduler value. It establishes only the observation boundary; it does
not establish scheduler fairness, stop-drain correctness, G4, or G5.

## Saved lifecycle completeness audit — 2026-08-19

**VERDICT: FAIL CLOSED — run 32 cannot be re-scored; rerun the unchanged frozen matrix.**

Question: after adding the writer-owned boundary, does run 32's already-written lifecycle JSONL contain every
event the writer reported, so the old fairness and queue-residue results can be safely re-evaluated without a
new live run?

One command (read-only over the saved evidence; prints full phase accounting):

```bash
.venv/bin/python prototypes/streaming-diarization/concurrency/proto_saved_lifecycle_completeness.py \
  --run-directory evidence/phase1/w2-local-concurrency/run-20260819T011500-iteration32 \
  --output evidence/phase1/w2-local-concurrency/iteration-36-run32-lifecycle-completeness.json
```

The raw log has **4,240** records but its final writer counter is **4,245**. The first five phase boundaries
match exactly (202, 548, 1,185, 2,259, and 4,194 cumulative records), while overload has 46 persisted records
against its 51-record counter. Thus the terminal matrix lifecycle evidence is incomplete. The evidence audit
does not reclassify any saved fairness or stop-drain result; it requires a new frozen matrix using the repaired
writer boundary and separated predicates. Artifact SHA-256:
`evidence/phase1/w2-local-concurrency/iteration-36-run32-lifecycle-completeness.json` is recorded in the
iteration evidence with SHA-256 `b0b4493c54218056d91c9925bdf6b5d577f3a3a073ce551c9d9eb31e5db04052`.

This names the third degenerate oracle in this workstream: repeated markers, then the unscoped fairness counter,
then the writer/evaluator race. A derived number is only usable when its source is complete and its predicate
actually measures the behavior it names. This audit establishes no scheduler result, stop-drain result, G4,
G5, live route, or inference result.
