# R5-F2: short local phrases stay grey, never solid, absent after Stop (prototype of the fix)

Throwaway prototype on `gemini/r5-f2` (starts at R5-D's last commit, product code `gemini/r4-ui` @ 9a1ca171).
No product code or test is changed in this phase. Evidence:
`~/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f2/`. Provider cap **$0.25** (lead correction).
Diagnosis this builds on: `../NOTES.md` (R5-D, mechanism H2b = the round-4 "2 s anchor").

## Contract (written before any measurement)

**Structural question.** The provider placed words on a stretch of the microphone lane. Did the local person
speak there? The answer must come from evidence that is present for real local speech and absent for
(i) a silent or noisy room, (ii) residue of the far end coming out of the speakers, (iii) text the provider
invents. Today the evidence is "the provider's word times form a continuous span of at least 2 s". R5-D measured
that this is not such evidence: real phrases measure 0.8-1.7 s in provider times, invented runs reach 1.9 s.

**Minimum primitives.**
- *Run* - the gated microphone words of one provider answer, joined per speaker label across gaps of at most
  0.6 s. This is the existing merge inside `attributed_embedding_intervals`; it is the unit that is admitted or
  withheld. Cannot be removed: evidence has to be attached to some stretch, and a single word is too short to
  carry any.
- *Local-voice evidence of a run* - a fact read from the two lane tapes over the run's time span, not from the
  provider's text: how much voiced microphone audio is there that the system lane cannot explain. Per 10 ms
  frame it is the existing level gate's own test (the tab is not voiced there, or the microphone is at least
  -15 dB relative to the tab at the best 0-100 ms lag) on frames the existing voice-activity detector calls
  speech. Candidate C1. Cannot be decomposed further: "voiced" answers (i), "not explained by the tab" answers (ii).
- *Anchor* - today's rule (a run of at least 2 s). Kept as one sufficient condition, so nothing published or
  saved today can be lost (candidate C4).
- *Lane memory* - `local_speech_seen`, existing, unchanged meaning.

Candidates to attack with data (each must earn its place; reject by numbers):

| | Evidence it needs | Unavailable when | Then |
|---|---|---|---|
| C1 unexplained voiced microphone audio under the run | both lane tapes (always held) | never | - |
| C1b the same, plus a minimum number of surviving words in the run | provider words | never | - |
| C1c the existing voice-cosine echo guard run on the short run itself (echo if it matches the tab voice at that time) | encoder, a system voice vector overlapping in time | no system voice vector (tab silent / short tab speech) | abstain: no echo verdict |
| C2 the instant preview heard the same words at the same time | the lane's instant-word stream | socket closed/failed, OpenAI-compatible provider (no preview) | abstain: today's rule |
| C3 voice match with earlier anchored microphone speech or a saved "You" voiceprint | an earlier >= 2 s local span, or a saved voiceprint | first phrase of a meeting with no saved voiceprint | abstain: today's rule |
| C4 the 2 s anchor alone | - | - | today's behaviour |

**Invariants.**
- I1 Superset: every microphone word published live or saved today is still published or saved (the anchor stays
  a sufficient condition). So long local turns cannot lose words by construction; verified in G3.
- I2 No word list, language list or script list.
- I3 A run with neither evidence nor anchor is withheld and counted exactly as today (abstain = today).
- I4 The evidence uses audio the engine already holds. No new provider request.
- I5 The system lane is never touched. The grey preview is touched only if G5 shows the same evidence does it for free.
- I6 A short run that carries evidence admits only itself. It does not open the lane (`local_speech_seen` keeps
  its >= 2 s meaning), so one real short reply cannot let invented words elsewhere into the saved text.

**Assumptions and unknowns.**
- Echo is simulated: R5-D's three-tap room copy at -40/-25/-15 dB, and round 4's gated band-limited fragments at
  -38 dBFS. Real echo-cancellation residue and double-talk attenuation on a physical microphone are **unmeasured**
  and cannot be measured with a file-backed microphone (attended check by the user).
- Room events are generated signals (round-4 `noise.py`), not recordings.
- Mandarin local speech is macOS text-to-speech (Meijia); English is public podcast audio (Lex Fridman / Keyu Jin).
- Provider answers vary call to call. A recorded answer is one sample. Wherever possible the negative-lane gate
  is therefore proven on audio alone, over every stretch of the lane, so it does not depend on which words the
  provider happens to return.
- The round-4 recordings (provider words on the listen-only lanes) were deleted by a worktree clean-up. The audio
  is rebuilt bit-for-bit from the committed builders at $0; provider words on it would be new paid samples.

**Falsifier.** C1 dies if, on any listen-only / room-noise / echo-only lane, some stretch carries at least as much
evidence as the weakest real short phrase (no threshold exists), or if a stretch above the chosen threshold
receives a provider word that survives the other guards (one invented or echoed committed/saved word = rejected).
The whole design dies if no candidate, alone or composed, passes G2 while reaching G1; then the best safe partial
rule and its recall are reported.

**Tool decision.**
- *$0 audio-only scan* (`scan.py`): the evidence at every stretch of every negative lane, and under every real
  short phrase. Decides whether a threshold exists and its margin. If negative max >= positive min, C1 alone is
  rejected and C1b/C1c/C2/C3 are measured for the overlap.
- *$0 production-engine replay* (`replay_f2.py`, R5-D's method: the product's own engine composition, recorded
  provider answers, candidate applied as a patch inside the prototype). Decides G1, G3, G4, G5 on R5-D's cells.
  The unpatched harness must first reproduce R5-D's matrix.
- *Paid calls* (cap $0.25, ledger before each): only (a) cells R5-D did not record - short replies in a meeting
  that also has a long local turn, varied short phrases, -15 dB echo, a room-noise lane - and (b) provider words
  on rebuilt round-4 negative lanes, spent where the scan says a provider word could matter.

## Contract amendment 1 (lead corrections, written before any measurement)

1. **The user confirmed they were speaking** (answers R5-D Q1): local speech reached the grey preview on the real
   MacBook (built-in speakers playing the tab, real echo cancellation, double-talk) and was never committed or
   saved. Its length is unknown - it is **not** assumed to be under 2 s. So both the 2 s anchor and the level gate
   (words 16 dB or more under the tab are dropped) are suspects, and "local speech while the tab is talking" is a
   first-class cell for short **and** long turns.
2. **The evidence must not depend on the local voice being louder than the tab.** The first-draft C1 above reused
   the level gate's fixed "-15 dB relative to the tab" as its test of "explained by the tab". That draft is
   withdrawn before measurement: it would call quiet double-talk speech "explained".
3. **Revised C1 primitive - the meeting's own echo return.** "Explained by the tab" is defined by what the tab is
   measured to put into this microphone lane, not by a fixed fraction of the tab's digital level:
   - per 10 ms frame where the tab is voiced, the ratio microphone level / tab level (best 0-100 ms lag, as the
     level gate already computes it);
   - the *echo return* = a robust quantile of that ratio over the context the engine already holds (the live
     window, the whole lane for the saved pass). Which quantile, and the margin above it, are decided by the
     measured ratio distributions of echo-only lanes versus double-talk (unknown until measured);
   - a frame is *unexplained* when the microphone is voiced and either the tab is silent there or the microphone
     level exceeds echo return x tab level by the margin;
   - run evidence = the longest contiguous stretch of unexplained voiced frames under the run (threshold T,
     measured). The same per-frame fact, taken over one word, is the candidate replacement for the fixed -15 dB
     in the level gate (C1w), so one primitive answers both suspects.
   Still attacked alongside: a least-squares echo removal on the two tapes (C1x: energy not linearly predictable
   from the tab) - kept only if the echo-return test fails a gate that C1x passes, because real post-cancellation
   residue is not linear and C1x cannot be validated on a file-backed microphone.
4. **Added gate G7' (replaces G7).** Level sweep of local speech while the tab is talking, 4 to at least 20 dB
   under the tab, short and long turns, at -40 and -25 dB echo: word recall per level with today's rule and with
   the candidate (gate decisions on recorded words at $0; provider answers re-recorded at the quiet end, where
   "the provider hears the same words" is not safe to assume).
5. **Report additions.** The attended check for the physical MacBook (steps, what to say and when, 2-3 minutes),
   which `engine_diagnostics` counters say afterwards which rule acted, and whether they must be saved with the
   meeting.
6. Provider cap is **$0.25**. "Rebuilt bit-for-bit" above is too strong: the round-4 audio is rebuilt from the
   committed builders and seeds; its text-to-speech parts depend on the installed macOS voices, and the deleted
   originals cannot be compared.

## Gates (fixed before measuring)

- **G1 repair.** Short local phrases (0.8-2 s; English and Mandarin; no echo, -40 dB, -25 dB; tab silent and tab
  talking) become solid live and are saved after Stop. Pass: every such cell has solid > 0 and saved > 0 and word
  recall (kept / spoken) >= 0.8 live and saved. Today: 0 in 5 of 5 cells.
- **G2 round-4 fix holds.** Every listen-only / room-noise / echo-only lane (round-4 fixtures rebuilt, R5-D cells)
  commits 0 and saves 0 invented or echoed words. One such word rejects the candidate. Reported twice: on the
  provider answers held, and as the audio-only bound over every stretch.
- **G3 long turns.** R5-D control cells: 3 of 3 saved; live and saved word counts >= today's.
- **G4 echo.** 0 echoed words committed or saved as local speech at -40 and -25 dB; -15 dB reported.
- **G5 grey row.** Do F2b echo fragments still appear in the grey microphone row? Measure the free variant if one
  exists; otherwise report only.
- **G6 cost.** Added time per live window and after Stop (pass: <= 50 ms per window, <= 250 ms after Stop for a
  40 s meeting, scaling stated); embeddings added.
- **G7 interplay.** Quiet local speech, 4-16 dB under the tab: what the evidence does where the level gate drops
  words today (report).

## Commands

```sh
PY=../MOSS-Transcribe-Diarize-wt-r5-f2.venv/bin/python; W=prototypes/gemini-live/mic-speaker-echo/f2
PYTHONDONTWRITEBYTECODE=1 $PY $W/run_all.py        # everything below at $0 from recorded answers
```

## Results

(filled in after measurement)
