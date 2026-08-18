# W0 local CPU live-provider bundle

This is the finalized manifest generated for source revision
`e1741f904fee942a5eef34e0d40a4d4f848b363d`. The ignored ONNX model and golden
WAV are deliberately host-local and must be placed beside this manifest in the
live data directory; all asset paths are relative so the directory can move as
one unit.

| File | SHA-256 |
| --- | --- |
| `voxceleb_resnet152_LM.onnx` | `5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8` |
| `golden.wav` | `d101dd44a5976c466d254df218f4e28b60091aba00b1ce2e9110a677ac0e60aa` |
| `live-provider-manifest.json` | `87fdd9335960f4765642a7b7a5e6a1437f9f100a591e58269b8717407b4cc2b9` |

Use the recovered real assets, not the fabricated `tests/test_live_manifest_finalizer.py`
fixture. The manifest declares its provider dependencies exactly: `onnxruntime==1.23.2`
and `webrtcvad-wheels==2.0.14`. The latter was installed from the local UV cache; no
network provider or alternate VAD was used.

Before launching a checkout at a different revision, regenerate the manifest from its
provisional sibling with that checkout's `git rev-parse HEAD` and the recorded finalizer
arguments. Do not copy a manifest source revision from another host. The preflight record
is [iteration-4-provider-preflight.txt](iteration-4-provider-preflight.txt).

This is a CPU/WebRTC bundle. Its successful golden preflight proves real local provider
admission only; it does not prove a GPU latency, memory, or attended-capture gate.

## Local attended-service recipe

The host-local data directory contains the finalized manifest beside the ignored, hashed
assets. The following starts the local TLS service without contacting a model endpoint; the
snapshot is the exact cached model artifact used by the G1/G2 canary. It does not write any
token to the repository or browser storage.

```bash
export MOSS_HF_MODEL=/Users/gao/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8
export MOSS_LIVE_PROVIDER_MANIFEST="$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
export MOSS_LIVE_HELPER_LEASE_SECONDS=30
./scripts/g3-attended-session.sh
```

`scripts/g3-attended-session.sh` instead uses vLLM only when a configured
`MOSS_VLLM_BASE_URL/models` returns 200; otherwise it requires the explicit local
`MOSS_HF_MODEL` above. The raw local TLS descriptor/session proof is
[iteration-6-local-hf-launch.txt](iteration-6-local-hf-launch.txt). Its HF/CPU decode path
is sufficient to make the attended G3 service ready, but is not a GPU G4/G5 measurement.
