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

After an authorized GitHub handoff and service restart, run the parked
bounded-window deployed proof from this branch:

```bash
bash "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-002-window-stitch-contract/deployed-repro.sh"
```

Do not run that command against an unchanged deployment; it is a post-handoff
proof that the deployed service contains the branch-local windowing changes.

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
remains compact `[start][Sxx]text[end]`, and speaker labels are preserved exactly
as returned per window.

The parent job fails closed if any child window returns a vLLM error payload, zero
generated tokens, empty transcript text, or zero parsed transcript segments. Partial
windowed output is not published. The persisted API usage object includes
`window_count`, `completed_windows`, and `possibly_truncated`. Generated token
counts are aggregated across windows, so they are not comparable to one window's
output cap.

Current limits: this does not provide cross-window speaker identity, resume or
checkpointing, per-window retry, upload-limit changes, context-cap changes, or
larger vLLM request limits. Those require separate reviewed changes.

## Reinstall or update

The reproducible setup helpers are in `ops/`:

```powershell
wsl.exe -d Ubuntu -- bash /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/install-wsl.sh
wsl.exe -d Ubuntu -- bash /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/download-model.sh
wsl.exe -d Ubuntu -- bash /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/install-services.sh
```
