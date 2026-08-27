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
