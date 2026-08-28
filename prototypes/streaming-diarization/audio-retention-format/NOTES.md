# Audio-retention format verdict

## Question

What measured per-hour size and local conversion time does WAV PCM16 or 32/48/64 kbit/s CBR
MP3 produce on real 16 kHz mono MOSS speech?

## Verdict

Measured 2026-08-26 with FFmpeg 8.1 on all eight real five-minute recordings under
`data/real/benchmark_5m`. Every input and output was 16 kHz mono; output files lived only in a
temporary directory. The one-command run printed every source/output probe.

| Format | Measured bytes/hour | Decimal MB/hour | Reduction vs WAV |
|---|---:|---:|---:|
| WAV PCM16 | 115,200,936 | 115.2 | — |
| MP3 CBR 32 kbit/s | 14,407,308 | 14.4 | 87.5% |
| MP3 CBR 48 kbit/s | 21,610,044 | 21.6 | 81.2% |
| MP3 CBR 64 kbit/s | 28,813,212 | 28.8 | 75.0% |

Local full-file encoding, including writing the output, was measured across all eight inputs:

| Format | Median projected encode time per audio-hour | Observed range |
|---|---:|---:|
| WAV PCM16 | 0.61 s | 0.58–1.19 s |
| MP3 CBR 32 kbit/s | 6.15 s | 6.07–6.38 s |
| MP3 CBR 48 kbit/s | 5.78 s | 5.50–5.92 s |
| MP3 CBR 64 kbit/s | 5.56 s | 5.28–5.98 s |

A required replay after the Wayfinder resolution measured 48 kbit/s at **6.48 s/hour median**
with a **6.05–6.99 s/hour** observed range. The two independent 48-kbit/s runs therefore have
medians of **5.78** and **6.48 s/hour**, with **5.50–6.99 s/hour** spanning every observation.
Host load affects the exact timing but not the decision: even the slowest observation encoded an
audio-hour in under seven seconds.

**Verdict:** MP3 conversion time is marginal on the measured MacStudio: roughly six seconds per
meeting-hour across two full runs, with a measured worst case below seven seconds. Production-
Windows-host conversion time is
**unmeasured** because that host's controlling charter makes it read-only. The operator selected
human playback/download as the archive's only purpose and delegated the bitrate judgment.

Select **MP3 CBR 48 kbit/s**, measured at 21.6 MB/hour. It avoids the most aggressive measured
choice (32 kbit/s), while 64 kbit/s costs 33% more storage without a selected exact-PCM or model
reuse purpose. Perceived quality was not measured; this is an explicit product judgment, not a
quality-gate result. The disposable listening clips were removed after the judgment; the reusable
one-command size/timing measurement remains in this bench.

## Terminal publication and cleanup

Measured 2026-08-27 with:

```bash
uv run --frozen python prototypes/streaming-diarization/audio-retention-format/publication_probe.py
```

The real FFmpeg 8.1 path converted a disposable 48 kHz stereo WAV to one MP3 reported by ffprobe as
MPEG Layer III, 16,000 Hz, mono, 48,000 bit/s. Every reported audio packet was 48,000 bit/s. MP3
duration was 1,000 ms; metadata byte count equaled the 6,741-byte file. Root, Account, and Meeting
directories were `0700`; the file was `0600`; the root-relative path was
`account-a/meeting-a/audio.mp3`. After terminal cleanup, that MP3 was the only surviving file.

Forced FFmpeg failure produced no staging/output/source files, selected explicit `unavailable`
metadata with no path/bytes/duration, and left the transcript document byte-for-byte unchanged.
Forced storage failure immediately after atomic replacement also raised explicitly, removed the
uncommitted final MP3, left zero Meeting files, and preserved transcript truth.
The accepted publication policy is therefore: encode to a same-directory staging MP3 with
`libmp3lame -b:a 48k`, validate the stream and packet contract with ffprobe, fsync and atomically
replace `audio.mp3`, durably commit metadata, then remove File working input. Metadata-commit failure
must remove the just-published MP3. Audio failure records `unavailable` after transcript durability
and never changes transcript success.
