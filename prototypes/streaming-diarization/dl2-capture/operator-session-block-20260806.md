# DL2 prepared session block — 2026-08-06

**PREPARED ONLY. Do not record until the supervisor gives an explicit GO and the operator completes a fresh pairing.** Existing capture-window logic remains fail-closed; this preparation adds no capture authority. Test/consented content only. Operator owns headphones, output selection, volume, TCC, playback, and every click.

**Required before every pairing/preflight in the Aug-8 block, and again after any AirPods reconnect:** open System Settings > Sound. Set **Input = MacBook Pro Microphone** and **Output = AirPods Pro**. macOS auto-switches input to AirPods on connect; never assume it stayed correct. The harness re-verifies both defaults and aborts before capture if either is wrong.

Raw for `CAL-HP`, `S06`, and `S05` is retained locally and remotely only until **23:05 EDT**, inside the existing 24-hour/2GB grant. Derived ASR/audit artifacts are sealed immediately. At sprint close run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 capture_harness.py cleanup --session-dir <session-dir>
```

New preflight refuses while any retained raw is overdue. Start no session too late to finish and clean by 23:05 EDT.

## CAL-HP — 60-second headphone calibration

Prediction: with interview speech playing through operator-worn headphones, the digital system lane carries full-level speech and the microphone lane contains room noise only. This validates headphones as structural acoustic-bleed elimination; it does not test echo cancellation.

Before pairing: operator selects headphones as output, puts them on, confirms interview speech is audible only in headphones, and stays silent. Keep interview playing through silent preflight.

- **RECORD / 00:00:** keep interview playing; operator remains completely silent.
- **00:15:** supervisor checks capture remains live; operator does nothing.
- **00:45:** keep interview playing; operator remains silent.
- **01:00:** supervisor runs finish automatically. Operator must not speak a stop cue.

Pass only after post-session signal/ASR confirms system speech and microphone room-noise-only. If microphone contains intelligible interview speech, headphones do not eliminate the path; stop the block for review.

## S06 — same speaker across lanes, 10 minutes

Source: operator's own consented S01b-era voice or another self-recording on the system lane. Use headphones if CAL-HP passes. Operator's live voice stays on microphone.

- **00:00–02:00 — LIVE ONLY:** self-recording paused; operator speaks normally on microphone.
- **02:00–04:00 — RECORDING ONLY:** operator silent; play operator self-recording on system.
- **04:00–06:00 — TRANSITIONS:** alternate 20–30s live and recorded turns; no overlap.
- **06:00–07:00 — SAME-VOICE OVERLAP:** operator talks over their recording.
- **07:00–07:15 — CONTROLLED GAP:** pause playback; operator silent for 15s.
- **07:15–08:00 — QUIET REGISTER:** operator resumes softly. This tests the recorded D2 hypothesis: gap >10s plus register drop may re-birth identity.
- **08:00–09:30 — REPEAT:** normal-volume live/recorded alternation, then one 20s overlap.
- **09:30–10:00 — CLOSE:** pause playback; say “S06 closing”; at 10:00 say “stop S06.”

### S06R single retry amendment — Aug 8

Before pairing, play the self-recording and require the operator to confirm it is audibly coming through AirPods; only then pause it. Recheck Sound input is MacBook Pro Microphone. Pair once. At each play cue, require an immediate audible-playback confirmation; abort rather than continuing solo if playback is absent. This is the only authorized S06 retry.

## S05 — same-gender remote, 15 minutes

Use one consented interview speaker matching the operator's gender. Use headphones if CAL-HP passes.

- **00:00–03:00 — REMOTE ONLY:** operator silent; remote interview plays.
- **03:00–06:00 — LOCAL ONLY:** pause remote; operator speaks normally.
- **06:00–09:00 — ALTERNATE:** 30–45s remote/local turns without overlap.
- **09:00–12:00 — OVERLAP:** three 20–30s natural overlaps separated by clean turns.
- **12:00–12:15 — CONTROLLED GAP:** both sources silent for 15s.
- **12:15–13:00 — QUIET LOCAL:** operator resumes softly to probe gap/register re-birth.
- **13:00–14:30 — NATURAL:** normal-volume alternation plus one final overlap.
- **14:30–15:00 — CLOSE:** pause remote; say “S05 closing”; at 15:00 say “stop S05.”

For every shape: visible supervisor countdown only; begin must pass both lanes=`capturing` and deployed revision `9089b332` before **RECORD**; finish immediately after final cue; run post-session ASR/audit immediately; do not delete raw before the 23:05 cleanup command.
