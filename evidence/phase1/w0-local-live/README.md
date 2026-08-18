# W0 local CPU live-provider bundle

This is the finalized manifest generated for source revision
`ab7a998ab6acb805eb30e91477ca3abf22dac83f`. The ignored ONNX model and golden
WAV are deliberately host-local and must be placed beside this manifest in the
live data directory; all asset paths are relative so the directory can move as
one unit.

| File | SHA-256 |
| --- | --- |
| `voxceleb_resnet152_LM.onnx` | `5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8` |
| `golden.wav` | `d101dd44a5976c466d254df218f4e28b60091aba00b1ce2e9110a677ac0e60aa` |
| `live-provider-manifest.json` | `c7102f467c206b739e3e1feaf7a0902e8f7fed89f8fe3d5c4bf90b122edc331a` |

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
