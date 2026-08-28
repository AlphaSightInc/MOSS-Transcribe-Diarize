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

It calls the production archive/Meeting handle on a disposable stereo WAV and 151-second two-stream
source, measures the shared mix, exact MP3, hierarchy fsync order, post-replace survivor, size-
mismatch discard/survivor/unobservable outcomes, and both metadata retries. Printed JSON includes
every structural-contract field and complete artifact/metadata state. All files remain temporary.

The Stop/persistence ordering falsifier runs the same production HTTP path under both supported
Python scheduling behaviors:

```bash
for python_version in 3.10 3.12; do uv run --python "$python_version" --frozen --extra dev python prototypes/streaming-diarization/audio-retention-format/stop_tail_order_probe.py; done
```

It prints the rejected no-latch result, the production intent-latch result, complete durable/public
Meeting state, and the in-flight-only concurrent/sequential/timeout lifecycle. All databases and
audio artifacts remain temporary.
