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

# Microphone choice (issue #2)

Chrome's own pick is wrong on a Mac with an iPhone nearby. A request without a device id is
resolved by Chrome's per-profile ranking (`media.audio_input.user_preference_ranking`, updated
from the permission bubble and Chrome settings), not the system default, and on macOS it makes
Chrome probe every input, which wakes the phone (reported in electric-capital/quest PR #18, where
`deviceId: {exact: "default"}` did not). macOS itself can also make the Continuity
iPhone the system default input. So every microphone request names its device exactly, and the
page, not Chrome, decides which one (`frontend/src/capture/microphoneChoice.ts`):

1. the device the person picked in the dropdown, if present;
2. else the system default (Chrome's `default` alias), unless it is an iPhone;
3. else the microphone already open, unless it is an iPhone;
4. else the best other microphone by Chrome's macOS transport suffix: headset or external
   (`(Bluetooth)`, USB `(vid:pid)`, the jack's `External Microphone`), then `(Built-in)`, then
   the rest (virtual loopbacks such as BlackHole carry no voice); Chrome's order breaks ties;
5. else the iPhone, when it is the only microphone.

An iPhone is recognised by its label: macOS names a Continuity microphone after the phone
("Gao’s iPhone Microphone") and Chrome adds no transport suffix to it (Chromium
`core_audio_util_mac.cc` maps no Continuity transport). A phone renamed without "iPhone" is
not recognised.

Chrome hides device ids and labels until the site holds microphone permission. The first
Enable microphone then opens Chrome's `default` alias once to obtain it, stops it, and opens the
chosen device. That probe is the one time an iPhone default can still be touched; with a
remembered permission the choice is made before anything opens. Until labels are known the
dropdown is not shown; afterwards it names the device that is open, or the one Enable will open.

Headphones in or out (`devicechange`): during setup the lane follows the rule; a recording keeps
its microphone until the person picks another. A picked device that disappears falls back to the
rule and is used again when it returns. Unplugging the device that is open still ends its track,
as before: during setup that is "Microphone stopped." and Reset; in a recording the lane is sealed.

Measured on the MacStudio, Chrome 154, with throwaway probes (not retained): before
permission `enumerateDevices()` returns one audio input with empty id, group and label; after it,
the alias reads `Default - Virtual Desktop Mic (Virtual)` and shares that device's group id;
labels carry `(Virtual)`, `(Built-in)`, `(Aggregate)` suffixes. The rebuilt bundle in real
Chrome with relabelled fake inputs (default = iPhone) requested exact `default` then exact
built-in with permission hidden, and exact built-in only with it granted; the dropdown showed
`MacBook Pro Microphone (Built-in)` both times. Unmeasured: a physical iPhone's Chrome label, and
whether a track opened on the `default` alias follows later default changes (on macOS the lane
always opens a concrete device, so the page does not depend on it).
