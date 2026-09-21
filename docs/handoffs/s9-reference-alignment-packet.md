# S9 headed-trial reference-alignment packet

**Decision.** Use retained `interview_adam_frank_180s` (180.000 s; two speakers) for the 1–3 minute S9 headed trial. Its eight source rows are extracted at `evidence/round4/headed-session/s9-adam-frank-180s-source-rows.jsonl`; its 531-word human-work template is `evidence/round4/headed-session/s9-adam-frank-180s-word-end-template.jsonl`.

**Why this clip.** It is a complete, retained, 16 kHz, 180-second two-person interview with eight existing source-owned rows. It exercises speaker turns without borrowing the Jamie adjudication population.

## Attended task (R4-11 before R4-10 S9)

1. With speakers muted and headphones on, play this retained clip only in the attended sitting. For every template row, confirm the end of the spoken word against the audio; do not rewrite words, infer a time from the transcript, or mark an uncertain time as confirmed.
2. Fill `word_end_sec` in seconds from clip start and set `alignment_status` to `CONFIRMED`. Preserve row order, IDs, text, speaker, and phrase bounds. If a word cannot be located, leave its end `null`, status `UNCONFIRMED`, name the reason, and the S9 per-word result remains **UNMEASURED**.
3. Require each confirmed end to be finite, nondecreasing within its phrase, and within that row's `phrase_start_sec`–`phrase_end_sec`. The first word's derived start is the phrase start; every later word's derived start is the preceding confirmed end. No invented midpoint timing.

## Handoff format

The attended deliverable is the completed template JSONL: one object per word, for example:

```json
{"id":"adam-180-00:0","source_interval_id":"adam-180-00","speaker":"Adam Frank","text":"if","phrase_start_sec":0.0,"phrase_end_sec":21.0,"word_end_sec":0.42,"alignment_status":"CONFIRMED"}
```

R4-10 converts only an all-confirmed template to the headed instrument input: one JSONL row per word with the same `id`/`text`, `start` equal to phrase start or prior word end, and `end` equal to `word_end_sec`. Run `prototypes/headed-session/complete_s9_reference.py --completed-template <completed.jsonl> --output <instrument.jsonl>`; it rejects an unconfirmed, non-finite, out-of-bounds, or regressing word end. This gives `reference_words_from_intervals` one real source interval per word; passing phrase rows directly would assign every word the phrase end and cannot establish per-word latency.

**Schedule.** R4-10 must reserve the human alignment above as attended R4-11 work. The disposable CPython 3.12.12/SQLite 3.53.4 runtime at `/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python` now clears the prior host-runtime gate: the packaged candidate CLI and five-second headed synthetic control both passed there with zero remote requests. The public headed tool nevertheless requires exactly 300-second WAV inputs. R4-10 may score this confirmed 180-second speech reference inside a declared 300-second session padded only with digital silence; the 120 seconds add no invented speech reference. A decision claiming a 300-second speech denominator requires another full 300-second human alignment. The actual acoustic decoder path remains a separately attended local-HF measurement, not established by the synthetic control.
