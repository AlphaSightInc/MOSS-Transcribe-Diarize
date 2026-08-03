# Capture-layout malformed-input policy probe

Question: at the real macOS capture boundary, which policy preserves truthful audio
when an `AudioBufferList` is malformed: fail closed, truncate to the shortest buffer,
or zero-fill missing channel tails?

Run from the repository root:

```sh
bash prototypes/capture-layout-policy/run.sh
```

The probe compiles the production `MOSSCaptureCore` sources with a throwaway driver,
constructs real `AudioBufferList` and `AVAudioPCMBuffer` values, invokes the production
copy/downmix seam, and prints every measured case. It does not install or mutate the app.
