# P3 — tentative fingerprint names on preview words (throwaway prototype)

## Contract before code

**Structural question.** Fresh preview words sit in "Speaker TBD" for ~19 s (median) until the canonical
Gemini window labels them. For voices the meeting has already labelled, can a local WeSpeaker fingerprint of
the newest audio name the speaker within ~2 s, accurately enough to show a greyed tentative name?

**Minimum primitives.** (1) The production `_OnnxWeSpeakerEmbedder` + pinned ONNX
(`prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx`). (2) Per-lane meeting-speaker centroids
known causally at wall time t = the production `ContinuityRegistry` centroids after every canonical window that
has settled by t (settle = window end + recorded API latency, calls serialized). (3) One trailing snippet
[t−W, t] of lane audio. Removing any one loses the voice evidence, the causal identity set, or the fresh audio.

**Invariants.** Causal: no centroid, label or reference information from after wall time t is used for the
guess at t. Constant cost per tick: exactly one snippet embedding per lane per step (never re-embed from
inception — settled evidence). Scoring uses only public corpora (`common/corpus.py`) and cached Gemini
responses (P61 C4 S15/L180 receipts). No Gemini calls.

**Simulation.** Every 0.5 s of audio time t (1.0× pace, wall = audio), if the last 0.5 s has a voiced
WebRTC frame (product detector semantics), embed [t−W, t]; cosine vs each known centroid; show best if
cos ≥ T and (best − second) ≥ M, else abstain. Sweep W ∈ {1.0, 1.5, 2.0, 3.0} s, T ∈ {.40, .46, .50, .55,
.60}, M ∈ {0, .05, .10}; centroid variants: product EMA (`ema`) and plain mean of settled window vectors
(`mean`). Baselines: `sticky` (latest settled speaker of the lane) and `hybrid` (fingerprint if it passes,
else sticky).

**Truth.** Reference speaker at t−0.1 s (steps with no reference speech, overlapping reference speakers or
`<EXCLUDE>` are skipped). Meeting IDs map to the reference speaker they overlap most over the whole clip's
settled rows. Flicker = shown guess ≠ eventual canonical label of the word at t.

**Metrics.** coverage = shown / eligible voiced reference-speech steps; accuracy = correct / shown;
flicker = disagreements with eventual canonical / shown steps that have a canonical word; post-change =
steps within the first 2 s of a turn whose speaker differs from the previous turn; time to first correct
guess after a speaker change; embedding CPU ms (product 1-thread and 4-thread).

**Falsifier / decision rule.** "Showable" if some (W, T, M) reaches accuracy ≥ 90 % with coverage ≥ 60 %
on the pooled long-form + accept6 set, flicker ≤ 10 % of shown steps, and p95 compute ≤ 150 ms. If accuracy
< 85 % at every setting with coverage ≥ 50 %, O3 is NOT showable (escalate).

**Assumptions / unknowns.** 1.0× pace; API latency = recorded per-window latency; mic lane with 2+ local
people and speaker echo unmeasured (no public multi-person mic fixture); E1 has no timed truth (coverage and
flicker only).

**Tool decision.** Reuse P61 C4 cached observations + vector receipts so the canonical lane is exactly the
qualified S15/L180 replay; only the snippet embeddings are new (local CPU). A result that crosses the decision
rule changes whether G2-O3 is implemented as shown UI, hidden, or dropped.

## Run

```
cd <worktree> && PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
    prototypes/gemini-live/tentative/tentative.py
```

Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P65/tentative/`.

## Results (2026-09-29; receipt `evidence/P65/tentative/sweep.json`, log `run.log`; $0, cached S15/L180 windows)

Pooled accept6 + bench5m x3 + Bill30m + long60 (169 reference turns, 11,451 eligible TBD-state voiced 0.5 s steps).
`fp` = fingerprint only (EMA centroid per canonical ID, causal); `sticky` = last canonical speaker.

| Setting | Coverage of TBD time | Accuracy when shown | Flicker vs later canonical | First 2 s after a speaker change | First correct guess p50/p90 |
|---|---:|---:|---:|---:|---:|
| **fp W1.0 T.40** | **.848** | **.987** | **.028** | .775 (cov .653) | **1.5 / 2.0 s** |
| fp W1.5 T.46 | .876 | .983 | .033 | .636 | 1.5 / 2.0 s |
| fp W2.0 T.40 | .910 | .973 | .043 | .517 | 1.5 / 2.5 s |
| sticky | .967 | .755 | .254 | .395 | 0.5 / 19.3 s |

Per clip at W1.0 T.40: long-form coverage .78-.89 at accuracy .95-.99; 60 s clips coverage .37-.54 (voices not yet known);
RTFL 4-way crosstalk abstains (coverage .19, accuracy .89); Adam Frank voice-over split flicker .10; E1 (no timed truth)
coverage .76, flicker .014. CPU per snippet embedding: 4 threads W1.0 median 49.8 / p95 50.6 ms (1 thread 159 ms).

**Verdict: SHOWABLE** by the decision rule (accuracy >= .90 with coverage >= .60, flicker <= .10, p95 <= 150 ms at 4 threads).
Recommended: W1.0 s snippet, T .40, EMA centroids from canonical >= 2 s spans, 4 ONNX threads, every 0.5 s per voiced lane;
show greyed tentative name; abstain below T; unknown voices stay "Speaker TBD" until the canonical lane births them.
Weak spots: first ~2 s of a new turn (.78), crosstalk (abstains), unmeasured on conference-compressed audio, similar voices,
mic-lane echo and several local people (no public corpus).

## R2 product-path paced HTTP check (WP4)

**Structural question.** Do display-only guesses survive the actual Account HTTP snapshot path, with the system and microphone lanes kept distinct, and cover at least 70% of visible Speaker-TBD reference-speech time at at least 95% accuracy on public long60?

**Minimum primitives.** The existing 1.0x long60 replay and public reference, the first observed provisional half-second audio bucket with its source lane and tentative canonical ID, the pre-Stop settled canonical-to-reference mapping, and the product `engine_diagnostics`. The capture never uses future labels to make a guess; the reference mapping is retrospective scoring only.

**Invariants.** Only `common/corpus.py` long60 audio is sent; no private/operator audio. Port 18740 and the WP4 worktree only. No retry after an accuracy failure. `provisional.segments` and `tentative_spans` stay out of the durable transcript and events. The original transcript string is unchanged. Cumulative embed wall time / paced audio duration is reported as a wall-share proxy, not a per-core CPU percentage.

**Assumptions / unknowns.** A growing preview segment may appear repeatedly with a longer end, so the scorer assigns each 0.5 s audio bucket the earliest visible segment covering its midpoint. The denominator is first-visible Speaker-TBD buckets with one unambiguous reference speaker, not all elapsed audio or silent intervals. Buckets with overlapping reference speakers are excluded and counted separately. This population may differ from the prototype's half-second voiced-tick denominator and is reported separately.

**Falsifier.** Coverage below .70 or correct half-second buckets below .95 of shown buckets fails the WP4 target on this denominator; absent snapshot rows or unsupported reference mapping makes the result `UNMEASURED`. A lane collision in the snapshot violates the interface regardless of aggregate accuracy.

**Tool decision.** `http_long60.py` reuses the existing `harness/run_long60.py` replay and only captures the first-seen lane-bearing provisional rows at its existing 250 ms poll. `score_http.py` assigns earliest visible 0.5 s audio buckets from those rows and maps canonical IDs against the existing pre-Stop settled snapshot. These tools answer whether to keep, revise, or park the live guess path; they make no Gemini calls of their own.

### 2026-09-29 paced HTTP long60 attempt 1 (pre-WP1 F13 revision)

Product code `9d905e20` accepted all 2,586 s at 1.0× on public long60. The harness timed out after 120 s with one canonical item pending before Stop; the session aborted. Actual settled accuracy is **UNMEASURED**. The first-visible preview trace contains 4,104 lane-bearing rows, with two guessed canonical IDs. On 5,160 observed reference-speech half-second buckets, 4,342 showed guesses (84.15% coverage). Even an oracle assignment of the two guessed IDs to the five public reference speakers would get at most 3,891/4,342 = **89.61%** right. This falsifies the ≥95% accuracy gate for this run independent of retrospective mapping. Embedding p95 was 221.3 ms, one busy tick, and cumulative embed wall time was 1,044.0 s (40.4% of audio duration, a wall-share proxy). Cost was $0.980261. Content-free receipt: `evidence/P66/wp4/attempt1-measurement.json`; failed-run scratch is `/tmp/moss-r2-wp4-long60-run-20260929/`. The production-transport result conflicts with the offline SHOWABLE prototype, so product acceptance remains failed pending a bounded integrated retry or a design correction.

### New-speaker centroid path: pre-fix contract

**Structural question.** When a new canonical speaker first appears in a settled rolling row but the rolling update carries no embedding observation, does the display labeler gain that speaker within the same window?

**Minimum primitives.** The settled lane-specific row identifies a canonical speaker and >=2 s continuous speech; the existing full lane tape supplies exactly that audio; the production voiceprint encoder supplies one vector; the labeler stores an EMA centroid. Removing any of these loses either identity, source lane, speech length, or acoustic evidence.

**Invariants.** No centroid from provisional text or future audio. A new speaker in a rolling or relabel update becomes guessable only after a settled >=2 s span and successful embedding. Lane centroids never cross. A speaker without 2 s remains unknown.

**Assumptions and unknowns.** The failed long60 trace lacks intermediate canonical snapshots and centroid diagnostics, so this gap is source-visible but its contribution to the 89.61% oracle bound is unmeasured. The public rolling transcript ended at 750 s, a separate upstream limitation.

**Falsifier and tool decision.** A one-command fake-encoder runtime probe creates speaker 0001 in the first window and speaker 0002 in the next with no second rolling observation; it prints all observed and labeler centroid IDs. If 0002 already appears, this suspected WP4 bug is false and no code change is warranted. The probe uses the production runtime publication path and no provider call.

**Prototype verdict (2026-09-29).** Before the patch, the one-command `new_speaker_probe.py` produced settled IDs `[0001,0002]`, voice observations `[0001,0002]`, but tentative centroid IDs `[0001]`. After routing each newly embedded settled voiceprint into the labeler, both IDs were present in the same rolling window; 49 focused tests passed, including a worker encoder exception that abstains without propagating into audio ingress. The production fix is limited to this missed observation handoff.

**Conditional full-trace result.** `offline_trace_probe.py` used the failed HTTP run’s 4,104 first-visible preview rows, public long60 audio, cached production WeSpeaker W1.0 vectors, and P61 causal ContinuityRegistry output (five IDs born at ~18/1870/2125/2424 s). It scored 4,496 shown / 5,160 eligible half-second buckets = **87.13% coverage**, and 4,450 / 4,496 = **98.98% accuracy**; 13 eligible buckets lacked cached vectors. Receipt: `evidence/P66/wp4/offline-trace-conditional.json`. This clears the numeric offline gate *conditional on the live system actually publishing all five canonical speakers*. Attempt 1 published only two and ended settled rows at 750 s, so it remains a live FAIL; no paid retry until the upstream stall is fixed.

**Retry client preparation.** After merging integration `e3df8e85`, `http_long60.py` binds the merged WP6 `SettingsReplayService`, `TimedSurfaceCapture`, and `TentativeProbe` in this WP4 worktree. It enforces balanced/clean-up OFF, retains the first-seen lane-bearing trace, and the merged harness writes `tentative.json` after terminal capture. `--help` completed as a zero-send import check. The lead authorized the second paid run on this integrated code as the S1 recurrence check.

**S1 recurrence witness.** The final one-arm wrapper adds one content-free snapshot at each existing 300 s progress point. `frontier-progress.jsonl` records accepted/committed seconds, last labelled row end per lane, rolling publication count, text revision version, and canonical speaker count. This is a public-snapshot proxy for lane progress, not internal `_lane_frontiers`; its purpose is to reveal another 750 s label stall while the run proceeds. It does not add a model call.

### 2026-09-29 S1-fixed paced HTTP long60 verdict

**Question and falsifier.** With the production two-lane HTTP stack, does the public long60 replay publish labels through the full 2,586 s and meet ≥70% first-visible Speaker-TBD coverage at ≥95% accuracy? A full-frontier run below 95% falsifies product acceptance even if a conditional offline prototype passed.

**Fixed revision and tool.** WP4 `8841f33a` merged S1-fixed integration `1a55b4d1`; `http_long60.py` sent the public source once at 1.0× with balanced schedule and clean-up OFF. The service finished Stop with all 41,376,000 samples accepted/accounted, pending=0, 268 rows. The S1 frontier passed its old 750 s limit: at 900 s accepted, labels ended at 884.2/885 s committed; at 2,400 s, 2,384.8/2,385 s. Five canonical IDs appeared by 2,400 s, six by Stop. No `worker_*` error occurred; `errors_by_code` was `go_away:4`, `503:1`. Cost was $0.980563.

**Measured WP4 gate: FAIL.** On the earliest visible row covering each unambiguous reference-speech half-second bucket, 4,972/5,160 buckets showed a guess (**96.36% coverage**), and 4,569/4,972 were right (**91.89% accuracy**). The mapping from guessed ID to reference speaker chooses the best label separately for every ID, so 91.89% is also the oracle upper bound for this frozen first-visible trace. The WP6 time-aligned tentative metric was 86.37% coverage and 83.47% accuracy; different denominator/timing, same failure. Embed p95 213.03 ms; zero busy skips; cumulative embedding wall 1,028.43 s / 2,586 audio s = 39.77% wall-share proxy, not per-core CPU. The settled transcript had 97.55% text coverage but 29.63% diarization error and six IDs for five reference speakers. Receipts: `evidence/P66/wp4/long60-fixed/{summary.json,tentative.json,tentative-score.json,engine-diagnostics.json,frontier-progress.jsonl,tentative-first-seen.jsonl}`; full scratch at `/tmp/moss-r2-wp4-long60c-run-20260929/`.

**Failure structure.** Of 403 wrong shown buckets, ID `speaker-0002` contributes 315: 165 Bill, 115 Javier, 35 Keyu; it is Lex-majority on 985 correct buckets. Settled rows already give Javier's 89.7 s of covered speech to ID 0002, which also covers 484.3 s of Lex. Bill splits across 0001/0003; Lex across 0002/0005. Thus the five-clean-ID conditional offline result (98.98%) did not predict this six-ID production trace. This does not prove the best fix is in the settled registry or the tentative threshold. A threshold change could abstain on some wrong guesses but must be measured on the same production vectors, and cannot create a distinct Javier canonical ID under the current contract. No further provider send is authorized; product accuracy remains blocked.

### Max-preset paced HTTP attempt (2026-09-29): interrupted, qualification UNMEASURED

Lead authorized one 1.0× public long60 send on `ff5b92ef` with `speaker_window=max` (15 s stride / 3 min context) and clean-up OFF to test whether a stronger canonical lane would improve WP4 guesses. The existing one-arm client was widened only to pass Max/OFF. The Codex daemon restarted during replay and its client process disappeared; the server stayed up, but the session became terminal `failed` before Stop. This is an infrastructure-interrupted attempt, not evidence that Max passed or failed final DER or guess accuracy. At its terminal partial snapshot, 2,050/2,586 s were accepted/accounted, system labels reached 2,049.8 s, three canonical IDs existed, 137 rolling publications occurred, cost was $1.347357, and `errors_by_code` contained `go_away:3` with no worker error. The last 1,800 s paced checkpoint had labels at 1,784.8/1,785 s committed. Full settled/final DER and ≥70%/≥95% WP4 gate are **UNMEASURED**. Content-free receipt: `evidence/P66/wp4/long60-max-interrupted/`. A new paced send would be a distinct paid attempt and awaits lead authorization and a budget increase.

### Max retry cancelled by lead/user decision (2026-09-29)

A fresh detached 1.0× Max/OFF long60 retry began after the prior infrastructure interruption. The lead cancelled it when the user selected Balanced (15 s / 90 s) as the final default and clean-up ON in the background. The client was stopped after 416/2,586 s accepted/accounted; the session became terminal without Stop. Cost was $0.228773, labels reached 416.0 s, 28 rolling publications and two IDs were present, and `errors_by_code` was empty. This is **not** a Max DER or WP4 accuracy qualification. Receipt: `evidence/P66/wp4/long60-max-cancelled/`. The remaining WP4 95% guess gate is to be measured on the final integration head at Balanced. The only full WP4 Balanced live draw here showed 96.36% first-visible coverage and 91.89% accuracy (WP6 metric 86.37%/83.47%) with poor settled canonical identity; do not report it as a passing gate.
