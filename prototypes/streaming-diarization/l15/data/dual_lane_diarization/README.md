# Dual-Lane Diarization Fixtures

This directory contains real Mic+Speaker diarization fixtures. `manifest.json`
records the remote/system and local/microphone lane layout, aligned WAV
recordings, per-lane references, and capture timing metadata.

## Required Case Layout

```text
data/dual_lane_diarization/cases/<case_id>/
  remote.wav
  local.wav
  reference_system_audio.jsonl
  reference_microphone.jsonl
  capture_notes.md
```

- `remote.wav`: system-audio/Core Audio Tap lane.
- `local.wav`: microphone/AVAudioEngine lane.
- `reference_system_audio.jsonl`: timestamped speaker/text reference for the
  system-audio lane.
- `reference_microphone.jsonl`: timestamped speaker/text reference for the
  microphone lane.

## Capture Steps

1. Set macOS output volume to 20:
   `osascript -e 'set volume output volume 20'`.
2. Build and launch the packaged app with `./scripts/build_app_bundle.sh`.
   Confirm the `Signing with:` line is not `adhoc` before relying on TCC
   persistence.
3. Start a Mic+Speaker session in the packaged app. Disable LLM by leaving the
   Endpoint URL and Model Name empty, or by setting summary and format intervals
   to 0.
4. Play the known system-audio fixture while the known local participant/source
   is captured by the microphone. In Mic+Speaker mode the packaged app writes
   lane WAVs under the session output directory:
   `<session_output_dir>/dual_lane_audio/remote.wav` and
   `<session_output_dir>/dual_lane_audio/local.wav`.
5. Copy those real lane WAVs into the case directory as `remote.wav` and
   `local.wav`. Do not replace them with generated or synthetic audio.
6. Record the packaged app path, session output directory, shared start
   timestamp, and any measured `capture_start_offset_sec` in `manifest.json`
   and `capture_notes.md`.
7. Write one JSONL reference per lane with `speaker`, `text`, `start`, and `end`
   fields.
8. If headed browser validation is used, close the browser/page before the run
   is considered complete and mention cleanup in `capture_notes.md`.

Use `python3 scripts/scaffold_dual_lane_fixture.py --case-id <case_id>` to add a
new case directory and manifest entry without fabricating recordings.
