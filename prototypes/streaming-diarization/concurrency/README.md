# Live concurrency bench

Ticket #3's bounded-dispatcher measurement extension. The first artifact freezes the gates and
metric definitions before any concurrency run.

Question: what is the largest dispatcher concurrency in `{1, 2, 4, 8}` that keeps live transcript
lag and memory below the frozen gates on the production live path?

One-command preregistration check (prints the full frozen state):

```bash
python3 prototypes/streaming-diarization/concurrency/validate_preregistration.py
```

CPU/HF-local preregistration (the deployed geometry is read from descriptors at run time;
this profile deliberately does not claim GPU figures):

```bash
python3 prototypes/streaming-diarization/concurrency/validate_cpu_hf_local_preregistration.py
```

Remote-vLLM tunnel preregistration (the future runner must use a run-owned manifest finalized
for its exact `HEAD`, probe the endpoint before and after, and never claim unavailable GPU telemetry):

```bash
python3 prototypes/streaming-diarization/concurrency/validate_remote_vllm_tunnel_preregistration.py
```

Controlled scheduler/queue probe (about 40 seconds; prints full state):

```bash
python3 prototypes/streaming-diarization/concurrency/proto_controlled_dispatcher.py
```

This replays hash-pinned real human-speech PCM in 0.5 s frames through the production runtime and
scheduler, but deliberately controls speech observations, decode, identity, and scheduler release.
It can reject scheduler/queue hypotheses; it cannot qualify G4 or G5.

The future measurement runner must load and hash-pin `preregistration.json`. Missing real decoder
results or missing local vLLM active/queued metrics cannot qualify a bound. Stubbed decoder runs may
exercise fairness and queue semantics, but remain labelled non-gating.

The CPU/HF-local runner must instead hash-pin `cpu_hf_local_preregistration.json`, compare its local
descriptor with the read-only deployed descriptor before capture, and retain the raw arrays named in
that contract. It may establish the local portions of G4 and G5, never deployed GPU latency or GPU
utilisation.

Its hash-pinned human-speech clip configuration is
`cpu_hf_local_fixture.json`. The runner uses two different bounded segments from that real recording,
then checks that each session renders only its own configured marker. The values belong in the fixture
configuration, never in general runner logic.

Full local CPU/HF measurement (about 19 minutes plus model warm-up):

```bash
.venv/bin/python prototypes/streaming-diarization/concurrency/run_cpu_hf_local_measurement.py \
  --model /Users/gao/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8 \
  --manifest /Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json \
  --provisional-manifest /Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.provisional.json \
  --output evidence/phase1/w2-local-concurrency/run-YYYYMMDDTHHMMSS
```

The command first reads the deployed descriptor, re-finalizes only the local manifest for the current
checkout, starts one loopback FastAPI process through the real `LiveServiceRuntime`, and records raw
frame responses, observer cursors/events, canonical dispatch order, instrumentation overhead, decode real-time
factor, and service process-tree RSS incrementally. Canonical-event file I/O runs in a dedicated writer thread,
with a five-second durability sync interval, so disk sync never holds the runtime publication lock. It records
screening at 1/2/4/8 sessions, then soaks only the largest
passing bound. The `--preflight` form validates its immutable inputs without starting a service.

Remote-vLLM route seam (one canonical span; not a W2 matrix or G4/G5 result):

```bash
.venv/bin/python prototypes/streaming-diarization/concurrency/proto_remote_vllm_route_seam.py \
  --manifest "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json" \
  --vllm-base-url http://127.0.0.1:18000/v1 \
  --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize \
  --live-helper-lease-seconds 30 \
  --output evidence/phase1/w2-local-concurrency/remote-vllm-route-seam.json
```

It reads `/v1/models`, starts only a loopback route probe, emits descriptor-derived two-lane frames,
and requires a `canonical_processed` event plus a clean stop. The heartbeat cadence is derived as one
quarter of the explicitly supplied helper lease. It records whether the manifest revision matches `HEAD`;
a mismatch, or this one-span probe itself, never qualifies W2.

The subsequent tunnel matrix must hash the exact remote-vLLM preregistration and fixture bytes and record
the selected model plus canonical `/models` identities before and after the run. It finalizes an ephemeral
execution bundle outside the repository, materializes its relative assets there, and copies only the finalized
manifest plus asset hashes into the evidence directory. It must not overwrite the shared local manifest or add
model bytes to evidence. Its p95 includes SSH-tunnel/tailnet transit; GPU memory, utilisation, OOM/errors,
and vLLM active/queued counts remain outside the available read-only surface.

Remote-vLLM tunnel matrix (about 19 minutes if a 600-second soak is selected; start the read-only tunnel
first). The preflight command checks endpoint identity and deployed bounds but does not start a local route
process. Use a fresh output directory for the measurement after a successful preflight:

```bash
.venv/bin/python prototypes/streaming-diarization/concurrency/run_remote_vllm_tunnel_measurement.py \
  --provisional-manifest /Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.provisional.json \
  --vllm-base-url http://127.0.0.1:18000/v1 \
  --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize \
  --live-helper-lease-seconds 30 \
  --port 18999 \
  --output evidence/phase1/w2-local-concurrency/run-YYYYMMDDTHHMMSS \
  --preflight
```

Without `--preflight`, the runner creates a new ephemeral finalized manifest for its captured `HEAD` outside
the repository, materializes its declared relative assets only in that temporary execution directory, and
copies the small manifest record into the requested output directory. It then starts one loopback production
route process using `VllmRunner`, runs the frozen 1/2/4/8 matrix plus the selected soak and overload/reconnect
sequence, and probes `/health` and `/v1/models` again before issuing its verdict. Helper health posts run at
one quarter of the explicit lease even while a remote request blocks.
