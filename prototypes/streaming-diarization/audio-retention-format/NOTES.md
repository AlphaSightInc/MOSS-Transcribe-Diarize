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

The rewritten probe imports and calls production `MeetingAudioArchive` and `MeetingHandle`; it no
longer carries a second publication or reconciliation implementation. Its printed state explicitly
records the structural question, minimum primitives, invariants, assumptions/unknowns, falsifier,
and tool decision. Real FFmpeg 8.1 produced a 6,741-byte MPEG Layer III file at 16,000 Hz, mono, and
48,000 bit/s at stream and every packet. Root, Account, and Meeting directories were `0700`; the
file was `0600`; transcript truth was unchanged. The production hierarchy trace before metadata was
exactly root-parent, root, Account, Meeting: each newly created child entry was fsynced through its
parent, followed by final-file fsync through Meeting.

Formal review exposed that the old proposal let the long-file window extractor choose a container's
default stream while terminal MP3 publication independently forced `0:a:0`. The extended probe used
a supported 151-second Matroska source whose first stream was 440 Hz and whose second/default stream
was 880 Hz. It measured the source selections as 440 Hz versus 880 Hz. One transient 16 kHz mono PCM
WAV made with the existing default-stream semantics then measured 880 Hz; the 150-second inference
window extracted from that WAV and the retained MP3 both measured 880 Hz. The shared-mix invariant
passed 3/3 consumers. The corrected policy is therefore one canonical working WAV before inference;
both direct/windowed inference and terminal encoding consume that exact one-stream artifact. If mix
preparation fails, transcription may still consume the original source, but retained audio is
explicitly `unavailable` rather than independently selecting another stream.

The production discard path now owns unlink, verified absence, and parent fsync. The probe measured
three adversarial outcomes directly through it: post-replace cleanup failure returned typed
`MeetingAudioArtifactSurvives` and made unavailable ineligible; a size mismatch with successful
discard left no artifact and made unavailable eligible; a forced size-mismatch discard failure
returned the same typed survivor state and made unavailable ineligible. Production `MeetingHandle`
also measured both metadata-reconciliation outcomes: successful retry of the same known-valid
available metadata returned available, while a second failure propagated; both retained the MP3,
attempted exactly `available, available`, and committed unavailable zero times. The accepted rule is
one causal reconciliation, not a general retry layer: only production discard success permits
unavailable; surviving known-valid bytes permit one exact available retry; another failure leaves
the Meeting failed without audio metadata. An MP3 and durable unavailable never coexist.
