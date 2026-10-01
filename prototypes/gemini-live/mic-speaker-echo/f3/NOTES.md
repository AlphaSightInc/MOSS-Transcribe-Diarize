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
PYTHONDONTWRITEBYTECODE=1 $PY $W/run.py            # everything at $0 from recorded answers; prints every table
```
(paid steps are listed in the results section with their exact command)

## Results

(to be filled after measurement)
