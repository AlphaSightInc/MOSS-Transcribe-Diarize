# Headed S9 admission and exact-lane driver

- Two UI setup attempts, 0 admitted sessions, 0 decoder requests.
- Product reason retained on attempt 2: `No microphone sound was detected`; both lane meters must register sound.
- Supplied `microphone.wav` is 300.0 s of digital zero; changing it would change the S9 input.
- Replacement qualification path creates one live session through `/api/live/sessions`, sends both exact WAVs as production 0.5 s live frames, and uses headed muted Chromium to observe the API and rendered transcript.
- Chromium arguments are exactly `--mute-audio`; no physical capture is opened.
- Driver controls: `13 passed`; exact mono/16-bit/16 kHz/300 s input is enforced, frame lane/sequence/timestamp/PCM/silence fields are asserted, and wrong duration is rejected.
- Before the retained run: proxy receipt absent/empty; vLLM running `0`, waiting `0`, stop `48938`, length `368`, all failure counters `0`.
