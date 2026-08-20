# Native signal observability prototype

Question: can one bounded pass over the exact strict-v2 PCM16 wire bytes expose enough per-lane
state to distinguish flowing silence or near-silence from usable audio, without retaining audio or
selecting a level threshold?

Prototype command used for the recorded verdict (throwaway source absorbed and deleted):

```bash
swift prototypes/native-signal-observability/probe.swift
```

Pre-registered checks:

- Digital silence is represented by JSON-safe `null`, never infinity.
- Full-scale PCM is within 0.001 dB of 0 dBFS.
- A half-scale signal present for half a frame is -9.0309 dBFS.
- Session maximum frame RMS survives a later silent frame.
- Malformed wire bytes increment a counter without overwriting the last valid state.
- One 8,000-sample wire frame costs less than 1 ms on this Mac.

No warning threshold, gain, normalization, lane policy, or product verdict is selected by this
prototype. Record the measured result below, then absorb the validated math into production tests
and delete `probe.swift`.

## Verdict

PASS on 2026-08-19. All six pre-registered checks passed. Exact vectors:

- Digital silence: `lastFrameRMSDBFS=null`, `silentFrames=1`.
- Positive full scale: RMS/peak `-0.0002650764 dBFS`.
- Half-scale for half a frame: RMS `-9.0308998699 dBFS`, peak `-6.0205999133 dBFS`.
- Quiet/loud/silent/malformed session: 3 analyzed frames, 24,000 analyzed samples, 1 silent,
  1 malformed, retained maximum frame RMS `-11.9999466654 dBFS`.
- 2,000 production-size 8,000-sample frames: 664.521 ms total, 0.332260 ms/frame.

Verdict: aggregate state and exact vectors are absorbed into `CaptureSignalLevel.swift` and
`CaptureSignalLevelTests.swift`. The same-user local control status exposes them; the server
heartbeat does not. Throwaway `probe.swift` was deleted. No level threshold or audio policy is
authorized.
