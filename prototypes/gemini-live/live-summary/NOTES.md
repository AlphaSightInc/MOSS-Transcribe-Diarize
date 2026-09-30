# Live (rolling) summary probe — issues #6 and #10 (round 4, helper R4-E)

## Contract

- **Structural question.** Why does the rolling summary read badly during a meeting while the summary after Stop reads
  well, and why does it answer in English for a Chinese transcript?
- **Primitives.** (1) what the pane *shows*, (2) what the model is *asked* (prompt + language rule), (3) what is *sent*
  (the live transcript so far). A fourth, *carried state* (previous summary fed back, LiveTranscribe style), is a
  candidate only if measurement shows refreshes losing points.
- **Invariants.** Five-key contract + `validate_summary` unchanged; one generator for live and final.
- **Falsifier.** If the rolling pane already showed the whole document, or if Auto language already matched the
  transcript, the display / language hypotheses are dead.

## Precommitted rubric (written before the first call)

Production generator (`GeminiSummaryGenerator`, default prompt, `gemini-3.8-flash`, Language = Auto), endpoint retry
semantics (3 attempts, `validate_summary`). Inputs: public transcripts as a live snapshot would hold them (rows ended by
the snapshot; a row being spoken is cut proportionally; speakers shown as live defaults "Speaker n").

| case | source | snapshots (s) |
|---|---|---|
| en_ackman_5m | benchmark_5m/lex_bill_ackman reference | 90, 180, 300 |
| en_ackman_30m | benchmark_30m/lex_bill_ackman reference | 600, 1200, 1800 |
| zh_keyu_jin_5m | my Chinese translation of benchmark_5m/lex_keyu_jin (`zh_keyu_jin.jsonl`) | 90, 180, 300 |
| zh_milei_5m | my Chinese translation of benchmark_5m/lex_javier_milei (`zh_javier_milei.jsonl`) | 90, 210, 300 |

No public Chinese transcript exists in the repo; the two zh files are translations of public English podcast
references (no private audio or meetings).

- **valid**: passes `validate_summary` within 3 attempts.
- **lang**: CJK share of letters over all output strings; zh case matches at ≥ 0.80, en case at ≤ 0.05.
- **recall**: precommitted facts (5–8 per case, regexes in `probe.py`, each counted only once said) found in the *visible*
  pane text: `pane_before` = the `summary` field only (what the rolling pane rendered), `pane_full` = whole document.

Decision rules:
- language rule ships iff any zh snapshot misses **lang** under Auto; after must be 12/12.
- full-document rolling pane ships iff mean recall(pane_full) − recall(pane_before) ≥ 1 fact.
- carry-forward is prototyped iff, after the above, a fact present at snapshot k is lost at k+1 in ≥ 20 % of cases.

## Results (2026-09-30, real Gemini, $0.32 total incl. flash-lite side runs)

Live and final paths are **identical** in prompt, model, temperature (0), JSON mime type, validator and transcript
format (`GeminiSummaryGenerator`): the only differences were what the pane showed and the transcript being shorter.

| run (12 snapshots unless noted) | valid | zh lang match | en lang match | facts in Theme-only pane | facts in whole doc |
|---|---|---|---|---|---|
| before, 3.8-flash, Auto | 12/12 | 6/6 | 6/6 | 28/54 | 50/54 |
| before, 3.8-flash, Auto, early zh (20/35/50 s, 6) | 6/6 | **3/6** | – | – | – |
| after, 3.8-flash, Auto rule | 12/12 | 6/6 | 6/6 | 27/54 | 50/54 |
| after, 3.8-flash, Auto rule, early zh (6) | 6/6 | **6/6** | – | – | – |
| before, 3.5-flash-lite, Auto (+ early zh 6) | 12/12 | **0/6 (+0/6)** | 6/6 | 21/54 | 47/54 |
| after, 3.5-flash-lite, Auto rule | 12/12 | 3/6 | 6/6 | 24/54 | 46/54 |
| flash-lite, stronger wording "…do not translate it into English…" (zh 6 + early 6) | 12/12 | 6/12 | – | – | – |
| flash-lite, Language = "Chinese" (zh 6) | 6/6 | 6/6 | – | – | – |

- **Display (F1).** The rolling pane rendered only the `summary` field ("Theme"): it held 28/54 of the facts the
  document held 50/54 of — the rest (topics, details, speaker background, numbers) were generated and thrown away.
  Rule met (Δ ≈ 1.9 facts per snapshot) → the rolling pane now renders the same document view as the final pane.
- **Language (F2).** Auto sent no language sentence; the English prompt wins while the transcript is short (3.8-flash
  answered English for 3/6 Chinese snapshots ≤ 50 s; flash-lite for 12/12 at every length). Rule met → Auto now sends
  "Write every string value in the transcript's dominant language; do not translate it." 3.8-flash: 12/12 zh, 6/6 en.
  flash-lite stays unreliable under Auto (3/6, 6/12 with a stronger wording); an explicit Language works on it (6/6).
- **Gate (F3, no model call).** `/summary/live` counted words with `str.split()`: the 5-minute Chinese transcripts
  here count 13 and 16 "words" (1,280 / 1,291 characters), so a Chinese live meeting got no rolling summary until its
  rows (or embedded Latin words) reached 40. Each CJK ideograph now counts as a word.
- **Carry-forward (not built).** A fact present at snapshot k was lost at k+1 in 3/27 (before) and 1/26 (after)
  cases — under the 20 % rule. LiveTranscribe's previous-summary feedback earns no place here: every call already sees
  the whole transcript.
- **Quality otherwise.** 100 % first-attempt validity in every run; no output described the meeting as finished. No
  live-specific prompt is needed.

## Cost of the 20 s wait (#10), gemini-3.8-flash, measured usage

Input grows 5.4 tokens per transcript second (English; Chinese 3.1), output (incl. thinking) mean 1,554 tokens,
latency mean 7.4 s. One request starts `wait` seconds after the previous one ends:

| wait | requests / hour | input | output | **$ / meeting-hour** |
|---|---|---|---|---|
| 60 s | 53 | $0.39 | $0.31 | **$0.70** |
| 20 s | 131 | $0.96 | $0.76 | **$1.73** |

(flash-lite at 20 s: 161 requests, $0.65/h.) Extrapolated linearly past the longest measured snapshot (30 min);
Chinese transcripts use ~40 % fewer input tokens per second.

Verdict recorded in `docs/design-gemini-live.md` (Round 4 addition). Run: `probe.py --label <name>`
(`--model`, `--language`, `--at`, `--auto-rule` for wording prototypes); results-*.json beside this file.
