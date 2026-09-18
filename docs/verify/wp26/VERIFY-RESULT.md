# WP26 verification result — 2026-09-18

**PASS: all executable verification gates.** Tested clean branch
`mvpfix/wp26-unassigned-terminal` at `dfb9b261092f2f62dbe419b48247b695bcf4b2db`,
base `625dbaa97b55fb5be66e06db9bfe4d8c985fd935`, from the specified WP26 worktree.
Python import resolved to that worktree. No production/test/script changes in this
verification pass; only this result and `evidence/mvpfix/wp26/fresh/` are added.

## F1 — execution and exact results

Read VERIFY.md, COMMON.md, WP26 brief, evidence/prototype notes, prototype skill,
and execution-plan sections 1–2. Inspected the requested three-file base diff:
only the unmapped-segment fallback, its reason/comments, two parametrized
regression cases, and design documentation changed there. No policy drift found.

Ran literally, once, from the worktree:

```bash
bash prototypes/streaming-diarization/wp26/verify.sh
```

Exit **0**; no failed verification attempt or rerun.

- Entire Python suite: **1912 passed, 2 skipped, 21 warnings, 37 subtests passed**
  in **149.49 s**. Skips: `test_live_identity_real_corpus.py:60` (operator-owned
  identity corpus absent); `test_live_speaker_accuracy.py:44` (real F-cert corpus absent).
- Full frontend: **249/249 tests, 28/28 files**, **2.62 s**. Three Node warnings
  about `--localstorage-file` without a valid path; no failures.
- Typecheck/build: **PASS**; build **34 modules / 74 ms**. Generated assets unchanged.
- Production replay, saved-store census, audit, whitespace and asset checks: **PASS**.
- Port **18126**: no listener. Verification command finished; no tunnel/server started.
- Decoder requests **0/60** under this user's cap (older brief says 400; not used).

Logs and measurements: `evidence/mvpfix/wp26/fresh/`, including `shell.txt`,
`python-full.txt`, `frontend-full.txt`, `typecheck.txt`, `build.txt`,
`replay-state.jsonl`, `prototype.json`, `production-replay.json`, `survey.json`,
`audit.json`, `listeners.txt`, `reference-check.json`, and `p5-source-check.json`.
The literal script normalizes trailing whitespace in text logs.

## F2 — cause, fallback, and reference-checked recovery

Three terminal local labels competed for two system-lane identities; one label
lost the one-to-one overlap mapping. The adapter saw labelled causal overlap and
skipped its acoustic fallback even though the resulting speaker was absent.
`moss_transcribe_diarize/app/live_lane_decode.py:286` now probes when uncovered
**or `speaker is None`**; lines 296–303 set the reason and crop the segment's PCM.
The existing same-lane preparer/thresholds decide identity; unsuccessful probes
remain unattributed. No time-nearest guess was added.

Prototype replay **PASS**: **69** reconstructed accepted causal preparations,
**24.662728 s** including instrumentation. Existing score/margin **0.35/0.1**.

| Turn | Emitted words | Audio seconds | Lex score | Ackman score | Recovered identity |
|---|---:|---:|---:|---:|---|
| 149.61–153.75 s | 14 | 4.14 | 0.9404659566 | 0 | speaker-0004 |
| 160.68–161.40 s | 2 | 0.72 | 0.4899272409 | 0 | speaker-0004 |

Independently read the saved words against public corpus
`interview_bill_ackman_60s/reference.jsonl`, rows **2/4**, both **Lex Fridman**.
These third-loop turns repeat the text of earlier assigned system rows **9/12**
exactly, **120 s** later, binding Lex to `speaker-0004`. The longer emitted turn
starts “And” where the reference starts “In”; its other normalized words match.
The short turn's normalized words match exactly. Attribution recovery preserves
that existing transcription difference. No audio relisten or word-level timing
oracle claimed. Detailed annotation: `fresh/reference-check.json`.

Production fallback: **2/2 segments, 16 words, 4.86 s** recovered; **0** remaining
unassigned system segments in this replay. **54/54** existing assignments unchanged;
**56/56** rows preserve words, times and lanes. Crops read **155520 bytes**;
probe times **0.633660 + 0.117243 = 0.750903 s**. This is not live Stop latency.
The full suite includes both new conflict-recovery/abstention regression cases,
which exercise the real mapper with three labels and two lane-owned identities,
including a stronger ineligible microphone candidate.

## F3 — saved-store census: 49 completed sessions

Read all **18 databases** (17 WP12, 1 WP17) immutable/read-only after checking for
nonempty WAL files. Counts include recognition sessions. This is the **pre-fix**
saved population; these stores were not repaired.

| Population | Affected/total sessions | Unassigned/total segments | Unassigned/total words | Unassigned/total segment seconds |
|---|---:|---:|---:|---:|
| WP12 accepted overlap | 1/3 | 2/127 | 16/1546 | 4.86/493.27 |
| WP17 accepted overlap | 0/27 | 0/212 | 0/2370 | 0/714.71 |
| WP12 discarded historical controls | 2/19 | 64/476 | 674/5362 | 190.69/1576.01 |

Historical controls do not estimate current defect prevalence. Separate retained
surface counts overlap these saved sessions and are not added. WP12 saved rows
lack lane metadata; none inferred. Durations sum segment intervals, not meeting
time. Repeated public clips do not establish arbitrary-meeting frequency.

## F4 — P5: simultaneous speech inside one lane

P5 remains **open**. Alternating voices on one lane require attribution; two
simultaneous voices arrive already mixed. This repair labels emitted words but
cannot recover omitted speech, and current within-lane normalization allows one
owner per interval.

All **3** retained P5 rows and witness definitions match their original source
(`fresh/p5-source-check.json`). Historical mono-mixture decoder measurements:

| Mixture | Emitted words | First-source unique tokens | Second-source unique tokens |
|---|---:|---:|---:|
| Parity | 184 | 35/54 | 39/41 |
| Second source −10 dB | 134 | 45/54 | 1/41 |
| First source −10 dB | 76 | 0/54 | 36/41 |

These are token-retention witnesses, **not word error rate or speaker accuracy**.
No same-tab conferencing capture or new live test. Recommendation remains to
exclude reliable same-lane simultaneous-speech recovery from MVP acceptance,
while retaining alternating-speaker attribution; this verification does not decide P5.

## F5 — provenance, limits, and deviations

- This verifier received a fresh task context without the implementation dialogue.
  An actual CLI `/new` event and MOSS:3.1 pane identity are **not independently
  attested**; no claim that starting a shell constitutes `/new`. Executable checks
  pass; literal context-reset provenance remains unverified.
- Replay uses the actual production encoder/preparer/fallback, reconstructed album
  vectors, retained accepted intervals and original repeated public PCM. Original
  runtime vectors, raw terminal labels and pre-terminal surface were not retained.
  The captured post-mapping proposal is replayed; existing assigned rows supply
  part of reconstructed coverage. This is not native-runtime or live Stop replay.
- New live Stop latency and arbitrary multi-voice accuracy remain unmeasured;
  two operator-corpus tests remain skipped. The existing prototype's scripted state
  output replaces an interactive TUI and is absorbed into the measurement bench.
- Added reference-word and historical P5 source checks to substantiate the requested
  report. An exploratory read first named nonexistent WP12 NOTES/prototype paths;
  `rg` returned exit 2, then actual paths were discovered. No writes or inference
  from that failed lookup; literal verification itself passed on its first run.
- No packages installed, new decoder requests, peer messages, shared-service changes,
  other-worktree content writes, push, merge, deployment, or GitHub actions.
