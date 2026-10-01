# R4-C follow-up: foreign-script words in the microphone preview (P69 finding F2)

In the P69 UI stress test (run c, a Mandarin meeting), the grey microphone preview showed
`さんね。` (Japanese kana) and `क्या?` (Hindi). Neither reached the saved text. Separately,
the saved system lane held one Cyrillic token, `кве`, in place of 馈.

## One command (from the worktree root)

```sh
PY=../MOSS-Transcribe-Diarize-wt-r4-c.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/preview-script/build.py        # fixtures (TTS + public audio)
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/preview-script/w3.py out.json mic.wav   # one paced W3 stream ($)
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/preview-script/sim.py           # rule arms, $0
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/preview-script/sim.py --product # the shipped composer, $0
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/preview-script/p69c.py          # P69 UI-observed rows, $0
python3 prototypes/gemini-live/preview-script/scan_saved.py                          # saved-text evidence, $0
```

W3 is the instant-word model (`gemini-3.5-transcribe-live`). `sim.py` replays recorded W3
updates through the same steps the product runs: the preview bookkeeping, the echo strip,
the script rule, and `_trim_committed_preview`.

## Contract

- **Structural question.** A short preview word is in a script the meeting has not used. Is
  it speech in a new language, or something W3 invented from noise or echo residue?
- **Minimum primitives.**
  - The script of each letter. Hiragana and Katakana count as one script.
  - A weight per stretch of one script: 3 per Han, kana or Hangul character; 5 per word of
    any other script.
  - **Sustained** means a weight of at least 20: four words or seven CJK characters.
  - The meeting's scripts: a script counts once a sustained amount of it has been committed
    on either lane in total, or has stood in one preview row of either lane.
- **The rule** (`gemini_lane_engine._without_foreign_script`, mic preview rows only).
  - A row that itself holds sustained speech in any script is left whole.
  - Any other row loses its stretches in scripts the meeting has not used.
  - A row with nothing left is not shown.
- **Invariants.**
  - No language or script list is used.
  - Committed and saved text is never touched.
  - A code-switched term inside a real sentence is never removed.
  - System rows are never touched.
- **Falsifier.** Genuine words in an established script are hidden, or a sentence in a new
  language is delayed by more than about 1 s.

## Inputs

All fixtures are public audio or local text-to-speech (`build.py`). The Mandarin lanes use
two genuinely different voices: Tingting for the far end and Meijia for the local person.

| Stream | What it is |
|---|---|
| zh2-sp | Mandarin meeting on speakers. Local Meijia turns with English terms, plus room-noise events and the echo-cancellation residue of the Tingting far end. |
| en2zh | English meeting (Acquired far end, Lex local). At 110 s the local person switches to Mandarin: two short replies, then sentences from 140 s. |
| zh2en | Pure-Mandarin meeting with no Latin before the switch. At 110 s the local person switches to English: `Okay.`, `Right, sounds good.`, then a Lex turn from 140 s. |
| zh2-system | The Tingting far end, used as the system preview for the zh2 cases. |
| zh2-echo | The zh2-sp local speech with the far end as raw −25 dB echo (used by `mic-preview-echo`). |
| P69 runs a, b, c | Mic preview rows as the UI showed them (`states.jsonl`); nothing new was sent. |

In the replay, committed text is the reference text of the turns that ended before the 15 s
rolling frontier, published 4 s late.

## Results

**Rule arms on the three mic streams (bar = 20).** "Word-polls" count one word shown at one
W3 update.

| Arm | zh2-sp invented foreign-script word-polls | zh2-sp genuine word-polls | en2zh genuine | zh2en genuine |
|---|---:|---:|---:|---:|
| None (before) | 243 | 23,506 | 19,199 | 35,332 |
| Every stretch in an unused script | 0 | 23,457 (drops `API`, `latency` before Latin is established) | 19,179 | 35,236 |
| Only rows made wholly of unused scripts | 12 (mixed rows keep the foreign word) | 23,506 | 19,179 | 35,236 |
| **Short rows only (shipped; `--product` gives the same numbers)** | **0** | **23,506** | 19,179 (−0.1%) | 35,236 (−0.3%) |

**Sensitivity to the bar.** At 15, a three-word Hindi row (`क्या तो जी`) establishes itself
and 68 word-polls remain. Bars of 20, 25 and 30 all remove everything. The longest invented
stretch seen weighed 15 here; earlier R4-C data had one of 18 (`ノ ミ シャ ソ ヤ`). So the
margin to 20 is thin.

**Cost of a genuine language switch (shipped rule).**

| First words in the new language | Effect |
|---|---|
| `好的。` in the English meeting (110 s) | Not shown in grey; appears with its commit about 12.9 s later |
| `对，没问题。` (125 s) | Same, about 12.7 s |
| First Mandarin sentence (140 s) | Shown 0.6 s later, once seven characters have arrived |
| `Okay.` in the pure-Mandarin meeting (110 s) | About 12.7 s (with its commit) |
| `Right, sounds good.` (125 s; three words, one under the bar) | About 12.3 s (with its commit) |
| First English turn (140 s) | No delay |

After the first sustained stretch or commit, the script belongs to the meeting and nothing
more is held.

**P69 UI-observed rows (`p69c.py`).**

- Run c: both foreign words are removed (`さんね。` → hidden; `Wait. क्या? 好的。` →
  `Wait. 好的。`). One other row changes: a one-poll first interim, `What`, is hidden.
- Runs a and b (English): 25 and 1,123 Latin runs, all unchanged.

## Decision on the saved `кве` token: not implemented

The proposed rule was: delete a saved token that stands alone in a script appearing nowhere
else in the meeting, inside another script's sentence.

**Evidence** (`scan_saved.py`): 1,617 evidence JSON files with transcript text, 12.8 M
letters. The shape occurs in two meetings:

| Token | Where | What it is |
|---|---|---|
| `кве` | P69 run c, saved system lane, `反 кве 说` | A decode error for 馈 |
| `嗯。` | Round-6 MOSS outputs, inside English text | A filler sound, written by the old engine |

**Why I did not ship it.**

- Deleting `кве` leaves `反说`. The character 馈 is still missing, so the saved text is
  still wrong.
- There is one real error in 12.8 M letters. That is too little to call the rule safe.
- The evidence has no meetings in which a genuine one-off foreign-script word occurs (a
  Japanese or Korean name in a Chinese meeting, for example). That is exactly the case the
  rule would delete from the permanent record. So its safety is unmeasured where it matters.
- The preview rule above is different: a wrong hold there costs seconds and loses nothing.

## Earlier Mandarin numbers (the one-voice fixture flaw)

`say -v "Flo/Reed/Eddy (Chinese (China mainland))"` silently speaks as Tingting, so my v1
Mandarin lanes (`mic-hallucination/build.py`) had one voice on both lanes.

- **Issue #3 and D2 tables:** unaffected. The v1 Mandarin lanes were excluded from those
  sweeps for this reason. The tables use the English v1 lanes and the v2 lanes, which were
  built with Tingting and Meijia.
- **Preview-echo table (d88be99d):** the Mandarin row changes on the corrected two-voice
  fixture. See `mic-preview-echo/NOTES.md`.
- `mic-hallucination/build.py` now uses Tingting for the far end and Meijia for the local
  person.

## Spend

Five paced W3 streams (zh2-sp, en2zh, zh2en, zh2-system, zh2-echo): **$0.1158** at the
list-price estimate. Live usage metadata is absent. Ledger lane `r4c-preview-script`.
Everything else was $0.
