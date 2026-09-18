# Capture setup error ownership (WP27)

The microphone and shared-audio actions complete independently. One status string
cannot retain both failures: an early Share fails synchronously, then microphone
success can overwrite its explanation while the panel remains in error state.

ControlPanel keeps one error per lane until Reset. Existing error text is retained,
with the lane name and Reset instruction rendered together. Progress copy remains
separate. An error clears displayed meters and prevents subsequent setup frames
from making those meters or readiness appear healthy. Reset clears both errors.

The current CaptureClient reference owns asynchronous results. After Reset, a
retired setup cannot update the panel; any late acquired resources are closed or
stopped. This uses existing client cleanup and changes no capture protocol,
readiness threshold, identity policy, or backend lifecycle checks.

Measured prototype: baseline 9 failed / 10 scenarios; candidate 10 passed / 10.
The real client makes zero chooser calls while the initial microphone is pending;
chooser cancellation in that interval is unreachable. Rejection after microphone
attachment, both failed lanes, pending setup followed by Reset, and successful
readiness are exercised with simulated devices and the real client.

The prototype was absorbed into `ControlPanel.captureFailure.test.tsx`, with four
additional regressions for retired failures after a fresh setup and late chooser
resolution/rejection after Reset. Commands, state traces, limitations, and failed
attempts: `evidence/mvpfix/wp27/NOTES.md`. Physical-device behavior is unmeasured.
