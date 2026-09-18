# F1: exact window, incomplete reference

The harness sends the first 25 seconds of Keyu PCM (400,000 samples), not an
energy-gated half-active 24-second stream. Idle frames are exact zeros and marked
silent. Microphone gain is 0.03 (-30.4576 dB), not -10 dB.

Reference omitted five words: **Kind of the same thing.** Source evidence:
`prototypes/streaming-diarization/data/real/benchmark_5m/lex_keyu_jin/reference.jsonl`
(first-party local corpus, 97–140 second Keyu paragraph): “…Chinese government,
it's kind of the same thing. There's paternalism…”
Historical independently retained whole-file decode at
`evidence/live-surface-optimization-20260825/pass-A-lex_keyu_jin_5m/file.jsonl`
places this sentence at 114.81–116.04 seconds and paternalism at 116.07–118.02.
The 60-second clip begins at 115 seconds in that source. Source original reference
`benchmark_diarization_1min/samples/lex_keyu_jin/reference.jsonl.orig` contains the
preceding paragraph too: it was trimmed too far when creating the short reference.

WP17 standalone decode of exactly the played 25-second PCM, with no lane merge,
produces the same five leading words at gain 0.03 AND gain 1.0. At 0.03 all ten
additions match the saved two-lane output. Thus no cross-lane producer is needed.
The other five additions (four fillers and a repeated “deference”) remain scored:
no human acoustic adjudication is claimed. At unity gain only the repeated
“deference” remains beyond the five proven missing words. No gain/policy change.

The fixture corrects only the five source-supported words. The immutable historical
corpus/manifests and all quality predicates remain unchanged. Counts: original
48 reference / 58 observed / 10 additions -> corrected 53 / 58 / 5 additions,
WER 20.8333% -> 9.43396%. Both saved/reopened cases contain the identical mic text.
“Kind” and “same” cease being falsely treated as system-exclusive vocabulary;
this also removes the two false attribution counts and associated duplicate counts.
Raw diffs: retained-transcript-diffs.json (public source text only). Full current
producer traces and raw responses remain ignored under runs/wp17/.
