# Lane balance — harness and what is already known

## Why this exists

The operator's attended runs transcribe the shared lane cleanly and lose almost everything they say.
Their fifth run is the clearest evidence: from their own microphone only `嗯。`, `Yes.`, `Um.`
survived — exactly the short loud interjections — while the shared lane produced full paragraphs.
That is the signature of a lane buried in the mono mix, not a broken microphone. The microphone was
independently proven healthy at about -21 dBFS while both lanes ran together.

## The measurement that is still missing

Iteration 20 measured a 15.377 dB disparity, tried peer-RMS matching, measured WER +3.468 pp and
rejected it. **That rejection is not safe to rely on**: its fixture played the SAME audio in both
lanes, so matching levels just sums one signal with itself. The real condition is two DIFFERENT
speakers, where the quiet lane carries words that exist nowhere else.

`proto_lane_balance.py` is that experiment: `meet_k2_s0.wav` as the shared lane, `meet_k2_s1.wav`
attenuated to the measured -15 dB as the microphone lane, mixed through a faithful copy of
`live_mixer.py`'s soft-limited sum, under three policies (current equal gain, full rms match, half
match). It transcribes each lane clean first to get per-lane references, then measures what fraction
of each reference survives the mix. Microphone recall is the number that matters.

## Two facts about the runtime, learned the hard way

- **Audio longer than about 12 s does not return** through this deployment. A 12 s clip decodes in
  ~1.1 s; 25 s and 60 s clips never came back and left the server generating after the client was
  killed, which then queued every later request behind them. Keep clips short, and expect a stuck
  server for a while after a killed long request.
- Read and write PCM with `array`, never `struct.pack("<" + "h" * n, ...)`. Building a
  192,000-character format string stalls for minutes and looks exactly like a hung model call.

## Not yet run to completion

The harness has produced its two reference WAVs but no policy result yet, because the runtime was
still busy with those earlier long generations. Nothing here is a finding; it is a bed to run.
