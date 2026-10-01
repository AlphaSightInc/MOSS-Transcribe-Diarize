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

## Results

(filled in below as measured)
