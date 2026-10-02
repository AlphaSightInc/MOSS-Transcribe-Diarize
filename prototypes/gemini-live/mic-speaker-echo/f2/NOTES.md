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
PYTHONDONTWRITEBYTECODE=1 $PY $W/run_all.py                      # every number below, $0, recorded answers only
PYTHONDONTWRITEBYTECODE=1 $PY $W/run_all.py --with-sensitivity   # + 26 ablation / sensitivity variants (slow)
PYTHONDONTWRITEBYTECODE=1 $PY $W/report.py                       # the gate tables again
# paid, already done, kept for the record (ledger.py enforces the cap; the key only through ../with_key.sh):
#   r4_chain.py terminal|windows ... --record     record_cells.py
```

`replay_f2.py` is R5-D's `replay.py` method (the product's own engine composition, only the provider swapped for
recorded answers) with its own evidence folder and ledger. `evidence.py` is the primitive; `candidate.py` applies it
to the product's `MicrophoneWordGate` as a patch inside the prototype. No product file was edited.

## Results (2026-10-01; spend $0.2368 of $0.25; key scan 0)

### Verdict: works for the defect, partly for gate G1

Today a microphone word needs two things to survive: be at most 15 dB quieter than the tab (level gate), and sit
in a window that holds 2 s of continuous provider word times (anchor). Both tests look at the wrong thing: the
first at the tab's loudness instead of the tab's echo in the microphone, the second at the provider's clock.
The candidate asks one question of the audio the engine already holds - *is there sustained speech in the
microphone that the tab cannot explain?* - and uses the answer in both places.

| Gate | Result | Numbers |
|---|---|---|
| Step 0 | pass | unpatched harness reproduces R5-D's 9 cells (rows at Stop, rows after clean-up, 5 counters): 9/9 |
| G1 repair | **partly** | phrases of 3+ words / 5+ characters: saved 25/25 (English, varied), 15/15 (R5-D English, no echo and -40 dB), 15/15 (Mandarin, -40 dB); today 0. Not repaired: the phrase said over the tab at -25 dB and -15 dB echo (0/5: the provider never returned those words, in 0 of 3 answers), one Mandarin phrase live (the provider gave it the echoed voice's label), 1-2 word replies (0/4, as today) |
| G2 round-4 fix holds | pass | 28 provider answers on rebuilt round-4 lanes (908 words; 137 and 133 survive the echo guards on the two listen-only lanes, round 4 had 104 and 73): today 0 kept, candidate **0** kept. 5 listen-only / room-noise engine cells: 0 committed, 0 saved |
| Double-talk (amendment 1) | pass on fixtures | local speech said while the tab talks, 20 dB under it, -40 dB echo: 6 s + 2.6 s turns 0/31 -> 27/31; one 28 s turn 0/51 -> 51/51 provider words; short English phrases 0/15 -> 15/15. The evidence compares the microphone with the tab's measured echo in it, never with the tab's loudness. Real echo cancellation: unmeasured (attended check) |
| G3 long turns | pass | 3 of 3 saved; saved units 24, 25, 39 -> 27, 27, 40; live 20, 20, 23 -> 22, 22, 24. No cell and no sweep level (18 cells, 63 sweep cells) is below today's rule |
| G4 echo | pass | 0 echoed units committed or saved at -40, -25 and -15 dB (listen-only and short-phrase cells) |
| G5 grey row | reported | unchanged by the candidate (echo fragments still appear: 4 and 44 snapshots). The same evidence as a row test removes 48 of 48, 0-0.5 s delay on 16 real phrases; not free (needs the frame facts as audio arrives) - offered as D3 |
| G6 cost | pass | +4.8 ms median, 9.7 ms max per live window; +21 ms after Stop for a 40 s meeting, +260 ms for 480 s (0.54 ms per meeting second, about 1.9 s per hour). No new embedding call site; a quiet local turn the level gate used to drop is now embedded once per window like any other local turn |
| G7' level sweep | reported | long turn under the tab, -40 dB echo: today 20/31 at 13 dB under the tab and **0/31 from 16 dB under**; candidate 27/31 at every level to 24 dB under. Short phrases: today 0 at every level; candidate 15/15 to 20 dB under, 0 at 24 dB under |

Totals over the 18 engine cells (343 units spoken): today live 90, at Stop 101, saved 157; candidate live 206, at
Stop 291, saved 310. Sweep (63 cells, 1,456 units): today 332 / 377 / 434; candidate 882 / 1,201 / 1,257.

### The rule (what `candidate.py` does)

Per 10 ms frame of the context the engine already holds (a live window's 30 s; the saved pass walks the lane in
the same 30 s contexts every 15 s, so both passes judge a frame the same way):

1. *Frame facts.* Is the microphone frame speech (WebRTC voice detector, mode 3)? Is the tab voiced within the last
   0-100 ms, and how loud (the level gate's own lag search)?
2. *Echo return of this meeting.* The median of microphone level / tab level over the frames where the tab is
   voiced. It is a measurement of how loudly the tab shows up in this microphone: -41.2, -27.7 and -17.9 dB on the
   -40, -25 and -15 dB echo fixtures (frame-to-frame spread above the median 3.4 dB), -48.6 dB = the noise floor
   with no echo. With under 1 s of tab speech in the context
   there is no measurement and the level gate's fixed -15 dB stands in.
3. *Unexplained frame.* Speech in the microphone where the tab is silent, or louder than echo return + 6 dB.
4. *Sustained stretch.* At least 0.4 s of unexplained frames in a row (holes up to 50 ms bridged).
5. *Run.* One provider speaker label's words joined across gaps of at most 0.6 s - the product's existing merge -
   taken before the level gate, so an echoed voice keeps its full length.
6. *Local run.* A run that touches a sustained stretch, has at least 80% of its words on unexplained audio
   (+-0.2 s, the word gate's pad), and whose words on that audio weigh at least 15 in the product's unit weights
   (5 per word, 3 per CJK character: three words or five characters). Its words on unexplained audio are *local words*.

Used in three places, everything else unchanged ("never below today" is by construction for B - the 2 s anchor
stays a sufficient condition - and *measured* for A and C, which change what reaches the voice and text guards:
0 of 81 cells below today):
- **A, level gate.** A local word that the fixed -15 dB test dropped is kept.
- **B, anchor.** A live window (or a saved lane) with no 2 s span keeps the local words of each local run that
  still weighs 15 after the voice and text guards, instead of dropping everything. `local_speech_seen` keeps its
  2 s meaning, so a short phrase admits only itself.
- **C, text guard.** A local word is treated like a word with a usable voice vector: dropped only as part of a
  two-word echo phrase, not for sharing one common word with the tab ("的", "uh").

### G1 and G3 per cell (units kept / spoken; unit = a word or one CJK character)

"Live" = solid before Stop. These meetings last 37 s, so a phrase after the last live window (27 s) can only become
solid at Stop. "In scope" = phrases of at least three words / five characters.

| Cell | Today live / Stop / saved | Candidate live / Stop / saved | In scope, over the tab (saved) | In scope, tab silent (saved) | 1-2 word replies (saved) |
|---|---|---|---|---|---|
| short EN, no echo | 0 / 0 / 0 of 15 | 10 / 15 / 15 | 5/5 | 10/10 | - |
| short EN, -40 dB | 0 / 0 / 0 of 15 | 10 / 15 / 15 | 5/5 | 10/10 | - |
| short EN, -25 dB | 0 / 0 / 0 of 15 | 5 / 10 / 10 | **0/5** (provider) | 10/10 | - |
| short EN, -15 dB | 0 / 0 / 0 of 15 | 5 / 10 / 10 | **0/5** (provider) | 10/10 | - |
| short EN, -40 dB, 20 dB under the tab | 0 / 0 / 0 of 15 | 10 / 15 / 15 | 5/5 | 10/10 | - |
| short ZH, -40 dB | 0 / 0 / 0 of 15 | 5 / 10 / 15 | 5/5 (live 0/5: label) | 10/10 | - |
| short ZH, -40 dB, 20 dB under | 0 / 0 / 0 of 15 | 5 / 10 / 9 | **0/5** | 9/10 | - |
| 8 EN replies, -40 dB | 0 / 0 / 0 of 29 | 17 / 25 / 25 | 25/25 | - | 0/4 (today 0/4) |
| 8 ZH replies, -40 dB | 0 / 0 / 37 of 39 | 14 / 29 / 39 | 25/25 (today 23) | - | 14/14 (today 14: the lane has one 2.3 s sentence) |
| long turn + 4 replies, -40 dB | 27 / 27 / 32 of 37 | 30 / 35 / 36 | 35/36 (today 31) | - | 1/1 (today 1/1) |
| long EN, -40 dB (R5-D control) | 20 / 20 / 24 of 31 | 22 / 27 / 27 | 27/31 | - | - |
| long EN, -25 dB (R5-D control) | 20 / 20 / 25 of 31 | 22 / 27 / 27 | 27/31 | - | - |
| long ZH, -40 dB (R5-D control) | 23 / 34 / 39 of 40 | 24 / 36 / 40 | 40/40 | - | - |
| long EN over the tab, 20 dB under | **0 / 0 / 0** of 31 | 27 / 27 / 27 | 27/31 | - | - |
| one 28 s EN turn over the tab, 20 dB under (provider words kept / returned) | **0 / 0 / 0** of 51 | 41 / 52 / 51 on the page | 51/51 | - | - |

Counters over the 18 cells, today -> candidate: level gate 2,064 -> 1,925 (139 local words kept); unanchored
200 -> 33; lane withheld 121 -> 15 (291 words kept by local voice with no 2 s span); voice guard 43 -> 43; text
guard 122 -> 120.

### G2: the lanes with nobody speaking

| Sample | Provider words (after the voice-activity gate) | Survive the echo guards | Today kept | Candidate kept |
|---|---|---|---|---|
| round-4 listen-only lane A, saved pass (480 s; room events + echo-cancellation residue) | 266 | 137 (longest run 0.8 s) | 0 | 0 |
| round-4 listen-only lane B, saved pass (480 s) | 294 | 133 (longest run 0.8 s) | 0 | 0 |
| 26 live 30 s windows (10 on listen-only B, 8 + 8 on the listening stretches of lanes B-sp and A-sp) | 348 | 202 pass the level gate | 0 | 0 |
| engine cells: echo -40, -25, -15 dB; room-noise events + echo -40 dB | 278, 386, 388, 44 dropped by the gates | - | 0 / 0 / 0 | 0 / 0 / 0 |

The round-4 answers were bought again (the originals were deleted); the tab lane's words were not, so the voice
and text guards drop nothing there and more words reach the anchor than in the product - the 0 is an upper bound.
The heaviest invented run that sat on a sustained stretch weighs 10 ("Think about", on a throat-clearing event;
next "后 一 个。" = 9, which is the tab's own "统一到一个平台" heard through the residue), against the bar of 15.

**The audio alone** (`scan.py`, no provider involved). On echo-only lanes there is nowhere a word could be
admitted: longest unexplained stretch 0.00, 0.00, 0.02, 0.04 s at no echo, -40, -25, -15 dB (bar 0.4 s), and 0.02 s
on the round-2 lanes with -20 and -10 dB echo (the fixed -15 dB reference calls 1.0 s of that -10 dB echo
"unexplained"). On the round-4 noise lanes there are such places, and the scan says exactly where: 6 and 9
sustained stretches in the two 480 s listen-only lanes (2.6 s and 4.3 s in total), all on the generated
"throat clearing" event - a voiced sound no speech test separates from speech. Breath, keys, cough, creak, fan,
room tone and the residue fragments make none (longest 0.26 s). Another person or a television in the room does
(59 and 75 stretches per 120 s): that is speech in the room, admitted today as well once it lasts 2 s.

### G7': how quiet can the local voice be (tab at -17 dBFS)

Provider words are a recorded answer reused at every level (R5-D's method); they were recorded at 10 dB under the
tab (R5-D) and again at 20 dB under (this prototype) - at 20 dB under the provider still returned the whole long
turn (24 words) and all three short phrases; today's level gate then dropped every one (111 and 71 words).

| Local speech under the tab | 4 | 7 | 10 | 13 | 16 | 20 | 24 dB |
|---|---|---|---|---|---|---|---|
| long EN turn, -40 dB echo, today saved (of 31) | 25 | 25 | 24 | 20 | 0 | 0 | 0 |
| long EN turn, -40 dB echo, candidate | 27 | 27 | 27 | 27 | 27 | 27 | 27 |
| long EN turn, -25 dB echo, today | 26 | 26 | 25 | 22 | 0 | 0 | 0 |
| long EN turn, -25 dB echo, candidate (live in brackets) | 27 | 27 | 27 | 27 | 27 | 27 (11) | 5 |
| long turns said wholly over the tab, -40 dB, today | 24 | 24 | 24 | 17 | 0 | 0 | 0 |
| long turns said wholly over the tab, -40 dB, candidate | 27 | 27 | 27 | 27 | 27 | 27 | 27 |
| long ZH turn, -40 dB, today (of 40) | 40 | 40 | 39 | 33 | 0 | 0 | 0 |
| long ZH turn, -40 dB, candidate | 40 | 40 | 40 | 40 | 40 | 40 | 40 |
| short EN phrases, -40 dB, today (of 15) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| short EN phrases, -40 dB, candidate | 15 | 15 | 15 | 15 | 15 | 15 | 0 |
| short ZH phrases, -40 dB, candidate (words heard at 10 dB under) | 15 | 15 | 15 | 15 | 15 | 9 | 10 |
| short EN phrases, -25 dB, candidate (the phrase over the tab was never returned) | 10 | 10 | 10 | 10 | 10 | 10 | 10 |

Two floors, both measured: the voice detector at mode 3 stops seeing speech near -40 dBFS (mode 2 sees it to
-45 dBFS but halves the margin against residue, see below); and the local voice must be roughly 5-10 dB above the
echo of the tab in the microphone - not above the tab (-25 dB echo: full recall while the voice is 9 dB above
the echo, live recall 11 of 31 at 5 dB above, gone at 1 dB).

### Why each element is there (one removed at a time; 18 cells + 28 round-4 samples; stress = the text guard
cannot match any Chinese token, which happens when the provider answers the two lanes in different scripts)

| Variant | Units live / at Stop / saved (of 343) | Invented words kept on round-4 samples (of 908) | What it shows |
|---|---|---|---|
| today's rule | 90 / 101 / 157 | 0 | - |
| **candidate** | **206 / 291 / 310** | **0** | - |
| without A (level gate untouched) | 164 / 235 / 256 | 0 | A is what returns quiet double-talk speech (long turn 20 dB under: 0/31) |
| without B (anchor untouched) | 125 / 152 / 196 | 0 | B is what returns the short phrases |
| without C (text guard untouched) | 206 / 291 / 305 | 0 | a Mandarin phrase loses "的" to the tab and then fails the weight |
| reference = fixed -15 dB, not the measured echo return | 144 / 224 / 246 | 0 | the quiet cells are lost again; and on the -10 dB echo lane the fixed test finds 1.0 s of "local" audio in pure echo (measured reference: 0.01 s) |
| no sustained stretch required | 211 / 296 / 315 | **48** | residue fragments ("Oh about the words", "Google give it away") |
| no text weight required | 212 / 300 / 312 | **14** | words on noise events ("Think about", "也 是 太。") |
| no coverage required | 211 / 296 / 310 | 0 | nothing admitted here, and one Mandarin phrase the provider merged with the echoed voice is repaired live (+5). But 6 echoed characters of a 78-word echoed run then pass the level gate as "local" (0 with coverage) and only the text guard and the weight test stop them; under the stress one ("题") is committed live and at Stop inside a local row |
| voice detector mode 1 / mode 2 | 211 / 296 / 310, 206 / 291 / 310 | 0, 0 | pass, but invented 15-weight runs then touch 0.39 s / 0.34 s stretches against the 0.40 s bar (0.20 s at mode 3) |
| stretch 0.2 s / 0.3 s / 0.5 s | 211 / 296 / 315 for the first two, 201 / 286 / 305 | **7**, 0, 0 | 0.4 s is twice the longest invented case; 0.3 s also passes |
| weight 10 / 20 | 210 / 297 / 312, 193 / 268 / 283 | **4**, 0 | 15 is the lowest passing bar; 20 costs 27 saved units |
| coverage 0.5 / 1.0 | 211 / 296 / 310, 206 / 291 / 310 | 0, 0 | flat |
| margin 3 dB / 12 dB | 211 / 296 / 315, 201 / 286 / 305 | 0, 0 | flat within 5 units |
| echo return = 0.3 / 0.7 quantile | 211 / 296 / 310, 182 / 267 / 286 | 0, 0 | a high quantile is pulled up by the local voice itself; the median is the highest safe choice |
| holes bridged 0 ms / 100 ms | 198 / 283 / 302, 211 / 296 / 315 | 0, 0 | flat |
| stress, today's rule / candidate / candidate without coverage | 90 / 101 / 157, 206 / 291 / 310, 211 / 296 / 310 | 0, 0, 0 | echoed units committed: 0, 0, **1** |

Every variant committed 0 units in the five nobody-speaking engine cells, and none is below today's rule in any
cell. The scorer flags 3 units under today's rule and 5 under the candidate as "not in the reference text but
said by the tab": all are real local words ("of", "uh", "我").

**A local turn that fills the window** (`vlong.py`; a 28 s turn over the tab, 20 dB under it, the case where the
median could be pulled up by the local voice itself): the provider returned 51 words; today keeps 0 in every
pass; the candidate keeps 15/15, 39/40, 11/11 in the three live windows and 51/51 saved.

### Candidates rejected by numbers

- **Duration alone** (first-draft C1: voiced unexplained audio, fixed -15 dB reference, voice detector mode 1).
  Noise events give 0.56-0.88 s, real 3-5 word phrases 0.68-1.05 s: no threshold. And the fixed reference calls a
  local voice 16 dB or more under the tab "explained" (lead amendment 2). Rejected before any engine run.
- **C1x, least-squares echo removal.** Not built. It can only help where the echo is a linear copy of the tab
  (file-backed fixtures, echo cancellation off); no gate needs it there, and real post-cancellation residue is not
  linear. Unmeasured.
- **C2, the preview agrees.** R5-D's 10 instant-word streams: it heard the real phrases (9 of 9: no echo and -40 dB) and it
  heard the echo just as well (the microphone preview's final texts in both listen-only cells are the tab's
  sentences, which the 15 s window also returned). So agreement cannot separate local speech from echo, its
  timing is a whole turn (10-16 s), and it does not exist for OpenAI-compatible providers. Against noise-invented
  text it is unmeasured (round 4's streams were deleted; a 480 s stream costs $0.07). Rejected as the primitive.
- **C3, voice match with earlier local speech** (`c3_voice.py`, production encoder, one embedding per stretch).
  Cosine to the same voice's long-turn anchor: replies over 1.2 s 0.63-0.82, 0.6-1.2 s 0.43-0.78, under 0.6 s
  0.35-0.51. Not the local voice: noise events at most 0.19, residue at most 0.37, plain echo at most 0.46, another
  local voice at most 0.44. So it could add 2-word replies, not 1-word ones, only after a 2 s turn exists, at one
  embedding per stretch - and in those meetings the saved pass keeps them already. Not adopted.
- **C4, the 2 s anchor alone.** Today: 0 of 15 in 5 of 5 short-phrase cells. Kept only as the sufficient
  condition it already is, which is what makes "never below today" hold.

### Other findings (outside F2; numbers for the lead)

- **F-a The text echo guard does not see through Chinese script variants.** The provider answers a request in
  simplified or traditional characters at random; when the two lanes differ the guard's exact-token test lets
  the echoed characters whose forms differ through: 19 of 67 and 40 of 107 echoed words in two listen-only probes
  (0-8 when the scripts agree). Today the level gate and the anchor hide this. Folding variants before comparing is
  a separate fix.
- **F-b The provider does not return a short phrase said over the tab when the echo is -25 dB or stronger**
  (0 of 3 answers each at -25 and -15 dB; it transcribes the tab's sentence instead). The instant-word model did
  hear it at -25 dB ("Can you elaborate on Alan Turing?").
- **F-c The level gate, not the anchor, is what removes a normal-length local turn in double-talk**: at 16 dB or
  more under the tab every word of a 6 s turn is dropped (0 of 31 saved in 4 of 4 long-turn series), 2 s span
  or not.
- **F-d Clean-up can save fewer local words than the live transcript held** (long turns over the tab at 4-10 dB
  under: live 26, saved 24 of 31) - F3's subject.

## Production change (implementation-ready; nothing below is applied in this phase)

One new class and three edited call sites in `moss_transcribe_diarize/app/gemini_lane_engine.py`, the counters in
`gemini_live_runtime.py`, the wiring in `phase2_web_cli.py`. `evidence.py` + `candidate.py` are the code to lift.

1. **`gemini_lane_engine.LocalVoiceEvidence`** (new; numpy is already a dependency).
   - `__init__(self, system_read, *, vad_factory=None)` - `system_read(start, end) -> bytes` is the reader
     `AcousticEchoGuard` already gets; `vad_factory` defaults to `lambda: webrtcvad.Vad(3)` (a fresh detector per
     context, so the same audio always gives the same frames; tests inject a fake as they do for the level gate).
   - `local_words(self, mic_pcm16, words, *, offset_sample=0, whole_lane=False) -> dict[int, int]` - `{id(word):
     run number}` for the local words among `words` (the words *after* the voice-activity gate, before the level
     gate). Steps 1-6 of "The rule" above, verbatim from `candidate.local_audio` + `candidate.local_words`.
     With `whole_lane=True` the frames are judged in 30 s contexts every 15 s (constants `GEMINI_MIC_WINDOW_SECONDS`
     / `_STRIDE_SECONDS`). Production should compute only the contexts that overlap the words' time span, so a
     Stop tail costs milliseconds; the prototype computes the whole lane each time (the 260 ms per 480 s figure).
   - Also exposes `echo_return_db` and `sustained_seconds` of the last call for the diagnostics below (proposed;
     the prototype logs stretches and runs per call in `gates.jsonl` instead).
2. **`MicrophoneWordGate.__init__`** gains `local_voice: LocalVoiceEvidence | None = None`. `None` = today's
   behaviour exactly (every existing test constructs the gate without it and must pass unchanged).
3. **`MicrophoneWordGate.filter`** (live) - after `voiced = self.webrtc_gate.filter(...)`:
   - `local = self.local_voice.local_words(pcm16, voiced, offset_sample=offset_sample)` (or `{}`);
   - A: `acoustic` = today's `self.acoustic_gate.filter(...)` result plus the `voiced` words whose id is in `local`,
     in `voiced` order;
   - C: the text guard result is `filter_voice_aware(kept, system, vectors)` plus the local words that survive
     `filter_voice_aware(kept, system, {label: None for every label in kept})` (phrase matches only);
   - B: `if kept and not attributed_embedding_intervals(kept):` keep the words in `local` whose run still weighs
     15 (`sum(3 if single CJK character else 5 for each _preview_units(word.text))`), drop and count the rest as
     today; `elif kept: self.local_speech_seen = True` unchanged.
4. **`MicrophoneWordGate.filter_terminal`** (saved, and the Stop tail) - the same A and C with `whole_lane=True`;
   B replaces the `else: withheld, kept = len(kept), ()` branch: the surviving local runs are kept, the rest is
   withheld and counted; `local_speech_seen` is **not** set by them.
5. **Counters** (`MicrophoneWordGate._record` -> `report_drops` -> `GeminiLiveRuntime.record_engine_call` ->
   `_GeminiState` -> `engine_diagnostics`, per meeting and per lane like the five existing ones):
   `mic_words_from_provider` (words after the voice-activity gate), `mic_words_kept_by_local_voice_level` (A),
   `mic_words_kept_unanchored_by_local_voice` (B), and two gauges `mic_echo_return_db` (last measured) and
   `mic_local_voice_seconds` (sustained unexplained seconds so far).
6. **Wiring** (`phase2_web_cli._build_gemini_live_runtime_factory`): `local_voice=LocalVoiceEvidence(lambda start,
   end: lane_engine.lane_tape("system").read(start_sample=start, end_sample=end))` into `MicrophoneWordGate`;
   policy entry `"microphone_local_voice": "echo_return_median_plus6dB_vad3_0p4s_weight15_coverage0p8"`;
   `provider_revision` `hybrid-w3-mic-short-v8` -> `-v9`.
7. **Docs**: `docs/design-gemini-live.md`, the microphone-gate paragraph (lines 91-103) and the evidence table row
   "E1 microphone acoustic gate" ("quiet operator gain 0.1 defeats this rule" is what A repairs).

| Parameter | Value | Measured margin |
|---|---|---|
| voice detector mode for the evidence | 3 | invented runs weighing 15+ touch stretches of at most 0.20 s at mode 3, 0.34 s at mode 2, 0.39 s at mode 1 (bar 0.40 s) |
| echo return | median of microphone/tab level over tab-voiced frames, at least 1 s of them | 0.3-0.7 quantile: same result on all cells |
| margin over the echo return | 6 dB | echo-only frames spread 3.4 dB above the median; 3-12 dB: same result on all cells; echo-only lanes: longest stretch 0.04 s |
| sustained stretch | 0.40 s, holes of 50 ms bridged | invented runs of weight 15+: at most 0.20 s; real English phrases of 3+ words at -40 dB echo down to 20 dB under the tab: at least 0.47 s; the Mandarin 5-character phrase said over the tab: 0.69 s at 10 dB under, 0.36 s at 20 dB under (not repaired there) |
| text weight | 15 (three words / five CJK characters; the unit weights of `_repeated_units`) | heaviest invented run on a sustained stretch: 10 |
| coverage | 80% of the run's words on unexplained audio | echoed runs at most 21%, real runs 100%, a run the provider merged with the echoed voice 62% |
| word pad, run join | 0.2 s, 0.6 s | the product's existing values, not swept |

**Where it sits next to the other round-5 changes.** F1 (preview trim) and F3 (clean-up replacing live words) are
in `gemini_live_runtime.py`'s publication path; this change touches that file only in the counter plumbing. Rule W
(`gemini_long_final.py` / `gemini_final_policy.py`) assigns speakers; this change decides which microphone words
exist before any speaker is assigned, and reads the provider's raw labels in live windows and the labels after
`FinalWordPolicy.remap` in the saved pass. If rule W merges or splits microphone labels, a run can fail the
coverage or weight test and fall back to today's behaviour - recall can move, admission of non-speech cannot.

## Regression tests to add (`tests/gemini/test_gemini_lane_engine.py`; fake voice detector and synthetic levels,
word lists copied from the recorded patterns)

1. `test_local_voice_frames_use_the_measured_echo_return_not_a_fixed_level` - tab at amplitude 1000; microphone =
   its echo at -10 dB: no sustained stretch (the fixed -15 dB test alone would call it local); add a voice 20 dB
   under the tab over a -40 dB echo: one sustained stretch.
2. `test_short_local_phrase_with_no_two_second_span_is_published_live` - R5-D pattern: an echoed run of 29 words
   (label 0) and `Can you elaborate on that?` 8.4-9.2 s (label 1) over local audio 8.0-9.1 s: exactly the 5 words
   come back; counts `unanchored_window_dropped_words` absent, `mic_words_kept_unanchored_by_local_voice == 5`.
3. `test_listen_only_echo_window_publishes_nothing_with_local_voice_enabled` - 63 echoed words, echo at -25 dB:
   `()`, counters as today.
4. `test_words_on_a_noise_event_are_not_local_speech` - a 0.6 s voiced burst with `Think about` and with
   `后 一 个。`: `()` (weights 10 and 9).
5. `test_residue_fragments_are_not_a_sustained_stretch` - three 0.2 s bursts 0.5 s apart with `Oh about the
   words` (weight 20): `()`.
6. `test_echoed_voice_overlapping_local_speech_is_not_rescued` - a 31-word echoed run across 3-15 s, local audio
   8.0-9.1 s, no local words (the -25 dB pattern): `()` and the level gate's drop count is unchanged.
7. `test_quiet_local_turn_under_the_tab_passes_the_level_gate` - 24 words 6.2-12.0 s, voice 20 dB under the tab,
   real `AcousticEchoGuard`: all 24 kept, `local_speech_seen` true, `mic_words_kept_by_local_voice_level == 24`.
8. `test_local_words_lose_only_echo_phrases_to_the_text_guard` - `好 的， 没 问 题。` with the tab saying `的`
   within 1.5 s: 5 kept; with the tab saying `没 问` at the same time: nothing kept (the rest weighs 9).
9. `test_saved_pass_keeps_local_runs_without_opening_the_lane` - three 5-word phrases 15 s apart and a stray
   `No.`: 15 words saved, `lane_withheld_words == 1`, `local_speech_seen` false.
10. `test_one_and_two_word_replies_stay_withheld_without_other_evidence` - `Yeah.` and `Thanks everyone.` on
    sustained stretches: `()` live, counted as unanchored (today's behaviour, stated as a limit).
11. `test_saved_pass_and_live_window_judge_the_same_stretch_alike` - the same 30 s of audio through `filter` and
    through `filter_terminal`: the same local words.
12. `test_engine_diagnostics_report_local_voice_counters` (`tests/gemini/test_gemini_live_runtime.py`).
13. Every existing microphone-gate test unchanged (they build the gate without `local_voice`).

## What it cannot do

- **One- and two-word replies** ("Yeah.", "好的。", "Thanks everyone.") with no 2 s turn near them stay as today:
  grey, then gone; saved only when the lane has a 2 s turn. An invented word on a noise event looks the same
  (2 words / 3 characters measured), and the voice match that could tell them apart needs 0.6 s (C3).
- **A phrase the provider never returns** (said over the tab with echo at -25 dB or stronger in the lane): 0 of 5.
- **A phrase the provider files under the echoed voice's label** in that answer: not repaired in that pass (1 of 3
  Mandarin phrases live; the saved pass got it at 10 dB under the tab, not at 20 dB under).
- **Speech under about -40 dBFS in the microphone lane, or within about 5 dB of the tab's echo there.**
- **A voiced non-speech sound of 0.4 s or more** (throat clearing in the fixtures; humming, laughter - unmeasured)
  **on which the provider puts three or more words**: admitted. Measured heaviest: 2 words / 3 characters in 908.
- **Real echo-cancellation residue.** Every echo here is a copy of the tab (three-tap room, or round 4's gated
  band-limited fragments). A physical microphone after Chrome's echo cancellation was not measured: (i) how much it
  attenuates the local voice in double-talk; (ii) whether residue bursts of 0.4 s stand 6 dB above the meeting's
  median echo return (for example in the first second while the canceller converges). (ii) would show as "You"
  rows holding the tab's words, unless the text guard matches them.
- **Another person or a television in the room** is admitted as microphone speech from 0.4 s (today from 2 s).
- The grey microphone row is unchanged (D3).

## Stress matrix

| Cell | Provider answers | Engine path | Result |
|---|---|---|---|
| short EN phrases x3: no echo, -40, -25 dB (tab talking + silent) | R5-D recorded | ran | repaired except over the tab at -25 dB (provider) |
| short ZH phrases x3, -40 dB | R5-D recorded | ran | saved 15/15, live 5 of 10 possible |
| short ZH at -25 / -15 dB echo | none recorded | **not run** | - |
| long EN turns -40, -25 dB; long ZH -40 dB (controls) | R5-D recorded | ran | never below today |
| long EN turns wholly over the tab, 20 dB under it | new (paid) | ran | 0/31 -> 27/31 |
| one 28 s EN turn over the tab, 20 dB under it | new (paid) | ran | 0/51 -> 51/51 provider words |
| short EN / ZH, 20 dB under the tab, -40 dB | new (paid) | ran | 15/15; 9/15 |
| 8 varied EN replies, 8 varied ZH replies (1-8 words) | new (paid) | ran | 3+ words 25/25 and 25/25; 1-2 words unchanged |
| short replies beside a long turn | new (paid) | ran | 32 -> 36 of 37 saved |
| -15 dB echo: short EN, listen-only | new (paid) | ran | 0 echo committed; 10/15 |
| room-noise events + -40 dB echo, nobody speaking | new (paid) | ran | 0 |
| listen-only -40, -25 dB | R5-D recorded | ran | 0 |
| level sweep 4-24 dB under the tab, 9 series x 7 levels | reused words (2 recorded levels) | ran, gates only | table above |
| level sweep at -25 dB echo with words recorded at the quiet end; ZH at -25 dB | none | **not run** | - |
| round-4 listen-only lanes A, B (480 s), saved pass | new (paid) | gate chain, no tab words (upper bound) | 0 of 560 |
| round-4 lanes, live 30 s windows x26 | new (paid) | gate chain, no tab words | 0 of 348 |
| round-4 lanes through the whole engine (tab lane answers) | none | **not run** (would cost about $0.34 per lane) | - |
| round-4 noise pilot windows (12 kinds x 4), Q-MIC -20 / -10 dB echo, round-4 hp/sp/v1 lanes | none | audio scan only | stretches listed; no provider answer |
| instant-word (preview) streams on the new cells and on noise lanes | none | **not run** | C2 and G5 measured on R5-D's 9 cells only |
| real Chrome + real UI | - | **not run** | the change is behind the provider; R5-D's browser run is not replayable |
| physical microphone, real echo cancellation, real double-talk | - | **cannot be run here** | attended check below |
| meetings over 15 minutes (chunked saved pass), OpenAI-compatible provider | - | **not run** | cost extrapolated from 480 s |

## Attended check on the MacBook (2-3 minutes; built-in speakers and microphone, no headphones)

Share a tab that talks continuously (any interview or podcast video at normal volume), start a meeting, then:

| Time | Do | Expect after the fix |
|---|---|---|
| 0:00-0:30 | say nothing | no solid "You" row (grey fragments of the tab may still flicker: D3) |
| 0:30 | over the tab, normal voice: "Can you elaborate on that?" | solid within about 15-30 s |
| 0:50 | over the tab, one long sentence (5-6 s): "I think the plan is fine, but we should measure the latency before we decide." | solid within about 15-30 s |
| 1:15 | pause the video; say "Okay, sounds good." then, 5 s later, "Yes." | the first solid; "Yes." may never turn solid live (known limit) |
| 1:35 | play again; clear your throat, type for 5 s, laugh once - no words | no solid "You" row |
| 1:55 | over the tab, quietly (as if not to interrupt): "Let me check and get back to you." | solid, or missing - this is the unmeasured part |
| 2:15-2:35 | say nothing, then Stop and wait for clean-up | the four sentences are in the saved transcript under You; nothing else is |

Then read `engine_diagnostics` (it is in the snapshot the page already polls; see D4):

| Counter | What it says |
|---|---|
| `mic_words_from_provider` (new) | 0 or far too few: the provider did not hear the microphone speech - echo cancellation suppressed it or the provider chose the tab; no gate can help |
| `mic_words_dropped_by_acoustic_gate` | words more than 15 dB under the tab that carried no local evidence (the tab's own echo is expected here, in the hundreds) |
| `mic_words_kept_by_local_voice_level` (new) | above 0: words that today's level gate would have dropped - double-talk attenuation is real on this device |
| `mic_words_dropped_unanchored`, `mic_words_withheld_unanchored_lane` | words with neither a 2 s span nor local evidence (the 1-word reply; a phrase filed under the tab's voice) |
| `mic_words_kept_unanchored_by_local_voice` (new) | the short phrases this fix published |
| `mic_words_dropped_by_text_guard`, `mic_echo_dropped_by_voice` | echo caught by words / by voice |
| `mic_echo_return_db`, `mic_local_voice_seconds` (new) | the device's real echo return (expected under -35 dB) and how many seconds of sustained local speech the audio showed (expected: about the seconds you spoke; near 0 with missing sentences = the voice did not stand out from the residue) |

A solid "You" row during 0:00-0:30 or 1:35 with `mic_words_kept_unanchored_by_local_voice` above 0 is the failure
this prototype could not measure (residue or a non-speech sound admitted).

## Decisions for the lead / user

- **D1** Build the change as specified (A + B + C). Recommended.
- **D2** Text weight 15 (three words / five characters; saved 310 of 343) or 20 (the existing "sustained" bar;
  saved 283, loses "Okay, sounds good." and "好的，没问题。"; heaviest invented run 10 either way). Recommended: 15.
- **D3** The grey microphone row: build the row-level test as a follow-up (48 of 48 echo-only grey snapshots gone,
  0-0.5 s delay), or leave. It needs the frame facts kept as audio arrives.
- **D4** Save `engine_diagnostics` (content-free counters) with the meeting when it is saved. Recommended: R5-D
  could not tell which rule acted in the user's meeting because nothing was kept.
- **D5** Fold Chinese script variants in the text echo guard (finding F-a). Separate small fix; not needed by D1
  (the coverage rule covers it: stress row above).
- **D6** Run the attended check before calling F2 fixed on the real device.

## Spend

68 batch requests, $0.2368 with the output estimate, cap $0.25 (`spend.json`): round-4 listen-only lanes
$0.0845, 26 live windows $0.0687, 10 new engine cells $0.0836. No instant-word stream was bought. Key scan of the
evidence and prototype folders: see `keyscan.json`.
