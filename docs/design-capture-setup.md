# One-click Start (round 5)

Decisions: `docs/plan-r5-start-flow.md` (Q15–Q17, Start). This replaces the three-step setup ("Enable microphone" →
"Share audio" → "Start recording") and its per-lane error ownership (WP27).

**Structural question.** A recording takes up to two sources, each of which may be unwanted or unavailable, while the
server needs both lanes of a meeting attached. What is the least the browser must hold to start in one click?

**Primitives.**

1. *Source choice* — two booleans, "System Sound Output" and "Microphone", ticked by the person and remembered per browser
   (`lt:capture:sources`). It says what the next Start asks for; it is locked from the click until the recording ends.
2. *Lane* — one per source, always two per meeting. A lane is either *recorded* (fed by a device or a shared surface)
   or *silent* (fed zeros by the browser). Nothing else distinguishes them: same framer, same clock, same frames.
   A lane has no third, "failed" state: a recorded lane whose source stops becomes a silent lane.
3. *Start* — one sequential routine with one outcome: a recording with at least one recorded lane, or nothing.
   It is offered whenever nothing is running — on load, after a Start that recorded nothing, and after a recording
   has finished or was lost — so there is no Reset step between recordings.

**Invariants.**

- Chrome's share picker is requested first, inside the click, with nothing awaited before it (it needs the click's
  user activation); the microphone follows; the meeting is created only after both lanes are attached.
- A meeting is created only when at least one lane is recorded. A Start that records nothing releases everything it
  opened (tracks stopped, AudioContext closed) and returns to ready with at most one line.
- The meeting on screen (a finished recording, or one opened from History) stays until the next Start has created
  its meeting. Reset exists only while a Start is pending (an open picker, an unanswered prompt) and only cancels it.
- The browser never reports a lane as `failed`. The server seals a failed lane and then closes the meeting as failed
  instead of completed (`live_v2_session.stop`), so a source that stops must not cost the rest of the recording.
- A silent lane opens no device, has no track that can end, shows no level, and never raises the silent-microphone
  remedy (K1). Mute is offered only while the microphone lane is recorded: "unticked" and "muted" are different states.
- During a recording the boxes show the sources it really takes. The remembered choice changes only when the person
  ticks a box, or when a microphone found unavailable unticks itself.
- Echo cancellation is always on for the microphone. The page sends no `echo_mode`; the server accepts its absence
  and the Gemini runtime does not read it (`gemini_live_runtime.create` only validates it).

**Outcomes of one click** (Q16):

| System Sound Output | Microphone | Result | Line |
|---|---|---|---|
| shared with audio | opened | both recorded | — |
| shared with audio | unticked | system recorded, microphone silent | — |
| unticked | opened | microphone recorded, system silent, no picker | — |
| shared with audio | none / denied (a) | system recorded, microphone silent; Microphone unticks | Microphone unavailable |
| picker closed (b) | any | nothing starts | — |
| shared without audio (c) | opened | microphone recorded, system silent | System sound output not shared |
| shared without audio (c) | unticked, none or denied | nothing starts | No audio was shared — turn on “Also share audio” in Chrome’s picker |
| unticked | none / denied | nothing starts; Microphone unticks, Start is disabled until a box is ticked | Microphone unavailable |

A share that fails for any other reason, an attachment failure, a refused meeting (K7, K9) and an unreachable server
also start nothing and show the reason (K8). A source that stops between its attachment and the meeting starts
nothing and shows K3. Reset during Start retires it: whatever arrives late is stopped, and a meeting created after
all is stopped at the server.

**A recorded source that stops mid-recording** (Chrome's "Stop sharing", a closed shared tab, an unplugged
microphone): `CaptureClient.sourceEnded` connects the zero source to the lane's own framer, then disconnects the
ended source, so the framer never sees an empty input and the lane's sequence numbers, timestamps and `device_epoch`
continue. The panel shows "System sound output stopped." or "Microphone stopped." (K3), drops that source's level and the
controls that need it (Share again; Mute and the device dropdown), and shows its box unticked; the remembered choice
is untouched. The recording goes on with the other source — or with silence, if both have stopped — until Stop,
which completes normally. Stopping it automatically when the last source goes was not chosen: the person may be
about to stop anyway, and one rule ("a stopped source is silence") covers every case.

**Silent lane.** `CaptureClient.attachSilentLane` connects a started `ConstantSourceNode` with offset 0 to the
production `lane-framer` worklet in place of a `MediaStreamAudioSourceNode`. The worklet is unchanged and frames
whatever its input delivers on the AudioContext's `currentFrame` clock, so sequence numbers, timestamps and
`device_epoch` run exactly as on a recorded lane and the server accounts the time as silence — the same path Mute
uses, without a device. Measured, Chrome 154 headless, 16 kHz context, 8000-sample frames:

- Prototype (throwaway, absorbed into `captureClient.test.ts`): a fake-device microphone lane and a silent lane side by
  side for 10 s gave 19 frames each, first start frame 128 and last 144128 on both, step 8000, peak 0 on the silent
  lane, frame gaps 496–504 ms; a silent lane alone (no media stream at all) also gave 19 frames.
- Rebuilt bundle against a local server (provider blocked, $0): system-only 14 s — 28 frames per lane, the silent
  microphone's 28/28 `silent`, sequences contiguous, identical capture timestamps 0…13.5 s on both lanes, 0 non-200,
  every heartbeat `capturing`/`capturing`, no status line; microphone-only 12 s — 24 frames per lane, silent system
  24/24, no status line, no share label stored. Control: a recorded microphone that is digitally silent raised K1 at
  10.6 s. Falsifier that did not occur: a silent lane producing no frames, a different frame count, or K1.

Unmeasured: the cost of always-on echo cancellation to a voice heard through headphones (Q17); provider cost of a
silent lane on real Gemini (round-5 gate 2; lanes open provider sessions on voiced audio only).

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
Start then opens Chrome's `default` alias once to obtain it, stops it, and opens the
chosen device. That probe is the one time an iPhone default can still be touched; with a
remembered permission the choice is made before anything opens. Until labels are known the
dropdown is not shown; afterwards it sits under the Microphone box while that is ticked and names
the device that is open, or the one Start will open.

Headphones in or out (`devicechange`): before Start nothing is open (round 5), so the dropdown
follows the rule and rule 3 does not apply; a recording keeps its microphone until the person picks
another. A picked device that disappears falls back to the rule and is used again when it returns.
Unplugging the device that is open still ends its track; in a recording the lane is sealed.

Measured on the MacStudio, Chrome 154, with throwaway probes (not retained): before
permission `enumerateDevices()` returns one audio input with empty id, group and label; after it,
the alias reads `Default - Virtual Desktop Mic (Virtual)` and shares that device's group id;
labels carry `(Virtual)`, `(Built-in)`, `(Aggregate)` suffixes. The rebuilt bundle in real
Chrome with relabelled fake inputs (default = iPhone) requested exact `default` then exact
built-in with permission hidden, and exact built-in only with it granted; the dropdown showed
`MacBook Pro Microphone (Built-in)` both times. Unmeasured: a physical iPhone's Chrome label, and
whether a track opened on the `default` alias follows later default changes (on macOS the lane
always opens a concrete device, so the page does not depend on it).
