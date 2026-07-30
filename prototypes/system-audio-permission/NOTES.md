# System Audio permission probe

## Question

Can the macOS client distinguish System Audio Recording denial from legitimate silence without a
private TCC API, an audible sound, or publishing probe audio?

## Measured result — M4MBP, macOS 26.5.2, 2026-07-29

- `AudioHardwareCreateProcessTap`, aggregate creation, `AudioDeviceStart`, and the IO callback all
  succeed while `kTCCServiceAudioCapture` is denied. The callback delivers only Float32 zeros.
- A private global probe tap plus a process-specific `.muted` tap around a delayed child signal
  separates the states:
  - denied: 144 callbacks, 147,456 samples, 0 nonzero, peak 0;
  - granted, external program: global and mute taps each saw 237,532 nonzero samples;
  - granted, delayed child signal at normal output volume 38: global and mute taps each saw 96,098
    nonzero samples, peak 0.030001.
- The operator heard no tone in the normal-volume delayed-child run.
- `kAudioHardwarePropertyProcessInputMute=0` and
  `kAudioHardwarePropertyProcessIsAudible=1` in both permission states, so those public HAL
  properties are not permission preflights.

## Verdict

Start success is not authorization evidence. Production admission must run the measured dual-tap
probe asynchronously, keep the system lane pending while macOS owns the prompt, admit only after a
nonzero probe observation, map all-zero delivery to permission denial, and keep probe buffers out of
the production queue. The child signal waits until its process-specific mute tap is reading; stop
cancels the generation so a late answer cannot start capture.

If the microphone is already recording, `start` returns while the system probe remains pending. If
no lane is recording, `start` waits for the machine-bounded probe (one-second process-registration
bound plus five-second helper bound plus one second for classification) before answering. This
prevents a zero-lane capture from returning success and then becoming terminal asynchronously. The
real-process UDS regression initially exposed that false-success path as a subsequent HTTP 403; the
bounded admission rule restored its expected typed start failure.

The throwaway `/tmp/moss-dual-tap-permission-probe.swift` was absorbed into
`SystemAudioPermissionProbe.swift` and the app executable's child mode.

## Probe-signal handshake hardening — 2026-07-30

The original child waited 1.2 seconds before playing. Five M4MBP measurements put mute-tap first
callback at 135–149 ms, leaving about 1.05 seconds of margin, but a fixed delay was still a race.
The child now blocks on stdin after starting its audio engine. The parent writes one go byte only
after the process-specific muted tap's `AudioDeviceStart` succeeds; mute-tap failure and
cancellation close the helper without playing. The existing five-second helper timeout remains.
Driver-seam tests pin both the successful ordering and the no-go failure path.

## App lifecycle finding

The M4 operator also exposed a separate permission-workflow failure: System Settings correctly
warned that a running app must quit before an AudioCapture toggle takes effect, but MOSSCapture was
absent from Force Quit and Finder called it unresponsive. A live stack sample showed a healthy,
idle process blocked in the UDS `accept()` on its main thread. Because the bundle is an
`LSUIElement` application and never ran AppKit, `NSRunningApplication.isFinishedLaunching` was
false and an accepted terminate request did not exit the process.

Production now runs AppKit on the main thread and moves only the blocking UDS server to a background
queue. The Launch Services regression opens the real built bundle, crosses its authenticated UDS,
requires `finishedLaunching=true`, requests normal application termination, and requires the process
to exit within three seconds.
