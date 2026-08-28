# Audio-retention format measurement

## Question

For MOSS's retained 16 kHz mono mixed meeting audio, what on-disk size and local conversion
time does WAV PCM16 or constant-bitrate MP3 actually produce on the real five-minute speech
corpus?

## Run

```bash
python3 prototypes/streaming-diarization/audio-retention-format/measure.py
```

The command transcodes eight real five-minute MOSS benchmark recordings into a temporary
directory, prints the complete input/output and wall-time state as JSON, and removes the
temporary files.

Terminal publication and cleanup policy use a separate one-command falsifier:

```bash
uv run --frozen python prototypes/streaming-diarization/audio-retention-format/publication_probe.py
```

It generates a disposable stereo WAV plus a 151-second two-stream source, measures the shared
canonical mix across the long-window inference and retained-MP3 paths, performs real FFmpeg atomic
publication, probes metadata/modes/surviving paths, then forces encoding and post-replace storage
failures plus metadata/removal reconciliation and prints transcript/artifact/cleanup state. All
files remain temporary.
