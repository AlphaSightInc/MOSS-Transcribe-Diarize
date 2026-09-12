# Speechless terminal windows — 2026-09-11

**Result:** empty decoder output on a verified speechless window is a successful empty segment list. Empty output on speech remains a decode failure. A tape containing speech plus a long silent tail can finalize without changing identity policy or QUALITY_BOUNDS. No running service, local stack database, or host configuration was modified.

## Decision and measured basis

The domain question is whether an empty answer means no speech was present or the decoder missed speech. The independent evidence is the exact decoded window's mono 16-bit 16kHz PCM. Reuse the existing `webrtcvad-wheels==2.0.14` live/acceptance dependency; no dependency added.

Use WebRTC VAD mode 0 (least aggressive, favor detecting speech), 20ms frames, with **voiced sample fraction strictly below 0.0001 (0.01%)** to accept speechlessness. One full voiced frame in a maximum 150-second window is 0.0133%, enough to retain failure. A new VAD instance per window prevents state from a preceding window affecting this one. The last partial frame is zero-padded only for the VAD call; the denominator and voiced count include actual samples only.

VAD runs only after the decoder returns empty text or raises the typed no-generated-tokens/empty-text outcome. Nonempty malformed output, decoder exceptions, unreadable/nonconforming PCM, or unavailable VAD are never converted to success. Successful nonempty decodes take their existing path. This is an empty-output classification, not a pre-decode silence-skipping optimization.

Prototype contract, runnable command, and results: `prototypes/streaming-diarization/speechless-windows/NOTES.md`, `measure.py`, `results.json`, and `production-results.json`. The original independent probe preceded production changes; the final probe also calls the production classifier and checks agreement for every case.

| PCM case | Voiced fraction | Decision |
|---|---:|---|
| 150 seconds silence | 0 | speechless |
| 50 seconds human Javier introduction | 0.9324 | speech present |
| Same human speech plus silence to 150 seconds | 0.31187 | speech present |
| One second from that human recording surrounded by silence | 0.00347 | speech present |
| Silence ending on an incomplete frame | 0 | speechless |

Independent probe time was approximately 12ms per 150-second window on this Mac. This is not a decoder latency benchmark. Quiet/distant speech can be missed by VAD; the strict threshold and mode 0 reduce that risk but do not establish perfect speech detection. The human corpus probe is separate from the bundled provider fixture, whose human provenance was not verified.

## Implementation and diagnostics

- **F1:** `WindowedRunner._decode_window` classifies both typed empty outcomes and directly returned empty results. Accepted windows retain `condition=speechless_window_empty`, window index/bounds, sample counts, VAD mode/frame size, voiced fraction, and threshold in `TranscriptionResult.window_diagnostics`.
- **F2:** validated empty windows are allowed through stitching and count as completed. Their diagnostics survive checkpoint serialization/resume. Nonempty window stitching and identity resolution policy are unchanged.
- **F3:** terminal accounting and the content-free diagnostic event projection retain these window diagnostics. A proposal is still `running` until `LiveSession.apply_text_revision` accepts it; only publication sets `final`. An entirely speechless tape still has no transcript to publish and retains the existing no-transcript session outcome.

The typed empty exception does not expose prompt-token count; its synthesized empty result uses the existing integer accounting's zero for that unavailable count, preserves reported generated tokens, and measures elapsed decode time. No decoder text is added to diagnostics.

## Validation

Before implementation: new regressions **8 failed, 4 passed** (`/tmp/moss-speechless-red.log`). Failures included short/150-second silent windows and the mixed tape terminal pass.

Focused regression after implementation: **64 passed, 19 subtests passed** in 6.00s. Includes:

- **T1:** typed zero-token, typed empty-text, and directly returned empty results on silence, including partial-frame input.
- **T2:** speech with empty output still fails; later speech-bearing windows fail a mixed job; unparseable nonempty output remains failure.
- **T3:** speech plus a 300-second tape's silent tail passes real extraction, windowing, stitching, terminal finalization, and real session publication to `final`, preserving the spoken text.
- **T4:** the earlier 600-second host-reproduction test now processes all five windows and retains three silent-window classifications instead of failing at window 2. Sanitized diagnostic projection removes injected transcript text.
- **T5:** checkpoint resume reuses an accepted silent window without decoding it again; missing VAD preserves failure.

Full Python suite: **1380 passed, 2 existing optional corpus skips, 37 subtests passed**, zero failures, in 83.54s. Command: `.venv/bin/python -m pytest tests/ -q --junitxml=/tmp/moss-speechless-full.xml`. No frontend source changed; no model or host service calls were needed for these deterministic classification regressions.

Pre-push rebase incorporated `eb935313` (frontend polling interval and tests/assets only). No conflicts or backend changes. Post-rebase frontend suite: **196 passed**; TypeScript typecheck passed. The Python suite above ran before that unrelated frontend commit. Push target: `private/auto-mvp-0911`.
