# Local deployment notes

## Deployment choice

The GPU inference stack runs in Ubuntu 24.04 under WSL 2. The repository,
authoritative model download, configuration, job data, and logs remain under
`D:\Coding\MOSS-Transcribe-Diarize`. The isolated runtime uses an uv-managed
CPython 3.12 installation in the WSL user's Linux filesystem. A runtime copy of
the model is also kept there because loading tensors directly from the
Windows-mounted `D:` drive is prohibitively slow under WSL's 9P layer.

WSL was selected because vLLM only supports Linux natively and explicitly
recommends WSL on Windows. NVIDIA CUDA passthrough is already working on this
machine. Native Windows would be adequate for basic Transformers inference,
but not for the project's supported continuous-batching vLLM service.

The vLLM API listens only on WSL loopback port 8000. The web application listens
on port 7860 and is the only component exposed to trusted LAN and Tailscale
clients. The application does not provide user authentication, so do not expose
port 7860 to the public internet.

The installed runtime uses uv 0.11.30 with uv-managed Python 3.12.13. The pinned
CUDA 13 vLLM wheel needs its legacy model runner under WSL because WSL does not
expose CUDA unified virtual addressing. FlashInfer sampling is also disabled to
avoid a compiler/header mismatch in that wheel; vLLM falls back to its PyTorch
sampler while retaining CUDA model execution and continuous batching.

## Addresses

- Local: `http://127.0.0.1:7860`
- LAN: `http://192.168.68.38:7860`
- Tailscale: `http://100.64.0.8:7860`
- Private vLLM API inside WSL: `http://127.0.0.1:8000/v1`

The LAN address can change if the router assigns this PC a different address.
The Tailscale IP remains stable for this node. This tailnet's control plane does
not currently implement Tailscale Serve, so the service uses the node IP and
port rather than a Tailscale-provisioned HTTPS URL.

## Service operations

Run these commands from PowerShell:

```powershell
wsl.exe -d Ubuntu -- systemctl --user status moss-vllm.service moss-web.service
wsl.exe -d Ubuntu -- systemctl --user restart moss-vllm.service moss-web.service
wsl.exe -d Ubuntu -- journalctl --user -u moss-vllm.service -u moss-web.service -n 100 --no-pager
```

The Windows sign-in task starts WSL and refreshes the LAN forwarding rule because
the WSL NAT address may change after a restart.

To refresh the Windows forwarding immediately, run this from an Administrator
PowerShell window:

```powershell
& 'D:\Coding\MOSS-Transcribe-Diarize\ops\configure-windows-network.ps1'
```

## Verification

The installation passed all 27 upstream tests and an end-to-end six-second GPU
transcription. To repeat the health and transcription check:

```powershell
& 'D:\Coding\MOSS-Transcribe-Diarize\ops\smoke-test.ps1'
```

IDEA-003 local branch validation uses these three gates from the target root:

```bash
bash "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-003-speaker-continuity/repro.sh"
python -m pytest tests/test_speaker_continuity.py tests/test_windowed_transcription.py tests/test_app_api.py -q
python -m pytest tests -q
```

Latest local IDEA-003 audit: the evidence prototype passed, the focused
speaker-continuity/window/API selection passed with 28 tests and 3 subtests, the
full suite passed with 54 tests and 6 subtests, and `ops/moss.env` had no diff.

After an authorized GitHub handoff and service restart, run the parked deployed
speaker-continuity proof from this branch:

```bash
bash "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-003-speaker-continuity/deployed-repro.sh"
```

Do not run that command against an unchanged deployment; it is a post-handoff
proof that the deployed service contains the branch-local speaker-continuity
changes.

## Fine Fixture Evaluation

The speaker-mapped evaluator is a CPU-only scoring tool for short fine fixtures.
It compares positional MOSS speaker labels such as `S01` against real-name
reference speakers by exact assignment, then reports TBSA and DER mappings in
deterministic JSON. It does not run inference, import external scorers, classify
model quality, or set pass/fail thresholds for long-form recordings.

Run it from the repository root:

```bash
python -m moss_transcribe_diarize.evaluation \
  --manifest path/to/sample_manifest.json \
  --alignment-stats path/to/alignment_stats.json \
  --hypothesis path/to/segments.json
```

`--hypothesis` accepts a JSON segment list, a JSON object with `segments`, or
JSONL. Each segment must contain `start`, `end`, `speaker`, and `text`. The
reference file is always `reference.jsonl` next to the manifest; embedded
manifest reference paths are metadata only. The fine gate fails closed unless the
fixture has `match_rate == 1.0`, reference coverage equal to duration, usable
reference timestamps/text, and duration at most five minutes.

## Long Fixture Certification

The long-form fixture certifier is a CPU-only identity and policy check. It
streams source SHA-256 and byte counts, probes duration with `ffprobe`, inventories
the manifest-named sibling reference and alignment files, and fails closed on any
declared fact or threshold drift. It does not upload media, run transcription,
score quality, restart services, or close requirement A.

Run it from the repository root:

```bash
python -m moss_transcribe_diarize.long_form_fixtures \
  --manifest path/to/manifest.json \
  --corpus-root path/to/corpus-root
```

Manifests use schema version 1 and corpus-root-relative paths only. The
`duration_quality` role is the coarse, quality-eligible long fixture role:
`match_rate` must be `1.0`, duration must exceed 200 minutes, size must exceed
decimal 200 MB, and WER/DER pass-fail remains forbidden. The
`strict_size_smoke` role is smoke-only: it must exceed binary 200 MiB and may
record source integrity, admission, completion, resource, and continuity
observations, but it is not quality-eligible and must not add speaker-count,
sampled-message, WER, or DER pass-fail gates.

## GPU capacity

`ops/moss.env` is intentionally configured to coexist with the existing MinerU
vLLM workload that reserves about half of the RTX 4070 Ti Super. The profile gives
MOSS 30% of VRAM, two active sequences, and a 16K context, leaving roughly 1--1.5
GB of headroom after both services have loaded.

`MOSS_MAX_MODEL_LEN` is the shared context-cap source of truth. The vLLM service
uses it as `--max-model-len`, and the web service receives the same value as
`--max-len` so `/api/runtime`, the UI default, uploads, and reruns all report and
enforce the deployed serving cap.

If the other GPU service is stopped and MOSS can use the GPU exclusively, change
the values to:

```ini
MOSS_GPU_MEMORY_UTILIZATION=0.80
MOSS_MAX_MODEL_LEN=32768
MOSS_MAX_NUM_SEQS=4
MOSS_MAX_NEW_TOKENS=30000
```

Then restart both MOSS services. Higher values are possible only after measuring
the target recording lengths and concurrency; the practical limit is the 16 GB
VRAM capacity.

## Bounded vLLM windows

The web app wraps only the vLLM backend in a bounded window runner. HF inference
keeps the direct runner path and does not use this windowing contract.

For vLLM jobs, the app probes media duration and forwards the source as 16 kHz
mono WAV windows. Each forwarded request is at most 150 seconds. Window starts
advance every 120 seconds, so adjacent windows overlap by 30 seconds. The final
window starts at the next 120-second stride and is shorter when needed; it is not
shifted backward to fill 150 seconds.

Window stitching uses absolute timestamps. Each local segment is offset by the
window start, then kept only when its absolute midpoint belongs to that window's
ownership interval. Overlap ownership is split at the temporal midpoint. Non-final
upper bounds are half-open; the final upper bound is closed. The transcript grammar
remains compact `[start][Sxx]text[end]`; only the speaker labels may be relabeled
by the local identity resolver before midpoint ownership.

## Upload admission and transaction

`POST /api/jobs` admits uploads before FastAPI multipart parsing consumes the
body. `Content-Length` is mandatory, syntactically decimal, and non-negative; a
missing or malformed value returns HTTP 411. The runs filesystem must have at
least `2 * Content-Length + 512 MiB` free before the body is read; less free
space returns HTTP 507, while equality is accepted.

The upload receive limit is a 30-second idle bound, separate from the vLLM
inference timeout. Large uploads may take longer than 30 seconds as long as each
bounded receive/read block progresses. A stalled receive returns HTTP 408.

Committed uploads are transactional. The web app streams bounded blocks through
`JobManager` into a job-local temporary input while computing byte count and
SHA-256, flushes and file-`fsync`s the temporary file, then atomically renames it
into place. Only after that durable input commit does the app persist the queued
`JobRecord`, set source metadata and ready checkpoint metadata, and enqueue the
job once.

Any multipart, receive-timeout, write, hash, persistence, or other pre-enqueue
failure aborts the unpublished transaction and removes the in-memory record,
temporary input, final input, `job.json`, queue entry, and job directory. The
response shape for successful uploads remains the existing `JobRecord` JSON.

## Cross-window speaker identity

The vLLM window runner resolves speaker labels after all per-window transcript
segments have absolute timestamps and before midpoint ownership. The resolver
does not infer identity from equal local labels. Its node key is
`(window_index, local_label)`, and labels are deterministic job-level labels that
continue past `S08`.

Tier A is always local and deterministic. It compares adjacent overlapping
windows with merged interval support, Dice overlap, exact SciPy rectangular
assignment, and mutual-margin checks. The trial defaults are 2.0 seconds of
support, Dice >= 0.75, and a 1.0-second mutual margin. Same-window nodes are
cannot-link. Ambiguous, low-support, low-Dice, and cannot-link cases abstain with
reason-coded diagnostics instead of forcing a merge.

Tier B is an optional trial for Tier-A-unresolved singleton components only and
is disabled by default. The pinned trial asset is WeSpeaker ResNet152-LM revision
`4adba1525a6c9d5fff74b6df43a6ec97a86c4112` with state SHA-256
`b0446afc11bb51b0eb79559b60508e967310980cf1a5580804473104024239bc`.
When explicitly enabled, the local adapter must find and hash-verify that state
file before embedding. It performs no job-time download and model weights are not
committed.

Tier B selects only single-label speech evidence at least 2 seconds long, with at
most three intervals per node. Candidate centroids are matched with normalized
cosine >= 0.70 and mutual margin >= 0.20 while preserving same-window cannot-link.
Short audio, mixed or invalid embeddings, low similarity, low margin, missing
assets, hash mismatch, and provider failures abstain. Missing or failing Tier B is
reported as `tier_b_unavailable` and does not discard Tier-A output.

Finished jobs persist additive identity metadata without changing compact
transcript text, subtitles, or exports. The API exposes `identity_summary` and
`files.identity_resolution`; the versioned job artifact is
`identity-resolution.json`. Both summaries include
`fragmented_recurring_speakers`, the number of final singleton identity
components carrying an unmatched/unresolved birth-or-return diagnostic, and
`false_accepted_edges`, the number of accepted diagnostic edges that violate
same-window cannot-link or boundary/component one-to-one constraints. Both
values are computed from the persisted diagnostics rather than fixed constants.

The parent job fails closed if any child window returns a vLLM error payload, zero
generated tokens, empty transcript text, or zero parsed transcript segments. Partial
windowed output is not published. The persisted API usage object includes
`window_count`, `completed_windows`, and `possibly_truncated`. Generated token
counts are aggregated across windows, so they are not comparable to one window's
output cap.

## Durable window resume

For vLLM jobs, each web-app job directory contains an internal `checkpoint/`
directory. Its root manifest binds the job ID, source SHA-256, complete 150/120
window plan, model/prompt/inference options, identity configuration, Tier-B state,
and a contract fingerprint. Each committed window is an immutable record named
from its index and absolute start/end microseconds.

Resume is fail-closed. Startup recovery requeues interrupted `queued`,
`loading_model`, `transcribing`, and `postprocessing` jobs once. Same-process
window failures remain `failed` until `POST /api/jobs/{id}/resume` is called.
Active resume requests return the current job state without adding duplicate work.
`waiting_review`, `done`, `cancelled`, and legacy jobs without checkpoint metadata
do not resume. Changed inference options continue to use `/rerun`, which creates a
new job ID.

Only a validated consecutive committed prefix from window 0 is reused. Stray temp
files are ignored, but corrupt records, schema mismatches, source or fingerprint
mismatches, plan mismatches, duplicate records, and gaps reject before model
invocation. A committed window is never replayed for the same job and contract;
the first uncommitted window may retry. Final transcript stitching and identity
resolution are rebuilt from ordered raw committed window outputs rather than from
serialized resolver internals.

During postprocessing, transcript, segments, SRT, ASS, and identity artifacts are
written under `.postprocessing`, validated as a complete set, then published by
replace before `waiting_review`. Startup recovery from `postprocessing` discards
staging and nonterminal final files and rebuilds them from the committed prefix.
Segment and download routes reject nonterminal jobs, so stale partial output is
not exposed as successful.

Current limits: Tier B remains default-off pending WSL/PyTorch parity and
approved deployed proof. This resume path does not add per-window retry beyond
same-job resume, upload-limit changes, context-cap changes, or larger vLLM request
limits. Those require separate reviewed changes.

## Default-off live session slice

IDEA-009 live mode is a local, default-off substrate only. It adds a sibling
`LiveSession` state machine for ordered 16 kHz mono PCM frames, replace-only
provisional suffixes, immutable in-order canonical commits, and exact
accepted/accounted sample equality on successful close. The batch `JobManager`,
complete-file upload routes, checkpoints, artifacts, statuses, and
`waiting_review` workflow remain the production path.

Provider admission is fail-closed. VAD, stable live identity, and bounded
complete-WAV inference are internal adapters, and any provider asset must already
exist locally with the declared SHA-256. The live path must not download models or
weights at runtime. Canonical spans freeze only from VAD end-silence, hard cap, or
stop flush, and they publish only after bounded decode returns valid transcript
timestamps and confirmed stable session identity.

The FastAPI transport is absent unless `create_app(..., live_enabled=True,
live_max_retained_samples=...)` is called by an explicit local test or reviewed
future integration. Enabling this in deployed service configuration is not part
of the current local gate and should not be described as production live mode.

IDEA-010 adds an offline replay CLI for this disabled substrate:

```bash
python -m moss_transcribe_diarize.live_replay \
  --manifest /path/to/live-replay-manifest.json \
  --out-dir runs/live-replay
```

The manifest supplies ordered 16 kHz mono PCM frames, speech observations,
offline provider identity, bounded decode outputs, and identity evidence. The
CLI preflights manifest revision, configuration hash, provider revision/assets,
and optional read-only service state, then writes `trace.jsonl`, `summary.json`,
and `evaluator.jsonl`. It exits nonzero on integrity, provider, identity, or
RTF failures. It never starts, restarts, or enables the deployed service.

Local CPU gates for this disabled slice:

```bash
python -m moss_transcribe_diarize.live_replay --help
python -m pytest tests/test_live_identity.py tests/test_live_endpoint.py tests/test_live_replay.py -q
python -m pytest tests/test_live_session.py tests/test_live_vad.py tests/test_live_api.py -q
python -m pytest tests/test_vllm_runner.py tests/test_windowed_transcription.py tests/test_jobs.py tests/test_app_api.py -q
python -m pytest tests -q
git diff --check
```

Operator-only enablement replays remain parked until a separate deployment
handoff reviews service configuration and available live provider assets. Do not
run or report them as measured production latency, quality, VAD suitability, or
online identity readiness from this branch-local CPU work:

```bash
# parked 60-second local/live replay after explicit deployment enablement
# parked 300-second local/live replay after explicit deployment enablement
```

## Reinstall or update

The reproducible setup helpers are in `ops/`:

```powershell
wsl.exe -d Ubuntu -- bash /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/install-wsl.sh
wsl.exe -d Ubuntu -- bash /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/download-model.sh
wsl.exe -d Ubuntu -- bash /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/install-services.sh
```
