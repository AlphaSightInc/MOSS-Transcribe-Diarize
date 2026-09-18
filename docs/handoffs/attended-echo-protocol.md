# Attended speakers/AEC measurement — UNMEASURED

**Decision P4 remains open.** Synthetic correlation did not safely separate quiet local
speech from playback. Production reports statistics; it never suppresses suspected leakage.
No physical microphone was available to WP3. This kit has not been run with a microphone.

1. **A1 — Prepare.** Human operator uses physical speakers and Chrome on their own machine.
   Keep speaker volume, microphone position and OS gain fixed. Use a public playback clip
   with its exact printed transcript. Close other microphone apps. In the WP3 checkout run
   `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> scripts/attended-echo/measure.py serve`.
   Open `http://127.0.0.1:18733/capture.html`. Start is a human click; select the playback
   tab and enable shared audio. This standalone recorder creates no MOSS meeting.
2. **A2 — Record six conditions.** For each AEC setting (on, off), record playback/operator
   silent, operator reading alone/playback paused, and both together. Use the same complete
   short playback excerpt (under 60 s). Read the displayed phrase once per recording:
   “The quiet blue river passes seven old bridges while the morning train carries fresh
   oranges into town.” Stop saves a JSON containing aligned 16 kHz per-lane PCM, block
   timestamps, RMS meters, requested AEC and actual browser track settings. Keep files
   private, outside git. Confirm the actual echoCancellation setting matches the request.
3. **A3 — Score.** With an authorized decoder endpoint and loopback tunnel, run
   `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> scripts/attended-echo/measure.py score <recording.json> --playback-text <exact-text.txt> --base http://127.0.0.1:18103/v1 > <private-score.json>`.
   It makes at most three sequential requests (system, mic, production-style mono mix).
   It reports ordered word error rate (edit distance/reference words), unique word retention,
   emitted-word counts, timing, and per-span playback explained energy/delay/gain. No transcript
   text is printed. Compare echo-only mic output to playback, not just its word count:
   matching words indicate leakage; unmatched words need inspection for hallucination.
4. **A4 — Decide and stop.** Compare near-alone versus both, with identical AEC settings;
   compare mic versus mono on the same recording. Report omissions/extra words from the
   ordered scores, loudness, actual settings, duration, and the exact six denominators.
   Missing or dropped blocks invalidate timing claims; inspect saved block clocks/meters.
   Human judgment remains necessary where playback and phrase share vocabulary. Do not
   call a low WER a physical qualification of other devices. Stop server with Ctrl-C and
   close the page/tunnel. Keep P4 open if quiet speech or leakage remains unresolved.

There is **no detector switch to enable**: WP3's candidate failed, so only telemetry ships.
A later attended result may justify a new prototype/policy; it does not authorize suppression.
Production `/snapshot.capture_guard` reports the latest committed aligned span; polling can
miss intermediate spans. The kit records every audio block for the attended measurement.
