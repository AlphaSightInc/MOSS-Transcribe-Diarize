# R5-F3: after Stop, clean-up loses words the live transcript had (2026-10-01) — fix prototype

Throwaway prototype on `gemini/r5-f3` (starts at R5-D's last commit, product code `gemini/r4-ui` @ 9a1ca171).
No product code or test is edited here. Evidence: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f3/`.
Diagnosis this builds on: `../NOTES.md` (R5-D), section "S3b".

## Contract (written and committed before any measurement)

**Structural question.** After Stop each lane has two transcripts of the same audio: the live one (already shown
to the user) and the whole-recording one (better speaker labels, long-range consistency). The whole-recording
answer replaces the live surface. What is the smallest rule that gives the user the better of the two without
losing speech either had and without showing the same speech twice?

**What the two requests are (read from the code and from R5-D's 53 recorded requests, $0).** The rolling-window
request and the whole-recording request are the same call: model `gemini-3.5-transcribe`, the same
`generation_config` (`verbatim`, word timestamps, speaker diarization), no instruction text (1 text token), no
language hint, no vocabulary. Only the audio differs (15 s refresh over a 90-300 s context, vs the whole lane up
to 900 s). So there is no "window wording" to copy; request-side candidates are the fields the request does not
use yet: `language_codes`, `custom_vocabulary`, `system_instruction`.

**Minimum primitives.**
- *Lane* — the rule never moves a word between lanes.
- *Timed word* — (text, start, end) as the provider returned it; both authorities are lists of timed words.
  Cannot be reduced to rows: a live row is many words, and a lost name is one word.
- *Hole* — a stretch of the lane's time line in which the whole-recording answer has no word.
- *Witness* — a live committed word whose own time span lies in a hole. It is the only evidence that the hole
  is an omission and not silence.
- *Comparable unit* (the project's rule: one per CJK character, other letter/digit runs whole) — used only to
  count what was kept, lost or doubled; the candidate rule itself should not need text comparison (to be tested).

**Invariants.**
- I-loss: a live committed word is in the saved transcript, or the whole-recording answer has a word in its time
  span (a replacement), or a counted gate removed it.
- I-once: no stretch of speech appears twice in the saved transcript.
- I-keep: every word the whole-recording answer returned keeps its text, time and speaker; rows stay sorted with
  one owner per interval.
- I-clean: words the whole-recording pass or its gates removed on purpose (echo, invented words, the duplicated
  character at a live window frontier) stay removed.

**Assumptions / unknown.**
- The real meeting's raw answers were not saved; why it lost 7 of 7 names and its punctuation is `unmeasured`.
- Fixtures are macOS text-to-speech Mandarin + public podcast/LibriSpeech English. Human code-switched Mandarin
  is not on disk: `unmeasured`.
- Round-4 fixtures' raw provider answers are not on disk (only saved rows); re-recording the 480 s listener
  fixture costs about $0.13, over a third of this cap. Real invented live words are therefore `unmeasured`
  unless a cheaper cell is found; recorded R5-D live defects and injected words stand in.
- Whether repeating identical request bytes gives independent draws is unknown; draws are made distinct by
  leading silence (R5-D's method).

**Hypotheses, in the order they are tested (stop at the first sufficient one).**
- H1 (request side): one of `language_codes`, `custom_vocabulary` (code-switched tokens taken from the live
  rows), `system_instruction` ("keep every word in the script it was spoken in; do not translate, drop or
  romanise names; keep punctuation") makes the whole-recording answer keep every live Latin token and keep one
  script, at no extra cost. *Falsifier:* any draw of the variant still loses an expected token (not reliable at
  the source), or the API rejects the field.
- H2 (witness rule): when the provider omits words it leaves a hole in its own word time line (first look at
  R5-D's recordings: the answer without "Media Lab 的" has no word 5.3-5.8 s; the live answer has three there).
  Rule H: live committed words whose span lies in a whole-recording hole are inserted there, when the uncovered
  run is at least `m` seconds; everything else stays as the whole-recording pass decided. *Falsifier:* an
  omission that leaves no hole (neighbours stretched over it), or restored words that double existing text, or
  recorded live defects restored, at any `m` that still restores the lost names.
- H3 (script): the script of the answer can be pinned by a request hint; otherwise the smallest behaviour is to
  accept, because the live rows themselves mix scripts between windows (R5-D's recorded meeting: window 1
  traditional, window 2 simplified). *Falsifier:* measured rates.

**Tool decision.**
- $0: R5-D's recorded answers replayed through the production classes (parser, repair, `TerminalTranscriber`,
  the whole lane engine via `../replay.py` composition). Decides H2 on every recorded pair and guards I-keep /
  I-clean. A recorded whole-recording draw at another leading silence is time-shifted to stand in as the
  clean-up answer of the same live sample (same audio, word times move by the silence difference).
- Paid, cap $0.35, public/synthetic audio only: request variants (H1, H3) — only the provider can answer; new
  live samples (two 15 s / 30 s window requests each) to widen H2's pairs; reproduction attempts for the total
  loss. Ledger check before each call (known + 1.25 x planned <= cap).
- Stopping rule fixed now: a request variant runs 5 draws on `sys-zhlatin-en`; if it loses an expected Latin
  token in 3 or more of the 5 it is not distinguishable from today (4-5 of 5) and stops; otherwise it runs to 10
  (5 more on `sys-zhlatin`). A variant the API rejects costs one call.

## Gates (fixed before measuring)

| Gate | Pass rule |
|---|---|
| G1 no loss | On every recorded and new draw: Latin tokens / names / digits present in the live rows are present after clean-up (kept / expected reported), and no voiced stretch >= 1 s that had live words is left without a row |
| G2 no duplication | Repeated-unit count of the saved lane text (units inside runs of >= 5 units that occur twice) is not higher than today on any pair; restored words never overlap a kept word in time |
| G3 improvements stay | Live defects clean-up removes today stay removed: the duplicated frontier character (system and microphone lanes), the mis-timed live word, echo / invented words where recorded. Every kept clean-up word keeps text, time and speaker; speaker error on the fixture with truth not worse by > .005; rows sorted, one owner per interval |
| G4 punctuation | Saved text has sentence punctuation where the live rows had it (marks per language, per draw), or the reason it does not |
| G5 script | Saved Chinese text uses the script of the live rows in N of N draws (N stated), or the measured remaining rate |
| G6 cost and latency | Added provider cost per meeting (about 0 for a request change; a retry doubles clean-up cost) and added wall time after Stop |
| G7 long meetings | State where the change sits relative to the chunk stitcher (`gemini_long_final.py`) and rule W; it must not change which speaker a kept word gets. Run on a chunked replay or mark UNMEASURED |

Reproduction target (R5-D could not): all names lost, punctuation lost. Variations to try: names at the very
start of the recording, Chinese then English in one short (40-60 s) recording, another Mandarin voice. Report the
rate, or UNMEASURED.

## Commands

```sh
PY=../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python; W=prototypes/gemini-live/mic-speaker-echo/f3
PYTHONDONTWRITEBYTECODE=1 $PY $W/run.py            # everything at $0 from recorded answers; prints every table (1-2 min)
PYTHONDONTWRITEBYTECODE=1 $PY $W/run.py --rerun    # also replays all 57 engine runs (~20 min)
PYTHONDONTWRITEBYTECODE=1 $PY $W/s6_patterns.py    # rule H on each recorded pattern (the regression-test seeds), 1 s
# paid (public/synthetic audio only; f3lib.check enforces known + 1.25 x planned <= $0.35), each through ../with_key.sh:
#   s1_request.py <fixture> <variant> <prefixes> --pay     one whole-recording request per draw
#   engine.py <run> <system.wav> [mic.wav|--silent-mic] --prefix P --record     live windows + clean-up of one meeting
#   s4_determinism.py --pay                                same request bytes twice
```

Files: `rule.py` is the rule (pure functions, the only part meant to be lifted out). `engine.py` is the product's
own engine composition with recorded provider answers (R5-D's `replay.py` method) plus three observation points.
`f3lib.py` paths, ledger, recording client, measures. `build_repro.py` / `build_invented.py` fixtures.

## Results (2026-10-01; spend $0.17 of $0.35; 62 paid calls; key scan 0 of 683 files)

The unpatched harness reproduces R5-D before anything was changed: its nine recorded meetings give byte-identical
live and saved transcripts (18 of 18 files), and its ten whole-recording draws give 8 of 10 without "Media Lab",
1 of 10 traditional, 7-8 punctuation marks, 0 words removed by parser, word gate or repair.

### H1 — fix it in the request: rejected (measured)

The window request and the whole-recording request are the same call (one `generation_config` across R5-D's 53
recorded requests, no instruction text). The three fields the request does not use:

| Request change | Result on the Chinese+names recording (names kept of 10, five leading silences) |
|---|---|
| today | 8, 8, 7, 7, 7 — every draw loses a name; traditional 1 of 5 |
| `custom_vocabulary` = the names the live rows held | API refuses: "custom_vocabulary is incompatible with word timestamps" |
| `system_instruction` (keep every word, do not drop names, keep punctuation) | API refuses: "Developer instruction is not enabled for this model" |
| the same instruction as a text part before the audio | accepted and ignored: 8, 8, 7, 7, 7 — the same omissions on all five |
| `language_codes` = cmn-Hans-CN + en-US | 10, 10, 7, 7, 7 — 3 of 5 still lose; traditional 3 of 5 (worse) |
| `language_codes` = zh-CN + en-US | 10, 10, 3, 7, 9 — 3 of 5 lose, one loses 7 of 10 names |

Every accepted variant met the stopping rule (3 or more of 5 draws lose a name) and stopped at 5 draws; none went
to the English fixture. Word times, speaker labels (1 label in the Mandarin passage, 2 in the English one) and
punctuation (7-8 marks) are the same in every variant. Cost of each: 0. A request change cannot make the answer
reliable; a language hint can make it worse.

Also measured: the same request bytes give the same answer, word for word with the same times (3 of 3 pairs of
independent calls). The variation R5-D saw comes from the audio bytes (length, leading silence), not from chance.
So the existing coverage retry (send the same chunk again after a >= 10 s gap) cannot return anything new; it only
doubles that chunk's cost and wait.

### Reproducing the total loss of names and of punctuation

| Condition (production request unless stated) | Answers | Names kept of 10 |
|---|---:|---|
| system-lane audio: R5-D's fixtures | 10 | 7-10 |
| names at the very start of the recording, then English (2 draws) | 2 | 9, 9 |
| another Mandarin voice (Meijia) | 2 | 10, 10 |
| pink noise under the speech at 10 dB / 5 dB | 2 | 6, 6 ("Google" became 工作 twice) |
| synthetic music under the speech at 10 dB; lane 25 dB quieter | 2 | 7, 7 |
| faint copies of the same speech (R5-D's recorded microphone-lane answers, echo at -25 / -40 dB) | 3 | 6, **0**, **0** |
| with a zh-CN language hint, clean audio | 5 | 10, 10, **3**, 7, 9 |
| with a zh-CN language hint, noise at 10 dB / 5 dB | 2 | **2**, **0** |

- All names lost: reproduced, but not at the production request on system-level audio (0 of 18 such answers lost
  more than 4). It appears on faint or noisy speech (2 of 3 faint copies; these answers were for the microphone
  lane and the echo gates removed them, so nobody saw them) and whenever the provider is steered to Chinese
  (3 of 10 zh-CN-hinted answers kept 3 or fewer). The provider has a mode that writes the Chinese and skips the
  code-switched words; what put the real meeting's answer in that mode is `unmeasured` (its audio is private).
- In every such answer the skipped names are **holes in the provider's own word times**: the neighbours keep
  their times and nothing is written in between: 85 of the 102 missing name tokens in the 32 answers for this
  audio; the other 17 have other text in their time ("Computer File", 工作).
  That is also what the real meeting shows: 2.0 s of voiced audio with no row between two rows of one speaker.
- Punctuation lost (real: 1 mark in 102 characters): **not reproduced**. 6-8 marks in the Mandarin passage in each
  of the 38 whole-recording answers for system-level audio, including the ones without names (5-7 in the faint
  copies). UNMEASURED.

### H2 — rule H (fill the provider's holes from the live words): works

**The rule in full.** Per lane, after Stop:
1. *Witness list.* The live words exactly as each rolling window committed them, with the provider's own times.
   When a later window commits a word that starts before that window's frontier (it straddles the frontier), the
   earlier window's words that overlap it, or that have the same text and end within one time step of its start,
   are dropped from the list (they are the truncated copy that makes the live frontier duplicate).
2. *Witness word.* A live word is a witness when the whole-recording words cover at most one provider time step
   (0.1 s) of it and not all of it. A zero-length provider word counts as one time step.
3. *Run.* Consecutive witnesses in the same hole form a run. A word at the edge of a run is dropped when the
   whole-recording word right next to it (within one time step) is the same word (same letters, or the same number
   written two ways): that is one word timed one step apart, not an omission.
4. *Restore.* A run with at least 0.15 s of uncovered time is inserted into the whole-recording words at its time,
   with the speaker label of the nearer neighbouring whole-recording word. Runs inside an interval the existing
   >= 10 s fallback already carries are skipped.
5. Nothing else changes: every whole-recording word keeps its text, time and label; the rule runs after labels are
   final (after the chunk stitcher / identity policy) and before the word gates, so restored words pass the same
   voice-activity gate and, on the microphone lane, the same echo and level gates as any other word.

**Parameters and margins.**
- 0.1 s time step: the provider's word times are multiples of 0.1 s in all 115 answers.
- 0.15 s minimum run: over 100 pairs every timing-jitter run is exactly 0.10 s (37 runs: 他, 和, 这, At, What,
  Why) and every other run is 0.20 s or longer (176 runs; the shortest real omission is "Media", 0.20 s); 0.15
  sits between. At 0.1 s the rule doubles a word in 8 of 100 pairs; at 0.3 s it starts to miss single names (6
  tokens against 4); at 0.5 s it misses 74 of the 115 lost name tokens.
- "at most one step covered": with "less than half covered" a 1.1 s live "Amazing." over the clean-up's 0.3 s
  "Amazing." was doubled in 18 pairs; with the absolute step it is not (0 pairs).
- same-word edge check: without it 37 doubled units (的 的, 院 院, 者 者); with it 0.

**Measured, $0, production classes.**

| What | Today | Rule H |
|---|---:|---:|
| 100 pairs (5 live samples x 20 whole-recording draws of the same audio): name tokens that live or clean-up had and the saved words lack | 115 in 47 pairs | 4 in 4 pairs |
| same pairs: units of the passage missing vs the script (mean of 115) | 3.25 | 2.06 |
| same pairs: extra units vs the script (doubled or invented), mean | 1.25 | 1.25 (0 pairs worse) |
| same pairs: doubled neighbouring units | 0 | 0 |
| whole engine, 25 distinct system-lane pairs: names kept of 250 (live had 230) | 185 | 236 |
| whole engine: pairs where the saved text has fewer names than the live rows | 15 | 0 |
| whole engine, 34 lanes (25 system + 9 microphone): every clean-up word kept with the same text, time, speaker | — | 34 of 34 |
| whole engine: row speakers unchanged; rows sorted; one owner per interval | — | 34 of 34 |
| whole engine: doubled units (live rows had 13: 议议, 前前, of of, 要要) | 0 | 0 |
| live words left without a saved word for >= 0.15 s (51 lanes incl. the cells below) | 42 lanes, longest 2.0 s | 0 lanes |
| the answer that lost every name (noise 5 dB + zh-CN hint): names in the saved row (live had 5) | 0 | 5 |
| injected 2.0 s omission (the real meeting's shape: two rows, 2.0 s of voiced audio without a row) | 2 rows, hole | 1 row, 13 characters restored |
| injected 1.5-1.6 s omission on the microphone lane, English and Mandarin | lost | restored, 13 of 13 words pass the microphone gates, frontier duplicate stays out |
| English 3-speaker meeting with exact truth, two leading silences: speaker error | .1217 / .1296 | .1217 / .0907 |
| chunked clean-up at small scale (25 s chunks, 5 s overlap, stitcher path): kept words and labels | 161 | 161 identical + 4 restored |
| mean clean-up wall time, 42 lane cells | 4.03 s | 4.11 s |
| rule time on a 2-hour lane (21,360 + 21,600 words, 120 holes) | — | 0.21 s |

What the rule restored, over all 45 rule runs (112 restored runs): names and words inside sentences (Media Lab 的
24, Grace Hopper 7, Alan Turing 7, Computerphile / Computer File 7, Microsoft, Hopper, carve outs, Cosette,
there.), "Yeah," 22, "uh I I" / "I I" 37 (speech at -15 to -23 dBFS that the whole-recording answer stops before),
and the three injected omissions. Largest distance from a restored run to the nearer kept word: 0.70 s.

**What rule H cannot do (each measured or stated).**
- It cannot restore what the live windows never had: 2 of 5 live samples lost "Media Lab" themselves.
- A replacement is not an omission: where the whole-recording answer wrote something in the same time ("Computer
  File" for "Computerphile", 工作 for "Google", 和作者 for 合作者) its version stays.
- A live word fully under a *different* neighbouring word is treated as replaced: "Lab" lost in 4 of 100 pairs.
- Punctuation that sits on a word both transcripts have is not carried over (the unreproduced real symptom).
- Script: restored words keep the live row's script; the injected 2.0 s case put 13 traditional characters into a
  simplified row. In the 25 engine pairs no saved text changed script (restored Chinese was 的).
- A live-only word that nobody said, in a stretch where the whole-recording answer is silent, comes back if it
  lasts 0.15 s or more (it passed the live gates). Two attack cells (20 s of music after speech; room events and
  echo residue on the microphone lane) produced 0 such words: the one invented live word ("Yeah." on a room
  event) is in the whole-recording answer too. Round 4's listener fixtures, where 3 invented words survived the
  live gates, have no recorded answers on disk and cost about $0.13 to re-record: UNMEASURED.
- Restored words take the nearer neighbour's speaker. Right in 2 of 2 with truth (Cosette, there.); "Yeah," went
  to the previous speaker's row in 17 of 22 runs, truth unknown.
- One character can be doubled when a hole's edge word is written differently by the two passes (traditional /
  simplified) and timed one step apart: 0 in 100 pairs and 34 engine lanes; the number case (10 / 十) occurred once
  and is handled.
- A frontier duplicate in two scripts (議 / 议) sitting exactly in a hole would be restored twice: 0 observed.
- The 0.1 s step is this provider's. The OpenAI-compatible provider path is unmeasured.

### H3 — script: no request fix; not solved here

- Whole-recording answers at the production request: traditional in 1 of 10 (R5-D's fixtures) and 8 of 18 over all
  fixtures (names-first 2 of 2, noise / music 3 of 3, Taiwan voice 2 of 2).
- A language hint does not pin it: 8 of 15 hinted answers are traditional; cmn-Hans-CN made the clean recording
  worse (3 of 5 against 1 of 5); zh-CN returned traditional on 5 of 5 recordings that were traditional without it.
- The live rows have no single script either: 3 of 7 live samples hold one row in each script.
- So "the script the live rows used" is not defined, keeping live rows would not make the text consistent, and the
  request cannot. Only converting the text can, which needs a conversion table or library and a chosen target
  script. Not added (the brief's bar: only if nothing else works — nothing else works). Decision for the user.

### Gate table

| Gate | Result |
|---|---|
| G1 no loss | **Pass with 2 stated limits.** Names: 115 -> 4 lost of the tokens either pass had (100 pairs); 25 of 25 engine pairs keep at least as many names as the better of live and clean-up. No lane keeps a live run >= 0.15 s without a saved word (0 of 51; today 42, three of them >= 1 s). Digits: restored when in a hole ("10" kept once, deduplicated against 十 once). Limits: replacements, and "Lab" under 的 (4 of 100) |
| G2 no duplication | **Pass.** Repeated-unit runs 0 -> 0; doubled neighbouring units 0 -> 0 (100 pairs and 34 engine lanes); restored words overlapping a kept word by more than one step: 0 of 332 |
| G3 improvements stay | **Pass on what was recorded; UNMEASURED for real invented live words.** Frontier duplicates: live 13, today 0, rule 0. Mis-timed live word (我 at 0.1 s): not restored. Every kept word identical in 34 of 34 lanes; row speakers unchanged 34 of 34; sorted and one owner 34 of 34. Speaker error with truth: unchanged (.1217) and better (.1296 -> .0907). "Yeah," and "uh I I" come back: the audio there is voiced at -14 to -23 dBFS, so they are speech the clean-up stopped before, not invented |
| G4 punctuation | **Not reproduced, not fixed.** 7-8 marks per Mandarin passage in every answer; live 6-8. Rule H carries the marks attached to restored words only (7.75 -> 7.80 mean). A clean-up answer without punctuation would stay without |
| G5 script | **Fail, by measurement, with no request-side fix.** Same single script as the live rows in 14 of 25 engine pairs; live rows mixed in 10 of 25; hints do not pin (8 of 15 traditional) |
| G6 cost and latency | **Pass.** Provider cost +0 (no request). Wall +0.08 s mean on 40-60 s meetings (noise level), 0.21 s of rule time on a 2-hour lane. The existing retry doubles a chunk's cost and returns the same answer (3 of 3 same-bytes pairs) |
| G7 long meetings | **Pass at small scale; 900 s plan not run.** The rule sits after the stitcher / identity policy and before the word gates; it reads final labels and never writes one on a kept word, so it needs nothing from rule W and does not change which speaker a kept word gets (161 of 161 identical on a 2-chunk run through `LongFinalStitcher`). A real > 900 s meeting costs about $0.16 per lane: not run |

### Implementation-ready design

1. `moss_transcribe_diarize/app/gemini_coverage.py` — add `restore_witnessed_words(words, witness, *, skip=())`
   and `drop_restated(witness, committed, frontier)`: `f3/rule.py` `fill_holes` / `uncovered_runs` / `one_owner`
   as they stand (constants `STEP = 0.1 s`, `MIN_RUN = 0.15 s`; the `VARIANT` sweep switch removed).
2. `gemini_hybrid_engine.py`, `GeminiHybridEngine._publish_window`: inside `if frontier > old:` and only when
   `gate_words` is true, keep `committed = [w for w in absolute if old < w.end_sample <= frontier]` in
   `self._witness_words` (after `drop_restated(self._witness_words, committed, old)`). In `finish()`, before
   `self.terminal.transcribe`, hand the list over: `self.terminal.set_witness_words(...)` when the terminal has it.
   About 3 words per second of speech are held (a 2-hour lane: about 22,000 small tuples).
3. `gemini_lane_engine.py`, `ConditionalMicrophoneTerminal`: pass `set_witness_words` through.
4. `gemini_provider.py`, `TerminalTranscriber`: `set_witness_words`; in `transcribe()`, after the
   stitch / `identity_policy.remap` step and before `self.word_gate.filter`, when the tape is the whole lane
   (`sample_offset == 0`): `all_words, restored = restore_witnessed_words(all_words, self._witness_words,
   skip=self.coverage_gaps)` and report `witness_restored_words`. `transcribe_interval` (Stop-tail recovery) and the
   File / URL runner pass no witness and are unchanged.
5. `gemini_live_runtime.py`: one new diagnostics counter `witness_restored_words` beside
   `terminal_coverage_fallbacks`. The >= 10 s row carry (lines 1126-1132) stays as it is; rule H skips its intervals.
6. `docs/design-gemini-live.md`: the "never loses live speech" paragraph gets the word-level rule and its limits.

Relative to the other round-5 work: F1 (preview trim) and F2 (microphone anchor) do not touch these functions;
F2 changes which microphone words the live path commits, and rule H takes whatever was committed. Rule W changes
labels inside `LongFinalStitcher` / `FinalWordPolicy`; rule H runs after both and copies a neighbour's final label.

### Regression tests to add (from the recorded patterns; `f3/s6_patterns.py` holds the numbers)

`tests/test_gemini_coverage.py`
- `test_omitted_name_is_restored_in_its_hole` — 院 5.2-5.3 | 计 5.8-5.9 with live Media Lab 的 -> 院 Media Lab 的 计; kept words unchanged.
- `test_word_after_the_hole_is_not_doubled` — clean-up kept 的 (overlapping by one step, and abutting) -> "Media Lab" only.
- `test_replacement_is_kept` — Computer + File over Computerphile's span -> nothing restored.
- `test_name_with_neighbour_one_step_into_it_is_restored` — 道 15.8-16.0 | 10 16.7 with live Computerphile 15.9-16.6.
- `test_same_number_written_two_ways_is_not_doubled` — live 10, clean-up 十.
- `test_one_time_step_of_jitter_is_not_a_hole` — a 0.1 s run is not restored.
- `test_long_live_word_over_the_same_cleanup_word_is_not_doubled` — Amazing. 27.4-28.5 against 28.2-28.5.
- `test_frontier_restatement_is_not_a_witness` — Computer / Computerphile (overlapping) and 要 / 要 (abutting, same text).
- `test_frontier_duplicate_covered_by_cleanup_stays_removed` — 議。 + 议。 against 议。.
- `test_mistimed_live_word_is_not_restored` — 我 at 0.1 s against 我 at 12.0 s.
- `test_restored_run_takes_nearer_neighbour_speaker_and_kept_words_keep_theirs`.
- `test_interval_owned_by_the_ten_second_fallback_is_skipped`.

`tests/test_gemini_provider.py`
- `test_terminal_restores_witnessed_words_after_labels_and_before_gates` — a restored word in unvoiced audio is removed by `WebRtcWordGate`; one in voiced audio is kept; labels of kept words equal the run without a witness.
- `test_chunked_terminal_restores_after_stitching` — two chunks, labels of kept words unchanged.
- `test_transcribe_interval_ignores_witness_words`.

`tests/test_gemini_hybrid_engine.py` / lane engine
- `test_engine_hands_committed_words_to_terminal` — only words committed by rolling windows, frontier restatements dropped; tail recovery rows are not witnesses.
- `test_saved_transcript_keeps_live_name_the_cleanup_answer_omits` — scripted provider (live answer with the name, whole-recording answer without): one row, the name once, rows sorted, one owner; counter = 3.
- `test_microphone_restored_words_pass_the_terminal_gates`.

### Stress matrix

| Cell | Status |
|---|---|
| Chinese+names then English, 5 leading silences, live x clean-up cross pairs (100 word-level, 25 engine) | ran |
| R5-D's 9 recorded two-lane meetings (echo -40 / -25 dB, short / long local speech, English / Mandarin) | ran |
| answers that lost most or all names (zh-CN hint; noise 10 / 5 dB) with their own live samples | ran |
| injected 2.0 s omission, system lane; injected 1.5 s omissions, microphone lane (English, Mandarin) | ran (injected) |
| English 3 speakers with exact truth, speaker error, 2 leading silences | ran |
| chunked clean-up through the stitcher, 2 chunks of 25 s | ran |
| names at the very start; another Mandarin voice; music under speech; quiet lane (request level) | ran |
| live-only invented words: music after speech; room events + echo residue on the microphone | ran, not exercised (0 produced) |
| round-4 listener fixtures (invented words in live rows) | not run (answers not on disk, about $0.13) |
| meeting over 900 s with the production chunk plan | not run (about $0.16 per lane) |
| real human code-switched Mandarin; the user's own recording | not run (not on disk / private) |
| request variants on the English fixture | not run (every variant stopped at the 5-draw rule) |
| OpenAI-compatible provider; overlapping speakers inside a hole | not run |
| real Chrome end to end | not run (the change is in the engine; R5-D's engine replay is the same code path) |

### Side findings (not part of the fix)

- The parser drops a word when the provider garbles a time: `"问" 4s-414.200s, "题" 414.200s-4.200s` — 题 is
  dropped (start beyond the audio) and 问 is clamped to 1 s. 1 word in 1 of 53 new answers (the zh-CN hint draw).
- The coverage retry re-sends identical bytes and gets the identical answer (3 of 3).
- Two local prototype bugs, no provider effect: a recording client that called itself (3,892 local recursion
  errors, removed from the ledger, 0 requests sent) and a client created on two threads at once (1 request not sent).
