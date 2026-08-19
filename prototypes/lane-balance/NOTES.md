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
`live_mixer.py`'s soft-limited sum, under preregistered policies. It transcribes each lane clean first to get per-lane references, then measures what fraction
of each reference survives the mix. Microphone recall is the number that matters.

## Preregistered comparison (before the first policy run)

Each preregistration fixes the candidates, metrics, and rejection rule. A candidate must gain
at least 5 percentage points of microphone recall and WER reduction, lose no more than 5 percentage
points of shared-lane recall, reduce quiet-lane missing words, and not increase the production-copy
limiter fraction. If neither raised-microphone arm passes every condition, the identity policy
stands. This one-corpus, synthetic-attenuation result cannot by itself authorize a production mixer
change or a Defect C warning threshold.

## Two facts about the runtime, learned the hard way

- **Audio longer than about 12 s does not return** through this deployment. A 12 s clip decodes in
  ~1.1 s; 25 s and 60 s clips never came back and left the server generating after the client was
  killed, which then queued every later request behind them. Keep clips short, and expect a stuck
  server for a while after a killed long request.
- Read and write PCM with `array`, never `struct.pack("<" + "h" * n, ...)`. Building a
  192,000-character format string stalls for minutes and looks exactly like a hung model call.

## First scored run — 2026-08-19

`evidence/phase1/g3-attended/iteration-2-lane-balance.json` is the one preregistered 12-second
run. It used the read-only local tunnel, whose sole advertised model was
`OpenMOSS-Team/MOSS-Transcribe-Diarize`. The WAV fixtures are intentionally ignored by Git and are
absent from this loop worktree, so the runner read them without copying from the canonical checkout
via `--fixture-root`; the artifact binds their SHA-256 values (`167cb9c0...2ba15b8` shared and
`bc0ec14d...c47854f` microphone) and the preregistration SHA-256
`2e03aa77...734f5381`.

| Policy | Mic recall | Shared recall | Mic WER | Missing mic words | Limited output | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Identity | 12.70% | 88.64% | 85.71% | 55 | 0.00% | baseline |
| Peer-RMS match | 66.67% | 72.73% | 84.13% | 21 | 0.00% | reject |
| Half match | 12.70% | 88.64% | 85.71% | 55 | 0.00% | reject |

Peer-RMS matching does recover 53.97 percentage points of microphone recall and 34 missing words,
but it loses 15.91 points of shared recall (more than the 5-point guard) and improves microphone
WER only 1.59 points (less than the required 5). Its actual gain is +25.742 dB from the attenuated
microphone input because this fixture's RMS imbalance is larger than the synthetic -15 dB attenuation.
Half matching changes none of the measured scores. No arm increased limiter use, but neither passed
every preregistered guard; retain identity and do not propose normalization, AGC, a fixed offset, or
a Defect C threshold.

This re-tests the old same-playback rejection on a valid different-speech bed. It remains only a
one-corpus, synthetic-attenuation, same-model-reference result; it cannot authorize a production
mixer policy or a Defect C threshold.

## v2 amendment — before the second score

`preregistration-v1.json` is immutable: the first result hash-pins it. Its +0, +7.5 dB, and
peer-RMS (+25.742 dB) arms left a meaningful gap: peer-RMS matches a naturally louder shared speaker,
not the clean microphone. `preregistration-v2.json` preserves the fixture, metrics, and all five
rejection guards, then adds exactly one arm: `restore_microphone_to_clean_level`, +15.0 dB
(gain 5.623413251903491). That exactly cancels this fixture's declared -15.0 dB synthetic
attenuation; it does not make the microphone as loud as the shared lane.

Validate and print the sealed state before the score:

```sh
python3 prototypes/lane-balance/validate_preregistration.py
```

The next permitted measurement is the existing runner using v2. It must report all four arms as a
gain-response curve, including that limiter engagement was zero in v1 and therefore its reject guard
was untested rather than passed. A v2 result still cannot authorize a production mixer policy or a
Defect C threshold without independently recorded varied lane-balance examples.

## v2 scored run — 2026-08-19

`evidence/phase1/g3-attended/iteration-2-lane-balance-v2.json` is the one real-vLLM score of the
sealed four-arm v2 contract (result SHA-256 `3721c46d...d2cb7db2`; contract SHA-256
`e58a8bbf...e0635fec`). It used the read-only local tunnel and the same ignored canonical fixture
root as v1. The exact +15.0 dB restoration arm is the important new point in the curve:

| Policy | Mic recall | Shared recall | Mic WER | Missing mic words | Limited output | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Identity | 12.70% | 88.64% | 85.71% | 55 | 0.00% | baseline |
| Half match (+7.5 dB) | 12.70% | 88.64% | 85.71% | 55 | 0.00% | reject |
| Restore clean level (+15 dB) | 12.70% | 86.36% | 85.71% | 55 | 0.00% | reject |
| Peer-RMS match (+25.742 dB) | 65.08% | 72.73% | 85.71% | 22 | 0.00% | reject |

Restoring exactly the synthetic attenuation costs only 2.27 percentage points of shared recall, but
recovers none of the quiet lane's clean-reference words. Peer-RMS recovers 52.38 points of microphone
recall and 33 missing words, but loses 15.91 points of shared recall and does not improve microphone
WER. Thus **no preregistered gain-only arm satisfies every frozen guard on this fixture**; the correct
verdict remains **RETAIN_IDENTITY**. The limiter was zero for every arm, so its guard was untested,
not a reason to accept a candidate.

This is a gain-response result for one synthetically attenuated, two-speaker corpus using same-model
references. It neither selects a production policy nor supplies a Defect C threshold. Any further
policy work requires varied, independently recorded lane-balance evidence and a fresh preregistration.
