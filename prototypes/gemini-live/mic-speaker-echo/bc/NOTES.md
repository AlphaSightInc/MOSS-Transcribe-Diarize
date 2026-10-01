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
