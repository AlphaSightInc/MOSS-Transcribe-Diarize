# Actual background capture — 2026-09-11

Question: does a hidden workspace's helper expire under real browser timer
throttling? Minimum primitives: active audio worklet, helper pulse, browser
visibility, server lease. Invariants: unchanged capture lanes, frame chronology,
server lease and Stop/finalization. Unknown: five-minute intensive throttling and
operating-system sleep; this experiment does not measure either.

Hypothesis: audio-worklet-driven heartbeats survive ordinary hidden-tab timer
throttling. Falsifier: actual hidden capture exceeds the 30-second lease or fails to
finalize. Merely dispatching a visibility event is insufficient evidence.

Playwright's bundled driver forces focus emulation, and Chromium launch defaults
disable background timer throttling. Leaving either enabled produces a misleading
background test. `driver.py` copies the installed Playwright package into a temporary
directory and disables its single focus override there; it never changes the shared
installation. The probe also removes Chromium's three background-disable switches,
asserts real `document.visibilityState == hidden`, and measures a 100 ms timer.
A changed driver override fails explicitly instead of silently weakening the test.

```sh
.venv/bin/python prototypes/streaming-diarization/background-capture/measure.py --corpus /path/to/corpus/mono_javier_intro_50s --output /tmp/background-45s
```

Uses the existing E2E harness's fresh workspace and two-source fake-audio capture,
with a separate labelled background probe (not a replacement network-row verdict).
Runs headed against https://127.0.0.1:17861. Bring the source tab forward, leave the
workspace genuinely hidden for 45 seconds, restore it, then Stop normally.

`results.json`: **45.012 seconds hidden**, 90 successful heartbeats, 180 frame
responses, largest observed heartbeat gap **0.506 seconds**. The nominal 100 ms
page timer ran 46 times, median **999.55 ms**, maximum 1008.10 ms: real 1 Hz
throttling occurred. Capture and session remained active; Stop reached completed
Meeting / final transcript.

Verdict: existing browser mechanism passes; no product change warranted.
`captureClient.ts::onWorkletFrame -> queueHeartbeat -> scheduleHeartbeat` drives
presence from audio samples, not a periodic workspace timer. It still uses main
thread message handling/network I/O: this is not a claim of immunity to arbitrary
page suspension. Existing local stack b76b5b5c, 30-second lease, no restart/reset.
Only content-free result retained here; temporary screenshots/audio/cookies excluded.
