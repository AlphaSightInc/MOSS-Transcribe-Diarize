# WP55a-P File conflict-policy prototype

Status: **COMPLETE — GATE FAIL; no production implementation permitted.**

## Contract

- **Question:** when interval evidence disagrees with pooled File identity, which
  smallest policy preserves pooled evidence without surrendering source-backed repair?
- **Minimum primitives:** pooled label and score; interval label and score; abstention;
  source-owned person/time; explicit composite-splice provenance.
- **Invariants:** words/times unchanged; fixed 0.35 score and 0.1 margin unchanged;
  unknown separate from wrong; every person's denominator retained; no aggregate-only win.
- **Unknown:** full MP3/M4A raw window responses were not retained. Their comparison is
  therefore a retained-transcript counterfactual with fresh CPU ONNX vectors, reported
  separately from exact raw-window controls.
- **Falsifier:** no policy passes both five-second violations plus every codec/person
  gate, or exact raw-window and retained-transcript evidence disagree on the decision.
- **Tool:** production CPU ONNX and retained media/transcripts answer identity policy;
  no decoder, network, or GPU call can improve this gate.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
prototypes/identity/file_policy_compare.py
```

## Verdict

**No policy qualifies. WP55a-I must stop.**

- **P0 current:** fixes much wrong-person time, but reproduces both 5-second
  violations, retains 9.45/9.30/7.56 seconds WAV/MP3/M4A correct→unknown, and
  flips 1.80 M4A seconds at three documented splice seams.
- **P1 abstain-only:** refuses cross-person moves, but still loses the same
  correct→unknown time and fails synthetic CASE 1.
- **P2 current fallback:** removes correct→unknown and retains repair, but still
  publishes synthetic CASE 2 as the wrong person. It is not eligible for WP55a-I.
- **P3 pooled margin (b′):** fixes both synthetic violations and all
  correct→unknown/splice flips, but refuses every measured wrong→correct move.
  Full retained wrong-person time is unchanged from baseline: WAV 92.04 s,
  MP3 222.63 s, M4A 92.40 s; 6-minute WAV 15.84 s. It therefore fails the
  every-codec wrong-time reduction gate.

The exact raw-window production-seam replay agrees: 30-minute WAV keeps
92.01/92.01 seconds wrong, with 0/13 cross-person repairs admitted; 6-minute WAV
keeps 15.93/15.93 seconds wrong, with 0/1 admitted. P0 reproduction matched the
production resolver exactly in both fixtures.

The one defined hole fired once in 30-minute WAV: the swept `current` label was
absent from that window's pooled scores, so P3 kept `current` as required.

All policies kept words/times identical and retained every person's fixed source
denominator. The three M4A correct→wrong rows—539.4–540.0, 1019.4–1020.0 and
1499.4–1500.0 seconds—are retained and reported as splice-seam rows, never dropped.
The 30-minute composite repeats 120 seconds; its recurring evidence is effectively
two source halves, not 15 independent observations.

Evidence: `file-policy-results.json` and
`../../evidence/round3/wp55a-p/file-policy-results.json`. Production source was
unchanged; decoder/network/GPU requests: 0.
