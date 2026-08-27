# Goal 2 adoption record — 2026-08-25

- Branch: `ralph/live-convergence-0824`.
- HEAD: `7608c91ce36441d9075fbba41e18c5fae8f464ac`.
- Goal-1 production patch SHA-256:
  `b006de9b04c73315c4c6e323d77fe112739fcd33f0d0110e13794133a5278e85`.
- The current four-file production diff is byte-identical to that patch.
- Current Goal-1 service: PID `57283`, cwd exact repository, listener `*:7861`, model
  `OpenMOSS-Team/MOSS-Transcribe-Diarize`, vLLM queue `0/0`.
- Runtime descriptor remains Goal 1's descriptor: source revision `29681e0479305449bb40caa49154fe4b1ae85eea`,
  combined config hash `431efb3f5c0c3d0b685a8121b4e72eee08fc8072001f6d9b178e924321d7a265`.
- Existing tracked Goal-1 edits and all untracked evidence/prototypes are user-owned and preserved.

Goal-1 production file SHA-256:

```text
b16b84b339f642556e62907ef53d01a1bb7eb927469f56f8769621d3820f7974  moss_transcribe_diarize/app/live_transcript_convergence.py
4566af8ccdf83bcebf8ccb28be7977c1b15ceffc0bc9ced29ddf4edd1489f7ec  moss_transcribe_diarize/app/live_coordinator.py
fcaadb8e36649950c987d751df9e1effbbf70dab9b0e2e979e9481ea08f8e80f  moss_transcribe_diarize/app/live_service_runtime.py
a76565f1db51527465acef20259ded27690404ceba8821dd7e5803579aab5049  moss_transcribe_diarize/app/live_session.py
```

The controlling plan SHA-256 is
`a966938775e5dd062907941834e26eb8320efe05fbc8bc9b8f4ee1d239deee0c`.

## B1 disposition — stop before production

The causal production-path prototype replayed all 112 saved 15/10 windows across 12 case-runs.
The frozen batch rule reproduced its saved content and settled speaker projection in 12/12, but
failed causal ownership in 12/12: 46 selected words straddled the publication frontier and 24 more
were wholly behind it. The real `LiveSession` seam refused the first invalid proposal in every
case-run as `segment_outside_owned_interval`; the frozen comparator stayed byte-stable.

Per plan B1, this is `FAIL_STOP_NO_IMPLEMENTATION`. No 15/10 production code was written, no
candidate was deployed, and no ABBA inference was launched. Authoritative raw evidence:
`causal-prototype.json`, SHA-256
`fd1ab4d8db9b2b4293dca8bd004fa9a744c078ceb296136a3c7783b4a954300a`.
