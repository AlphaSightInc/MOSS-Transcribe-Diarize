# R4-C follow-up: far-end echo in the microphone preview (round-4 smoke S5 and S4)

In the round-4 real smoke, the grey microphone preview showed the far end's voice a second
time, because the microphone picked it up from the speakers. The worst case was 406 preview
words; at 194 s, 387 of the 397 words in the mic preview were system-lane speech. The
committed and saved mic text stayed clean, so only the preview was wrong.

## One command ($0 with the recorded streams in place)

```sh
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r4-c.venv/bin/python \
  prototypes/gemini-live/mic-preview-echo/sim.py --product   # baseline vs the product rule
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r4-c.venv/bin/python \
  prototypes/gemini-live/mic-preview-echo/sim.py             # every rule arm
```

`sim.py` takes recorded W3 updates (W3 is the instant-word model, `gemini-3.5-transcribe-live`)
for both lanes, plus timed committed rows. It runs them through the same steps as the
product, in order:

1. The hybrid engine's preview bookkeeping (finals and interims; the committed frontier
   every 15 s, published 4 s late).
2. The lane composer's mic echo test, which is the part each rule arm swaps out.
3. The runtime's `_trim_committed_preview`.

It then counts what the grey mic preview shows at every W3 update.

## Contract

- **Structural question.** A mic preview row holds W3 text with no word timing. With speaker
  echo, one W3 turn never ends and grows to hundreds of words, while its row is clipped to the
  mic frontier. Which words of that row are the far end's speech, and which are the local
  person's?
- **Root cause.** `_echoed_preview` compared the whole row only with the system *preview*
  rows. Those hold just the uncommitted suffix of the far end (the last 15 to 20 s). The
  committed system words that the row's head repeats were never consulted, so the row stayed
  under the 60% match share and was shown.
  - The same-lane head trim (`_trim_committed_preview`) cannot help either: the mic's
    committed text is gated and has the echo removed, so the preview's head does not match it.
- **Minimum primitives.**
  - The row's units: one per CJK character, other letter and digit runs whole, number words
    mapped to digits.
  - The system words the row could repeat: committed system rows plus the system preview
    ending within n/1.5 + 5 s of the row's end, where n is the row's unit count. Speech runs
    faster than 1.5 units/s, so this window covers any passage the row could repeat.
  - An in-order match (difflib blocks) that marks repeated runs.
  - The lane's own committed rows, to catch already-shown leftovers.
- **Invariants.**
  - A row that repeats nothing is shown unchanged.
  - Only runs that repeat the system lane, or that repeat the mic's own committed text inside
    a row that also held echo, are removed.
  - System rows are never touched.
- **Falsifier.** On the headphone and no-echo lanes, any loss of distinctive local preview
  words or any added first-display delay beyond about 0.5 s. Or echoed words that are not
  cut by a large factor on the speaker-echo lanes.

## Inputs (all public audio or local text-to-speech)

| Case | Mic lane | System reference | Local truth |
|---|---|---|---|
| E1 | `P52/lane-live-E1-mic.json`: W3 recorded on the E1 mic (−25 dB echo, room noise, 3 local phrases) | W3 recorded on the E1 system lane (`P52/robust-live-e1_system-en-US.json`); committed text from the P52 cached 30 s/10 s rolling windows | The three committed mic rows of the r4 smoke |
| M2 | `P52/lane-live-M2-mic.json`: room noise plus the 3 phrases, no echo | as E1 | as E1 |
| en-hp, en-sp, zh-hp, zh-sp | W3 runs from `mic-hallucination` (v1 fixture) | Cached batch words of the system lane (stand in for preview + committed); committed mic words from the gated rolling windows | Reference local turns and backchannels |
| zh-echo | **New W3 run.** v1 Mandarin local speech plus noise, with the Mandarin far end added at −25 dB (40 ms plus reflections) | **New W3 run** on the Mandarin system lane; committed = cached batch words | v1 Mandarin local turns and backchannels |
| qmic-sp10 | **New W3 run** on Q-MIC `speakers--10-mic.wav` (Lex/Keyu with −10 dB echo) | **New W3 run** on Q-MIC `system.wav`; committed = cached batch words | Q-MIC local turns |

**Scoring.**

- **Distinctive local units:** matched in blocks of at least 2 against the local reference
  text, and not matched against the far end's reference text.
- **Echoed units on zh-echo and qmic:** the mirror image, matched to the far end's reference
  text and not to the local text.
- **E1:** every non-local unit counts as echo, because E1 has no human transcript of its far
  end.
- **Latency:** the time from a local item's first display in the baseline to its first
  display under the rule. Only items of at least 4 units count.

## Results (`sim.py --product`; "product" is the shipped `gemini_lane_engine._without_echo`)

| Case | Echoed words in one poll, max (base → product) | Echoed words summed over polls | Distinctive local units summed over polls | Local items shown | Added first-display delay |
|---|---:|---:|---:|---:|---:|
| E1 (speakers, English) | 244 → 13 | 44,636 → 1,598 (−96%) | 1,107 → 1,099 | 3/3 → 3/3 | max 0.4 s |
| zh-echo (speakers, Mandarin) | 133 → 9 | 31,060 → 517 (−98%) | 45,176 → 44,530 (−1.4%) | 32/33 → 33/33 | 0 |
| qmic −10 dB echo (English) | 63 → 7 | 6,478 → 353 (−95%) | 27,294 → 29,605 (+8%) | 5/5 | 0 |
| M2 (no echo) | 2 → 2 | 66 → 66 | 542 → 542 | 3/3 | 0 |
| en-hp / en-sp | 5 / 4 → 5 / 4 | 267 / 257 → 267 / 266 | 5,456 / 5,521 → 5,456 / 5,523 | 13/15, 14/15 (both) | 0 |
| zh-hp / zh-sp | 7 / 5 → 7 / 5 | 631 / 526 → 631 / 535 | 15,160 / 19,905 → 15,163 / 19,908 | 31/33 (both) | 0 |

**Notes on the table.**

- On the no-echo lanes the "echoed" column counts non-local leftovers. These are W3 errors
  and short backchannels, and they are unchanged.
- E1 local units drop from 1,107 to 1,099. The 8 lost units are the already-committed local
  phrase that the baseline showed a second time.
- **Committed mic words shown again in the preview (the S4 class).**
  - Strip rule without the own-lane check: 55 polls on E1.
  - With the own-lane check (shipped): 0 polls.
  - Baseline: 0 in this replay. The smoke measured 5 of 725 snapshots.
- **Cost of the rule.** 0.3 to 0.5 ms per composed preview on average, 1.6 ms typical
  maximum, and one 14 ms outlier. Nothing is held back, so the only latency is that compute.
- **Residual echo** (7 to 13 words) is text the two models heard differently, for example
  `ND1 and ND` for `NV1 and NV2`.

## Arms rejected

- **Bag-of-words 60% with committed + preview as reference** (the old test with its
  reference fixed). On E1 it hides whole rows: a local item is lost and local units are cut
  by 40%. On qmic it hides 2 of 5 local turns, and it delays Mandarin rows by 49 s.
- **Row-level in-order share (60%).** It still hides local phrases inside echo-dominated
  turns; on E1 one item is lost.
- **Strip with 3-unit blocks for CJK as well.** It removes ordinary shared characters, for
  example 面我们 and 有提升. Weighting five CJK characters as three words fixes this.
- **Strip with the own committed text as part of the main reference.** It breaks
  `_trim_committed_preview`'s head alignment on the headphone lane and re-shows old heads.
  Hence own-lane text only filters the leftovers of a row that held echo.
- **The 2 s live-speech anchor applied to the preview.** Preview rows have no timing. Gating
  the preview on a committed anchored window would hold every new local turn back until its
  rolling commit, 15 to 30 s. That is a latency arm with no measured benefit over stripping.
- **Sensitivity:** leftover runs of at least 3, 4 or 5 units, and CJK blocks of 5 or 6
  characters, gave the same local retention within 0.5%. Runs of at least 4 were chosen
  because they also remove the 3-word tail flicker in the existing E1 regression test.

## Spend

Four new paced W3 streams of 300 s each (the zh-echo mic and system, the qmic mic and
system): **$0.1007** at the list-price estimate. Live usage metadata is absent. Everything
else replayed cached or recorded data at $0. The ledger lane `r4c-mic-halluc` now totals
$0.8552.

## Correction (2026-10-01): two-voice Mandarin fixture and run matching

Two things changed after the table above was recorded.

1. **The Mandarin fixture had one voice.** `say -v "Flo/Reed/Eddy (Chinese (China mainland))"`
   silently speaks as Tingting, so the `zh-echo`, `zh-hp` and `zh-sp` lanes used the same voice
   for the far end and the local person. The corrected lane is `zh2-echo`: Tingting far end,
   Meijia local, built and recorded by `prototypes/gemini-live/preview-script`.
2. **The corrected lane exposed a matching weakness.** The far end repeated sentences it had
   said 140 s earlier, and its own preview lagged. The echoed row then held a passage found
   only in the preview, followed by a passage found only in older committed rows. One
   in-order alignment (difflib) can match only one of the two.
   - Fix: `_repeated_units` now finds, for each position, the longest run that occurs
     anywhere in the reference.

`sim.py --product E1 M2 zh2-echo` (the other recordings were removed by an external
clean-up of the worktrees, so those rows of the table above stand as recorded):

| Case | Echoed units in one poll, max | Echoed unit-polls | Distinctive local unit-polls | Local items shown | Added delay (items of 4+ units) |
|---|---:|---:|---:|---:|---:|
| zh2-echo, before any rule | 423 | 126,023 | 32,275 | 17/18 | — |
| zh2-echo, d88be99d (in-order alignment) | 102 | 3,361 | 30,198 | 15/18 | ≤0.4 s |
| **zh2-echo, run matching (shipped)** | **10** | **225 (−99.8%)** | 29,981 (−7.1%) | 14/18 | ≤0.4 s |
| E1, run matching | 13 | 1,594 | 1,099 | 3/3 | ≤0.4 s |
| M2, run matching | 2 | 66 | 542 | 3/3 | 0 |

- E1 and M2 are unchanged by the matching fix (E1 was 13 and 1,598 before).
- **The local loss on zh2-echo is short replies.** `好的`, `是的` and `没问题`, spoken while
  the far end is echoing, sit as leftovers of under four units inside an echo row. They are
  dropped from the grey preview and appear with their commit. Sentences are not affected.
  - The earlier one-voice lane reported −1.4%; it understated this.
- On the no-echo lanes of `preview-script` (zh2-sp, en2zh, zh2en), genuine word-polls are
  identical under both matchers: 23,506, 19,199 and 35,332.
- Cost: about 0.5 to 0.7 ms per composed preview.
