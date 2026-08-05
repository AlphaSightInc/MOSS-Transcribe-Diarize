# pending_source_separation_001

Status: real aligned dual-lane recording captured.

Expected files for completion:

- `remote.wav`
- `local.wav`
- `reference_system_audio.jsonl`
- `reference_microphone.jsonl`

Packaged app capture path after `DARCHDISC-052`:

- Build with `./scripts/build_app_bundle.sh`.
- Launch `.build/app-bundles/debug/LiveTranscribe.app`.
- Start a Mic+Speaker session with LLM disabled.
- Use the session status `output_dir`; the app writes
  `dual_lane_audio/remote.wav` and `dual_lane_audio/local.wav` there.
- Copy those real WAV files into this case directory, then add per-lane JSONL
  references and manifest timing metadata.

The current fixture is metric-eligible as a source-separation/leakage fixture:
both lanes contain the same real `lex_keyu_jin` playback content because the
microphone lane captured the room playback from MacBook Pro Speakers.

## Iteration 8 capture attempt - 2026-04-29

- Built packaged app with `./scripts/build_app_bundle.sh`; signing was
  `local-dev-cert (LiveTranscribe Local Dev, 51E289BA70A36BCDD063F1EFA660D56AEBD83DA7)`.
- Set macOS output volume to 20 before playback.
- Disabled LLM by using the default empty endpoint/model live session settings;
  no LLM-specific validation was run.
- Used LaunchServices app-mode packaged capture on port 8090 with Mic+Speaker
  mode and played real fixture
  `data/benchmark_diarization_1min/samples/lex_keyu_jin/audio.wav`.
- The app wrote aligned lane WAVs, but the local/microphone lane was silent:
  remote RMS 0.10312092 / peak 0.84906006; local RMS 0.00000000 / peak
  0.00000000.
- Because the microphone lane has no speech, the attempted WAVs were preserved
  only under `scripts/ralph/artifacts/DARCHDISC-055/partial_ls_*.wav`; this
  fixture case remains incomplete.
- No headed browser was used, so browser cleanup was not applicable.

## Iteration 33 capture - 2026-04-29

- Built packaged app with `./scripts/build_app_bundle.sh`; signing was
  `local-dev-cert (LiveTranscribe Local Dev, 51E289BA70A36BCDD063F1EFA660D56AEBD83DA7)`.
- Launched `.build/app-bundles/debug/LiveTranscribe.app` through
  LaunchServices on `127.0.0.1:18077`.
- Selected `MacBook Pro Microphone` device index `120`.
- Set macOS output volume to 20 and input volume to 100 before playback.
- Disabled live-session LLM settings with empty endpoint/model and
  `summaryIntervalSec` / `formatIntervalSec` set to `0`; session status
  reported `llm_status: idle`.
- Played real fixture
  `data/benchmark_diarization_1min/samples/lex_keyu_jin/audio.wav` once in
  Mic+Speaker mode.
- Copied the packaged-app lane exports into this case:
  - `remote.wav`: system-audio/Core Audio Tap lane.
  - `local.wav`: microphone/AVAudioEngine lane.
- Captured WAV stats:
  - system audio: 59.584 sec, RMS 0.104984, max amplitude 0.849086.
  - microphone: 59.584 sec, RMS 0.017853, max amplitude 0.172704.
- Per-lane references were derived from the existing
  `lex_keyu_jin/reference.jsonl`, shifted by the measured system-audio
  first-nonzero offset `2.005272` seconds and clipped before the recorded WAV
  tail.
- No headed browser was used, so browser cleanup was not applicable. Cleanup
  left no exact-name `LiveTranscribe`, `afplay`, `ffmpeg`, `sox`, or
  `osascript` processes.
