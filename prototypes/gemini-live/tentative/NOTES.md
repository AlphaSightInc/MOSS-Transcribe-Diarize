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

**Minimum primitives.** The existing 1.0x long60 replay and public reference, the first observed provisional segment with its source lane and tentative canonical ID, the pre-Stop settled canonical-to-reference mapping, and the product `engine_diagnostics`. The capture never uses future labels to make a guess; the reference mapping is retrospective scoring only.

**Invariants.** Only `common/corpus.py` long60 audio is sent; no private/operator audio. Port 18740 and the WP4 worktree only. No retry after an accuracy failure. `provisional.segments` and `tentative_spans` stay out of the durable transcript and events. The original transcript string is unchanged. Cumulative embed wall time / paced audio duration is reported as a wall-share proxy, not a per-core CPU percentage.

**Assumptions / unknowns.** First observed `(start_sample,end_sample,lane)` represents a preview word once; revisions at the same interval count at first visibility. The denominator is reference-speech overlap of first-seen provisional system segments, not all elapsed audio or silent Speaker-TBD intervals. Overlapping reference speakers contribute their overlapped speech time. This population may differ from the prototype's half-second voiced-tick denominator and is reported separately.

**Falsifier.** Coverage below .70 or correct time below .95 of shown time fails the WP4 target on this denominator; absent snapshot rows or unsupported reference mapping makes the result `UNMEASURED`. A lane collision in the snapshot violates the interface regardless of aggregate accuracy.

**Tool decision.** `http_long60.py` reuses the existing `harness/run_long60.py` replay and only captures the first-seen lane-bearing provisional rows at its existing 250 ms poll. `score_http.py` applies duration overlap to those rows and the existing pre-Stop settled snapshot. These tools answer whether to keep, revise, or park the live guess path; they make no Gemini calls of their own.
