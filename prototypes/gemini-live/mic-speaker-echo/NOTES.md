# R5-D: built-in speakers + built-in microphone bug report (2026-10-01) — diagnosis only

Throwaway diagnosis of the user's report on `gemini/r4-ui` @ 9a1ca171 (MacBook Pro, Chrome,
built-in speakers playing the shared tab, built-in microphone, echo cancellation on). No
product code is changed here. Evidence: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/mic-speaker-echo/`.

## Contract (written before any measurement)

**Structural question.** One meeting has three text authorities per capture lane: the instant
preview (grey), the rolling commit (solid, live) and the clean-up pass (saved). For each
reported symptom: which authority and which lane produced the text the user saw, and which
rule let two authorities show the same speech, or let one authority lose speech another had?

**Minimum primitives.**
- *Lane* (system = shared tab, microphone) — a row never changes lane.
- *Authority* (preview / rolling / clean-up) — exactly one owns each audio second at a time.
- *Comparable unit* — the token two authorities' texts are compared in (a CJK character, a
  word of a spaced script, a digit run). Dedup rules are only as good as this unit.
- *Admission gate* — a rule that removes words (voice activity, level, echo, 2 s anchor).

**Invariants the product claims** (`docs/design-gemini-live.md`).
- I1 The grey preview of a lane does not repeat that lane's committed text.
- I2 A microphone preview row does not repeat the system lane.
- I3 Local speech that reaches the grey preview is committed or, if withheld, withheld by a
  counted gate (`engine_diagnostics`).
- I4 Clean-up never loses speech the live transcript had ("the saved transcript never loses
  live speech").

**Symptoms as reported, and hypotheses (ranked before testing).**

S1 "grey text repeats the solid text".
- H1a The grey text is the *system* lane's own preview and `_trim_committed_preview` fails
  on unspaced scripts: it compares whitespace/punctuation-delimited runs, so a Chinese clause
  (or a Chinese+Latin run) is one token and never matches. *Prediction:* the same replay
  trims in English and trims 0 units in Chinese; the row sits under the committed card as a
  same-lane continuation.
- H1b The grey text is the *microphone* preview of speaker echo and `_without_echo` fails.
  *Prediction:* the row is a separate card with the microphone source label.
- H1c Preview bookkeeping keeps a W3 turn that ended before the frontier.
  *Prediction:* the repeated row's end sample is at or before `committed_samples`.

S2 "microphone text shows in grey, never becomes solid"; S3 "clean-up has no microphone text".
- H2a No local speech existed; the "microphone text" is S1's grey row. *Prediction:* saved
  audio has no near-end energy where the tab is silent; no microphone row in either picture.
- H2b Local speech existed and was shorter than the 2 s anchor (round 4, issue #3), so every
  live window dropped it (`mic_words_dropped_unanchored`) and the saved pass withheld the
  lane (`mic_words_withheld_unanchored_lane`). *Prediction:* a fixture with only short local
  phrases shows grey mic text, 0 solid mic rows, 0 saved mic rows, both counters > 0.
- H2c Local speech existed, quieter than −15 dB under the tab level, and the acoustic gate
  dropped it while the tab was talking. *Prediction:* `mic_words_dropped_by_acoustic_gate`
  rises with the level gap; the same phrases survive when the tab is silent.
- H2d Echo guards (voice cosine, token match) removed local words.

S3b (seen by the lead in `after.png`) "clean-up lost every Latin word and the full stops".
- H3a The provider's whole-recording answer differs from its window answer on mixed
  Chinese/Latin speech (omits Latin tokens or gives them unusable times).
  *Prediction:* the raw clean-up response for a Chinese+names clip followed by English lacks
  the names or times them outside voiced audio; a Chinese-only request keeps them.
- H3b Our pipeline drops them (parser tolerance, voice-activity word gate, ordering).
  *Prediction:* raw response holds the names; a named stage's output does not.
- H3c Punctuation loss is the same mechanism (separate tokens) or provider variance.

**Falsifiers.** H1a dies if the replay trims Chinese, or the real row was a microphone row.
H2b/H2c die if the counters stay 0 in the matching fixture. H3a dies if the raw response
keeps the names with usable times; H3b dies if no stage output differs from its input.

**Tool decision.**
- $0 runtime-seam replay (`GeminiLiveRuntime.publish_update` with scripted updates) decides
  H1a/H1c: it is the production publication path and needs no provider.
- Saved-state facts of the real meeting (read-only copy; numbers only) decide H1b and bound H2a.
- One paid probe per question on *public/synthetic* audio only: raw rolling vs clean-up
  responses for H3; one real-Chrome end-to-end run for S1–S3 together. Cap $1.00.

**Assumptions / unknown.** The real meeting saved no per-lane audio and no diagnostics, so the
real microphone lane's content is `unmeasured`; only the mixed MP3 and the final rows exist.

## Commands

```sh
PY=../MOSS-Transcribe-Diarize-wt-r5-d.venv/bin/python; W=prototypes/gemini-live/mic-speaker-echo
F=~/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/mic-speaker-echo/fixtures
PYTHONDONTWRITEBYTECODE=1 $PY $W/build.py                      # public/synthetic fixtures ($0)
PYTHONDONTWRITEBYTECODE=1 $PY $W/s1_trim_replay.py             # S1 at the publication seam ($0, 2 s)
PYTHONDONTWRITEBYTECODE=1 $PY $W/replay.py rp-short-aec40 $F/sys-zhlatin-en.wav $F/mic-short-aec40.wav
                                                               # whole production engine on recorded provider answers ($0, 15 s)
PYTHONDONTWRITEBYTECODE=1 $PY $W/e2e_analyze.py rp-short-aec40 # the three symptoms as numbers
PYTHONDONTWRITEBYTECODE=1 $PY $W/matrix.py                     # every recorded cell, one line each
PYTHONDONTWRITEBYTECODE=1 $PY $W/gate_sweep.py                 # speaking level vs the microphone gates ($0)
# paid (public audio only; ledger.py enforces the cap): add --record to replay.py through with_key.sh;
# probe_batch.py / probe_variance.py (raw provider answers); server.sh + e2e_run.py (real Chrome, real UI)
```

`replay.py` is the feedback loop: the product's own engine composition with only the provider swapped for
recorded answers (batch responses keyed by request bytes, instant-word events replayed at their sent positions).
It cannot reach the provider unless `--record` is given.

## Results (2026-10-01; total spend $0.26 of $1.00)

**Real meeting, from saved state only** (`real-facts/real_facts.json`; no lane audio, no diagnostics, no live rows
were saved): 4 final rows, all system lane, 0 microphone rows; the Chinese rows hold 0 Latin words (the live row in
the picture held 11) and 2.0 s of fully voiced audio (7.8-9.8 s) has no row; tab sound about -17 dBFS in its lane;
no speech-level energy in the 4 s where the tab was silent; whether anyone spoke under the tab sound is
unmeasured (the voiceprint check has no power there: control 0/15); no echo path above about -35 dB.
The grey paragraph in `during.png` is a system-lane row: it renders as a continuation of the Browser card, which
`transcriptCards.ts` allows only within one lane.

**S1 - H1a confirmed, H1b and H1c rejected.** `_trim_committed_preview` (gemini_live_runtime.py:1293-1332,
since 3901d2db, 2026-09-28) compares whitespace/punctuation-delimited runs. In an unspaced script a clause is one
token, and a Chinese+Latin run is one token, so the repeated head never reaches five matching tokens.

| Replay at the publication seam (`s1_trim_replay.py`) | preview units already solid | trimmed |
|---|---:|---:|
| Chinese with Latin names | 75 of 115 | 0 |
| Chinese only (system lane; microphone lane the same) | 60 of 93 | 0 |
| Japanese (word split simulated) | 56 of 80 | 0 |
| English control | 52 of 54 | 52 |
| Korean control (spaced) | 51 of 67 | 51 |

The same with committed text joined the pre-F1 way (a space between characters): 0 trimmed. So the trim never
worked for Chinese; the F1 join rule neither caused nor cured it.
Production engine on real provider answers (9 recorded cells + 1 real-Chrome run): the system grey row repeated
67-71 units of its own solid text for 12.5-16.5 s of a 40 s meeting in 10 of 10. The page showed it as a dotted
continuation under the solid card (`runs/short-aec40/shot-e27.png`, the twin of `during.png`).
Feasibility probe only (`replay.py --trim-in-units`): the same rule over the lane composer's units (one per CJK
character) leaves 0 repeated unit-polls (1,982 before) and keeps the fresh ones (2,151 -> 2,206) on three cells,
one of which has the solid row in traditional and the preview in simplified characters.

**S2/S3 - microphone text grey but never solid, and absent after clean-up.** Reproduced by two mechanisms; which
one the user met depends on whether they spoke (unknown).
- *H2b confirmed: the 2 s anchor* (gemini_lane_engine.py:427-431 live, 456-462 saved; span rule
  gemini_hybrid_engine.py:39-64; since 7ea36f81 and 1219db04, 2026-09-30; listed as an accepted cost in
  `mic-hallucination/NOTES.md`). "Can you elaborate on that?" said three times (5 words, 0.8-0.9 s by provider
  times): the provider returned the 5 words in every window, the level and echo guards kept 4-5, and the anchor
  dropped all of them (`gates.jsonl`). 5 of 5 short-phrase cells (English at no echo, -40 dB, -25 dB; Mandarin
  at -40 dB; real Chrome): grey in every cell, 0 solid rows, 0 saved rows; unanchored 10-18, lane withheld 10-15.
  Provider word times are shorter than the audio: a 2.6 s sentence measures 1.3-1.7 s and does not anchor alone.
- *Echo residue in the grey microphone row* (no local speech): at -40 dB, 2-4 word fragments of the far end in 4
  snapshots; at -25 dB, up to 30 units of mis-heard far-end text in 49 of 73. None is committed (level gate:
  278 and 386 words dropped). `_without_echo` needs a run of 3 words / 5 CJK characters (gemini_lane_engine.py:68).
- *H2c bounded.* Gate-only sweep (`gate_sweep.py`, provider words held fixed): a 6 s local sentence under tab
  sound at -17 dBFS is saved 27-28 of 30 words down to 10 dB under the tab, 23 at 13 dB under, 0 at 16 dB under
  (the level gate removes 58 words, the anchor withholds the remaining 13). The user's measured levels in other
  meetings were 4-10 dB under.
- H2d rejected here: voice guard 0 drops, text guard 0-2.
- Controls: long local sentences are saved in 3 of 3 cells (English -40/-25 dB, Mandarin -40 dB).

**S3b - H3a confirmed, H3b rejected.** The product drops nothing: parser 0, word gate 0, repaired 0 on every
recorded answer. The provider's answers for the same audio differ in code-switched words, punctuation and script:
- whole-recording requests: 8 of 10 lost "Media Lab" (2 of 10 Latin tokens); 1 of 10 came back in traditional
  characters; punctuation in the Chinese passage was 7-8 marks in every answer (6-8 in window answers), so the
  real meeting's punctuation loss (1 mark left) is not reproduced;
- recorded meeting: the live transcript at Stop held "Media Lab 的" and "Computerphile"; the clean-up answer had
  neither ("Computer File"); the real-Chrome meeting went the other way (clean-up restored both and came back in
  traditional characters).
Clean-up replaces the whole live surface (gemini_live_runtime.py:1138-1144); its only check against the live rows
is a wordless stretch of at least 10 s (gemini_coverage.py:12, gemini_provider.py:363-380), so a lost name or a
2 s hole is invisible to it. Why the real answer lost all 7 names is unmeasured (no raw response was saved).

**Also seen (not reported by the user).** The live transcript duplicates one character at a window frontier
("...会议。" then "议。..."/"議。...") in both independent provider samples; clean-up removes it.
