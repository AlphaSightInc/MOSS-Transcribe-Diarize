# P3 long-source scaling prototype

Question: does the production File window/checkpoint seam preserve full below/at/above
200-minute geometry and identical identity semantics after interrupted decoding?

Minimum state: source duration, fixed production windows, atomic checkpoint prefix,
decoder results, and the window audio paths consumed by identity resolution.

Invariants: no hidden duration cap or tail loss; every window is at most 150 seconds;
identical decoder results produce identical final text/identity after resume; File/URL
supplies durable checkpoint storage; source/output storage may grow linearly while active
Python memory never contains whole-source PCM.

Assumptions: the deterministic decoder says nothing about acoustic quality or real GPU
throughput. Tiny extracted files exercise control flow, not PCM disk cost. The report
therefore projects PCM/scratch bytes from the production 16 kHz mono PCM16 contract.

Falsifier: omitted/duplicated tail ownership, a resume mismatch, missing production
checkpoint routing, or superlinear control-state growth.

Tool decision: use the real `WindowedRunner`, `plan_windows`, checkpoint store, stitching,
and File task dispatch with deterministic adapters. Any failure changes implementation;
no decoder/GPU call can sharpen these lifecycle facts.

The 201-minute live run is narrower: it proves production runtime source retention, Stop,
terminal windowing, and abort release with nonzero PCM and deterministic empty canonical
answers. It is not end-to-end speech or acoustic qualification. `speech_scaling.py` separately
measures word-producing canonical publication at 5/15/30 minutes with one regular scheduler
drain per frame; it avoids an artificial ingest-faster-than-decoder backlog. The post-fix
receipt also includes a direct 201-minute point; `speech-scaling-before.json` preserves the
quadratic falsifier.

`build_candidate_manifest.py` produces an **isolated** candidate manifest with a
460,800,000-byte per-tape resource provision (240 minutes of 16 kHz mono PCM16). This is a
finite disk budget, not a product duration limit. The low-level default remains no tape;
Phase-2 Live refuses startup when `max_tape_bytes` is omitted. The currently consumed host
manifest is measured separately and is not edited.

Run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/long-source-scaling/probe.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/long-source-scaling/speech_scaling.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/long-source-scaling/build_candidate_manifest.py \
  --input ~/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json \
  --output /private/tmp/moss-duration-candidate/live-provider-manifest.json \
  --source-revision "$(git rev-parse HEAD)"
```

Candidate launch binding (not executed by this prototype): set
`MOSS_LIVE_PROVIDER_MANIFEST=/private/tmp/moss-duration-candidate/live-provider-manifest.json`
in an isolated Account profile. `ops/account-web-launcher.sh` passes that exact path to
`phase2_web_cli`; `LiveProviderBundleConfig.from_manifest` constructs the runtime descriptor,
and Phase 2 gives the same byte bound to its durable Live audio stage.
