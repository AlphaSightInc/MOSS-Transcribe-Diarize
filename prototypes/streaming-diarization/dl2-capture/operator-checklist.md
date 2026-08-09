# DL2 sprint operator card

**Every pairing/preflight, including after any AirPods reconnect:** System Settings > Sound → Input: **MacBook Pro Microphone**; Output: **AirPods Pro**. macOS may auto-switch input to AirPods. Harness re-verifies and aborts on mismatch.

Window: **Aug 5 21:50 ET → Aug 6 07:50 ET**. Test/consented content only. Harness never changes TCC, volume, source routing, or services; the operator owns every click.

Before each session: tell implementer the shape ID; confirm both source meters move; set volume/routing in the app; say “content consented”; start a rough cue log. Pair once, start consented background music on the system lane, then remain silent while the implementer runs `begin`. `begin` polls for at most three seconds for both lanes to reach the production `capturing` state, then verifies the deployed descriptor; any failure stops immediately before speech. Keep music playing until the implementer reports `PASS_BEFORE_OPERATOR_SPEECH` and says **RECORD**. After the timer, implementer runs `finish` then the one-command audit pipeline. Do not begin another session until both lane tapes passed and raw cleanup is confirmed.

| Order | Shape | Capture | Cumulative incl. 5m setup | Operator cues |
|---|---|---:|---:|---|
| 1 | S01 basic pilot | 10m | 15m | One remote voice on system; speak locally on mic; overlap twice; say lane/time cues aloud. |
| 2 | S03 two remote speakers | 15m | 35m | Two remote voices alternate; speak locally; overlap each remote once. |
| 3 | S05 same-gender hard class | 15m | 55m | Choose matching-gender remote voice; alternate, then overlap naturally. |
| 4 | S06 same-speaker cross-lane | 10m | 70m | Speak live, then play your consented recorded voice on system; include transition + overlap. |
| 5 | S08 long realistic | 30m | 105m | Two system voices; realistic agenda/turn lengths; natural crosstalk. |
| 6 | S09 missing-lane control, if time | 5m | 115m | Mute mic with normal app control; call out mute/unmute timestamps. |
| 7 | S10 wrong-lane control, if time | 5m | 125m | Change routing with normal app controls; call out switch timestamps. |

Pilot S01: pair once; play consented background music on the system lane; operator remains silent while implementer runs `begin`. If no **RECORD** cue arrives, stop—do not speak. On **RECORD**, stop/reset the music and start timer: 00:00 say “S01 basic pilot, microphone lane”; 00:30 confirm both source meters move and say “both lanes present”; 02:00 speak locally for 60 seconds with remote paused; 04:00 play the consented remote voice for 60 seconds while remaining silent; 06:00 speak over the remote voice for 15–20 seconds; 08:00 repeat a 15–20 second overlap; 09:30 say “S01 closing”; 10:00 tell implementer “stop S01.” If either lane meter is absent, say “abort S01” and stop—never improvise around the rail.

Audit: listen only to orange `LISTEN` rows in `derived/audit-packet/audit-rows.html`; attest lane, speaker, words, and approximate timing. Green `AGREE` rows remain spot-checkable.
