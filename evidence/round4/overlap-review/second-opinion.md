# R4-6 overlap second opinion

**Verdict: CONFIRMED.** All 13 acceptance-arm edits agree with 3.4 under the existing clean-reference scoring convention: **a=3, b=0, c=0, d=10**. The audio supports every class-(d) correction; the three spoken filler/repetition tokens remain class-(a) scoring additions by policy, not acoustic hallucinations.

## Independent source custody

- **W1 audio:** corpus `interview_bill_ackman_60s/audio.wav`, 60.000 s; reference row falsely spans `[0,29]` while containing pre-clip `And the key is` and post-cut `the book`.
- **W2 offline 29 s witness:** exact 464,000-sample clip, local snapshot `e8681d...`, greedy MPS, network disabled: starts `[0.54] To figure...`; hears `you know`, `market is`, `You're`, `divine`, `to to`; ends `[28.02-28.98] ...message of.`
- **W3 offline 60 s witness:** same local snapshot/network-disabled: `[28.02-29.25] And that's kind of the message of the book.` Zero remote calls.
- **W4 code:** `verify_demo_lanes.py:60-75` couples the first reference row's `[0,29]` interval/text to the demo PCM. `run.py:29-30,448-454` invokes the external ladder; its path uses `lane_pcm(...,24,...)` and `n=24*sr//fs` (`ir_lane_ladder.py:18-20`).
- **W5 correction replay:** production tokenizer/alignment against `demo_overlap_29s` gives **3/102 = 0S/0D/3I**, exactly `you`, `know`, second `to`.

## Per-edit adjudication

| # | Edit | Decision on 3.4 class/cause | Evidence line |
|---:|---|---|---|
| 1 | `and` -> empty | **AGREE d**, leading reference overhang | W1-W2: 29 s audio begins at `To`, not `And`. |
| 2 | `the` -> empty | **AGREE d**, leading reference overhang | W1-W2: same false pre-clip phrase. |
| 3 | `key` -> empty | **AGREE d**, leading reference overhang | W1-W2: same false pre-clip phrase. |
| 4 | `is` -> empty | **AGREE d**, leading reference overhang | W1-W2: same false pre-clip phrase. |
| 5 | empty -> `you` | **AGREE a**, raw clean-reference addition | W2 hears filler `you know`; corpus reference omits it; raw has it (`raw-system-0-29.json:21`). |
| 6 | empty -> `know` | **AGREE a**, raw clean-reference addition | Same W2/reference/raw evidence as #5. |
| 7 | empty -> `market` | **AGREE d**, reference tokenization | W2 says `stock market is`; reference says `stock market's`. |
| 8 | `market's` -> `is` | **AGREE d**, reference lexical/tokenization mismatch | W2 and W3 both say `market is`. |
| 9 | empty -> `you're` | **AGREE d**, reference tokenization | W2/W3 say separate sentence `You're much more accurate`; reference collapses it after `machine`. |
| 10 | `define` -> `divine` | **AGREE d**, reference lexical error | W2/W3 both say `divine`; corpus says `define`. |
| 11 | empty -> second `to` | **AGREE a**, raw clean-reference repetition | W2/W3 hear `here to to help`; clean reference retains one `to`; raw has two. |
| 12 | `the` -> empty | **AGREE d**, cut before reference tail | W2 ends `of` at 28.98; W3 completes `the book` only through 29.25. |
| 13 | `book` -> empty | **AGREE d**, cut before reference tail | Same W2-W3 boundary evidence as #12. |

## Required answers

1. **Yes.** Exact 29.0 s stops after `of`; full audio places the segment containing `the book` through **29.25 s**. The corpus `[0,29]` row overclaims its tail.
2. **Reference errors.** Audio says **`the stock market is a weighing machine. You're much more accurate`** and **`divine`**, not `market's ... much` or `define`.
3. **Yes.** Ladder evidence says 24,000 ms, and the actual invoked ladder code independently fixes both lane PCM and frame count to **24 s** while the reused corpus reference ends at 29 s.
4. **Yes, mechanically.** Applying `demo_overlap_29s` changes only the ten class-(d) alignments; exact replay leaves the three class-(a) additions `you`, `know`, second `to` visible (3/102). This is a scoring-policy statement: the audio does contain those disfluencies.

No product/decoder change supported. Correct only qualification reference/cut construction; retain the three residual additions and the 24 s ladder-specific reference.
