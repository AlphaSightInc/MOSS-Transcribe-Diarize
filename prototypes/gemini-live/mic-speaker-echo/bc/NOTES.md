# R5B-BC — microphone admission × witness restoration (throwaway, phase 1)

## Contract — before measurement

**Structural question.** Can the saved microphone transcript recover a live-only local reply without admitting
live-only echo or invented words, even after a real turn has anchored the lane?

**Minimum primitives.** Lane (owns audio/text); timed word (provider text and span); clean-up hole/live witness run
(F3 H, owns omission evidence); unexplained microphone frames/local-run evidence (F2, owns local-speech admission);
final speaker label (assigned after admission, owns identity only). Text omission and local audio are independent
facts; neither a neighbouring label nor an anchored lane proves that a witness is local speech.

**Invariants.** I1 clean-up words pass exactly the F2 microphone gates before restoration. I2 judge each H run alone,
never joined to clean-up neighbours by speaker label. I3 restore microphone words only with F2 local-run evidence,
even when local_speech_seen is true. I4 labels assigned after admission; W on/off cannot change microphone admission.
I5 H retains all clean-up words and preserves system-lane final labels; no worse recorded F2/F3 counts or duplicates.
I6 $0 provider calls; neighbouring worktrees/evidence read-only; no production edits in phase 1.

**Hypothesis.** Gate clean-up first, judge each >=0.15 s H candidate with F2's measured local evidence alone, then
assign the nearer kept microphone label (or the lane's local label). System H stays after W and before word gates.

**Assumptions/unknowns.** Recorded answers measure deterministic replay, not fresh provider behavior or physical echo
cancellation. The round-4 three invented live words have saved text but no retained raw answers: reproduce that
pattern explicitly with deterministic timed witnesses on public fixture audio, label it an injection. One-/two-word
omitted replies and words the provider never returned remain outside the restoration guarantee.

**Falsifier.** Any 3–6-word omitted local reply at -10/-20 dB under tab fails; any invented/noise-only candidate is
restored including anchored lanes; any recorded F2/F3 metric regresses; W changes microphone admission; any required
cell is unexercised (UNMEASURED blocks phase 2).

**Tool decision.** Python replay in the production classes plus process-local F2/H patches is necessary to exercise
actual gates/engine with saved responses at $0. First measure naive restore-before-gates (6/31 unexplained => 0
eligible), then required order. Re-run every recorded F2/F3 cell and W on/off; a regression changes the design or
blocks implementation. Print relevant word/frame/run/label state and keep receipts in evidence/P72/bc.

**One command (no key, no network).**

```sh
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/mic-speaker-echo/bc/run.py
```

## Required measurements

A: 3–6-word omitted reply among kept echo at -10/-20 dB; naive order first, then isolated order.
B: round-4 是。哦。六。 beside real turn + deterministic live-only noise, anchored and unanchored.
C: all recorded F2/F3 cells; saved/live units, names, extra/doubled units vs prototypes.
D: A–C with actual W label step off/on; identical microphone admission.

Results, full microphone rule, regression seeds and verdict added after measurement.

## Execution details and corrections

- The harness extends `f3/engine.py`: real runtime factory, public lane tapes, actual live commits, real production
  voice activity, acoustic, voice/text echo guards, identity encoder, continuity registry, terminal and stitcher.
  F2/H/W are imported read-only; patches live only in the replay process. Every provider request needs a recorded
  response; a missing answer fails instead of calling a provider. The original source evidence is never rewritten.
- `probes.py` reproduces the reviewer denominator on public phrase audio with six explicitly constructed timed
  words (the sixth token is an injection, not fresh provider evidence). The production-engine omission runs use
  the **five actual words committed by F2**. Both measurements are retained and distinguished.
- The whole-engine three invented characters and noise witnesses are deterministic committed-word injections on
  the public `inv-events` lane, not claims that a new model produced them. Clean-up retains the recorded 24-word
  real turn; it omits only the attack witnesses. F2's 28 independent recorded negative samples widen that attack.
- An observer initially intercepted *every* call to the shared voice-activity gate, including isolated candidate
  calls. With injected clean-up it incorrectly substituted echo neighbours for a candidate, returning 0/5.
  `injected-engine-observer-failure.log` retains the failure. The observer now captures only the terminal's first
  gate call. Affected cells are re-exercised, not scored from that failed harness.
- Hole discovery reads the **ungated clean-up word timeline**: removal by a gate is not a provider omission.
  After clean-up gates finish, each candidate independently passes voice activity, local evidence and the F2
  microphone guards. Labels use only kept clean-up neighbours, never a previously restored run. The placement
  audit replays any older receipt whose candidate list or observer could change. No evidence threshold changed.
- The 100-pair matrix with W uses actual final W labels from the newly replayed engine answers, shifted across
  the original five live samples. W is executed on the system lane before H, including the real two-chunk stitch
  and exact-truth three-speaker controls. The microphone's evidence does not inspect W's system labels.
- One import-resolution error in `repair_replay.py` selected F3's `run.py` rather than BC's. That script reprinted
  its cached $0 tables and regenerated original F3 **derived summary tables**. Original raw provider responses,
  audio, engine runs and receipts were not modified; no provider call occurred. BC helpers now load their runner
  by explicit file path. This source-summary write is a custody deviation, retained here for the lead.

## Final microphone-lane rule — implementation handoff

1. Keep the exact provider clean-up timeline after its identity step. H's hole calculation uses that **ungated**
   timeline, so a word removed by a gate is not misclassified as an omission. H witness ownership, timing step,
   edge-word equality and coverage-fallback skip intervals remain exactly `f3/rule.py`.
2. The clean-up words pass voice activity and the F2 microphone gate chain normally, before any witness is inserted.
   F2 decides level/voice/text admission and the existing lane anchor exactly as it does without H. Keep its output.
3. Form each H candidate independently: consecutive owned live witnesses in one provider hole; at most 0.1 s
   covered per word, not fully covered; equal adjacent edge words removed; uncovered run time at least 0.15 s;
   skip any interval owned by the existing >=10 s fallback.
4. For **that candidate alone**, pass voice activity and obtain F2 unexplained-audio frames in the same 30 s/15 s
   whole-lane contexts. Detector mode 3; median microphone/tab echo return with >=1 s tab speech, otherwise -15 dB;
   unexplained speech while tab silent or >6 dB over echo return; sustained >=0.4 s, <=50 ms holes bridged;
   existing 0.2 s word pad and 0.6 s label-run join. At least 80% of the voiced run's words must touch unexplained
   audio; words on it weigh >=15 (word 5, single CJK character 3); run must touch a sustained stretch.
5. Keep only those local words. Apply the same F2 level/voice/text guards to that isolated admitted run; local words
   lose text admission only to the measured two-word echo-phrase guard. Each surviving local run must still weigh
   >=15. `local_speech_seen=true` **never waives** steps 4–5. Do not combine candidates or neighbouring clean-up
   words by speaker label to manufacture or dilute admission evidence.
6. Only after admission, label the restored run with the nearer **kept clean-up** neighbour (distance from run edge,
   earlier neighbour wins a tie); no kept neighbour -> the microphone lane's local label. A previously restored
   run is not a clean-up neighbour. Keep provider text/times, extending zero-length words to the measured 0.1 s
   step as H already does. Insert in time order; count only actually admitted `witness_restored_words`.
7. System lane remains measured F3 H: after final identity/stitcher/W labels, before word gates. Every retained
   clean-up word keeps its label; restored words copy the nearer final neighbour. No microphone evidence or W
   label operation moves words between lanes.

### Limits

- A one-/two-word omitted reply (weight <15) is not restored, even on an anchored lane. A Mandarin reply needs at
  least five character units. This is a known limit, measured by the length probes, not an implementation defect.
- Cannot recover words live never committed or words replaced by clean-up text covering their time.
- No requirement to restore a committed microphone word without fresh local evidence of its own: this deliberately
  closes round 4's anchored-lane invention path. System-lane live-only inventions remain H's known limitation.
- F2 still cannot distinguish sustained voiced non-speech that a provider assigns >=3 words from local speech.
  None admitted in the recorded negatives; that is a bounded observation, not a general guarantee.
- Physical echo cancellation, real microphone attenuation, new provider answers, >900 s product chunk plan and
  OpenAI-compatible provider behavior remain UNMEASURED outside this $0 phase. Per-run evidence scans the complete
  microphone tape like the F2 prototype; production should use WP-B's bounded overlapping-context implementation.

## Regression tests needed in phase 2 (none added to production in phase 1)

Retain F3's 12 rule tests + 3 terminal tests + 3 engine tests, and all F2 regression meanings. Add:

- BC-T1 naive restore-before-gates merges 6/31 words under echo label -> 0 local; isolated restore -> 6/6 at -10/-20 dB.
- BC-T2 actual five-word F2 committed reply omitted by provider, echo neighbours retained: whole engine saves 5/5,
  no echo, finalization completes, both levels.
- BC-T3 same sustained stretch: 3/4/5/6-word restores admitted; 1/2-word omitted replies withheld, anchored included.
- BC-T4 three round-4 characters 是。哦。六。 omitted beside real 24-word local turn: 0 restored, turn intact,
  `local_speech_seen=true`; exercise initially unanchored and already anchored gate state.
- BC-T5 voice-gated three-word noise burst with weight 15 but no sustained stretch: 0; five-word noise-only run: 0.
- BC-T6 repeat BC-T1…5 with actual system W off/on: identical microphone text and times.
- BC-T7 clean-up gated removal does not create an H provider hole; candidate-local evidence must not borrow neighbouring
  words or previously restored labels. Empty kept microphone clean-up with an eligible reply uses local lane label.
- BC-T8 F3 window-frontier owner, equal edge word, numeral equality, coverage fallback ownership, and post-W labels
  preserved; actual chunked terminal and truth controls retain their measured results.

These are test seeds, not certification claims. Only phase 2 writes the tests and production rule; the brief requires
red-before/green-after evidence there. Phase 1's naive-rule failure and composed-rule success are prototype evidence.

## Measured verdict — PASS, phase 1 only

**The composition works on every required recorded/control cell.** Each restore is evidence-gated independently;
provider holes decide which words are candidates, microphone audio decides whether those candidates are local,
then a final label decides which row owns admitted text. No production implementation or provider call occurred.

| Gate | Prototype/control | BC, W off | BC, W on |
|---|---:|---:|---:|
| BC-A reviewer naive denominator, -10/-20 dB | 6/31 unexplained; 0 local words | reproduced | reproduced |
| BC-A isolated six-word control, -10/-20 dB | omitted 0/6 | 6/6 each | 6/6 each |
| BC-A whole engine, actual five committed words, -10/-20 dB | omitted 0/5 | 5/5 each | 5/5 each |
| BC-B whole engine, invented 是。哦。六。 beside real turn | clean-up omits 3; real turn 24 | restores 0; keeps 24 | restores 0; keeps 24 |
| BC-B whole engine, live-only three-word noise | clean-up omits 3; real turn 24 | restores 0; keeps 24 | restores 0; keeps 24 |
| BC-B 28 recorded round-4 negatives, 908 voice-gated words | F2 0 | restores 0, anchored off/on | restores 0, anchored off/on |
| BC-C F2 18 engine cells, live / Stop / saved, denominator 343 | 206 / 291 / 310 | 206 / 291 / 310 | 206 / 291 / 310 |
| BC-C F2 long-voice cell, before Stop / Stop / saved words | 41 / 52 / 51 | 41 / 52 / 51 | 41 / 52 / 51 |
| BC-C F2 63 level cells (9 series ×7 levels) | frozen per-cell recall | every cell >= prototype | every cell >= prototype |
| BC-C F3 100 pairs, lost names | 4 (today: 115) | 4 | 4 |
| BC-C same pairs, missing / extra units mean | 2.06 / 1.25 | 2.06 / 1.25 | 2.06 / 1.25 |
| BC-C same pairs, doubled adjacent units | 0 | 0 | 0 |
| BC-C F3 25 system-pair engine cells, names /250 | 236 | 236 | 236 |
| BC-C F3 truth controls, speaker error, prefix 0 /3 s | .0907 / .1217 | .0907 / .1217 | .0907 / .1217 |
| BC-C F3 every recorded engine word retained (45 runs) | original H text/times | none lost | none lost |
| BC-C added duplicate word occurrences; row ownership failures | comparative bar 0 | 0; 0 | 0; 0 |
| BC-D microphone admission differences | W must change none | **0 across every pair** | **0 across every pair** |

**Population actually exercised:** 128 fresh engine replays (45 F3 +19 F2, each W off/on), 126 fresh sweep replays,
8 whole-engine injected replays, 36 isolated probes, 112 recorded-negative conditions (28 ×W ×anchor), 200
100-pair combinations using actual W labels, 16 original H patterns. The placement correction inspected 106
older microphone receipts and re-exercised 6 affected cells. No required BC cell is UNMEASURED.

### F2 recorded engine cells — unchanged or better, both W states

Values below are prototype -> BC, W off and on identical. Extra microphone words on listener-only lanes remain 0.

| Cell | Live units | Stop units | Saved units |
|---|---|---|---|
| listen-aec40 | 0/0 -> 0/0 | 0/0 -> 0/0 | 0/0 -> 0/0 |
| listen-echo25 | 0/0 -> 0/0 | 0/0 -> 0/0 | 0/0 -> 0/0 |
| short-aec40 | 10/15 -> 10/15 | 15/15 -> 15/15 | 15/15 -> 15/15 |
| short-echo25 | 5/15 -> 5/15 | 10/15 -> 10/15 | 10/15 -> 10/15 |
| short-noecho | 10/15 -> 10/15 | 15/15 -> 15/15 | 15/15 -> 15/15 |
| zhshort-aec40 | 5/15 -> 5/15 | 10/15 -> 10/15 | 15/15 -> 15/15 |
| long-aec40 | 22/31 -> 22/31 | 27/31 -> 27/31 | 27/31 -> 27/31 |
| long-echo25 | 22/31 -> 22/31 | 27/31 -> 27/31 | 27/31 -> 27/31 |
| zhlong-aec40 | 24/40 -> 24/40 | 36/40 -> 36/40 | 40/40 -> 40/40 |
| dlong-e40-L37 | 27/31 -> 27/31 | 27/31 -> 27/31 | 27/31 -> 27/31 |
| short-e40-L37 | 10/15 -> 10/15 | 15/15 -> 15/15 | 15/15 -> 15/15 |
| zhshort-e40-L37 | 5/15 -> 5/15 | 10/15 -> 10/15 | 9/15 -> 9/15 |
| varied-en-e40-L27 | 17/29 -> 17/29 | 25/29 -> 25/29 | 25/29 -> 25/29 |
| varied-zh-e40-L27 | 14/39 -> 14/39 | 29/39 -> 29/39 | 39/39 -> 39/39 |
| mixed-e40-L27 | 30/37 -> 30/37 | 35/37 -> 35/37 | 36/37 -> 36/37 |
| short-e15-L27 | 5/15 -> 5/15 | 10/15 -> 10/15 | 10/15 -> 10/15 |
| listen-e15-L27 | 0/0 -> 0/0 | 0/0 -> 0/0 | 0/0 -> 0/0 |
| listen-e40-L27-n3 | 0/0 -> 0/0 | 0/0 -> 0/0 | 0/0 -> 0/0 |

### Scoring boundaries retained, not hidden

- BC-S1 F2 now admits repeated genuine short replies which F3 alone withheld. In 10 W-expanded engine cells the
  old broad repeated-text metric rises from 0 to 5/10 units because the participant really says the same reply at
  different times. Truth scoring gives **0 extra units** for those microphone rows. These are admitted speech,
  not doubled speech. Original raw metrics and the separate time/truth explanation are retained in `verdict.json`.
- BC-S2 In 42 W-expanded sweep cells the row-overlap echo proxy rises although **all three microphone surfaces are
  byte-identical in text and time to F2**. H extends a system row into the scorer's window, and its common-word
  token set changes. No new microphone word exists. The raw proxy increases remain in `sweep-matrix.json`; the
  comparative admission finding uses demonstrated identical microphone output, not a retuned echo rule.
- BC-S3 The two original noise5 F3 controls already restore an `I I` tail whose two words have the same span.
  BC reproduces those exact two occurrences in both W states. The frozen F3 adjacent-duplicate scorer excludes
  `I` as a speech stutter. **No added duplicate**, but the repeated timestamp witnesses remain a system-H limit
  for the lead to review; this phase does not change H to remove them.

### Verification and reproducibility

- Full backend command from this worktree:
  `MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python -m pytest -q -p no:cacheprovider tests`
- Result: **2707 passed, 9 skipped, 2 xfailed, 27 warnings, 37 subtests passed**, 435.16 s. No production tests changed;
  phase-2 regression names/required before-after failures are above. Frontend out of scope.
- Run the command in the contract to reproduce all BC matrices. It replays recorded answers, prints state and
  refuses a missing answer. `validate.py` exits nonzero on incomplete population; its JSON records comparative
  regressions, actual/inherited repeated-word tuples, raw proxy changes, speaker error and W admission equality.
- Evidence root: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/bc/`. `population.json` fixes original engine
  commands/receipts; `engine-matrix.json`, `sweep-matrix.json`, `negative-matrix.json`, `injected-engine.json`,
  `probes.json`, `h-patterns.json`, `h-pairs-with-w-labels.json`, `placement-audit.json`, `speaker-error.json`,
  `backend-suite.log`, and `verdict.json` hold the full state and results. Each engine folder keeps recorded-call
  receipts, timed witnesses, terminal words, actual W state, microphone candidate decisions and both surfaces.
- One-command run retains the prototype for lead review/phase-2 regression absorption, as the explicit brief
  requires. It is not production scaffolding. Local commits only; $0 added provider cost; no push/merge/PR.

**Lead handoff:** G-BC passes on the frozen recorded population; authorize phase 2 only with written GO and the
branch cut from merged WP-B. Phase 1 stops at `Stage: BC DONE — waiting for lead`. Physical acceptance, new provider
behavior and product-code reproduction of this prototype belong to later phases. Review the source-summary
custody deviation and inherited system `I I` witnesses above; neither is silently removed from this result.
