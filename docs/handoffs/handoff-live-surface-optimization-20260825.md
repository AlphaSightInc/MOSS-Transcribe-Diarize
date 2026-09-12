# Handoff — optimize pre-Stop live quality and certify all transcript surfaces

Written 2026-08-25 EDT. This supersedes the execution state in
`docs/handoffs/handoff-8YIE4C.md`; retain that document as campaign history.

## Mission

Continue optimizing MOSS, with priority on **what the user reads before pressing Stop**.
First certify three MOSS surfaces on identical real audio and golden references:

1. **pre-Stop live** — the last published rolling transcript before the Stop request;
2. **post-Stop live** — the terminal transcript after `finalization_status=final`;
3. **file mode** — the same PCM bytes through the file endpoint.

Then compare, honestly and on the same audio/reference/evaluator, with the runnable surfaces
of these authoritative m4mbp projects:

- `/Users/ga0/Desktop/AI_Projects/LiveTranscribe`
- `/Users/ga0/Desktop/AI_Projects/Github_Projects/ProjectClerk`

Do not call an offline import a live measurement. Report an unavailable peer live surface as
**unmeasured** unless an attended AV/TCC run is actually performed.

## F1 — current campaign is complete; do not rerun it

- Branch: `ralph/live-convergence-0824`
- HEAD: `7608c91ce36441d9075fbba41e18c5fae8f464ac`
- Ralph run: `20260825-042645-70858`, complete at iteration 35, exit 0
- Worktree was clean before this handoff; this new handoff file is the only expected
  untracked path.
- Nothing was pushed.
- Claude's completed monitor is tmux `MOSS:1.1`; the finished Ralph terminal is `MOSS:2.1`.

Claude's campaign claim was independently checked against Git and the committed evidence:

- `evidence/live-convergence-0824/CAMPAIGN_REPORT.md`
- `evidence/live-convergence-0824/post-implementation-tests/NOTES.md`
- `evidence/live-convergence-0824/benchmark/REPORT.md`
- `evidence/live-convergence-0824/M4-e4-exit-2/gates.json`

The campaign added rolling re-decode during capture and terminal file-equivalent re-decode
after Stop. File mode stayed byte-identical on 5/5 golden cases.

## F2 — measured MOSS baseline to preserve

### Latest measured pre-Stop baseline: deployed 10-second window / 10-second stride

These numbers were measured at M2. Later production changes add only the Stop-time terminal
path, but the final campaign build has not freshly captured a pre-Stop snapshot; A2 must confirm
them rather than assuming they remained identical.

Three fully referenced 60-second cases, macro mean:

| metric | pre-campaign live | current pre-Stop rolling | paired file |
|---|---:|---:|---:|
| WER, lower is better | .199870 | **.131357** | .103946 |
| DER, lower is better | .176389 | **.111278** | .102111 |
| speaker accuracy, higher is better | .823611 | **.888722** | .897889 |
| content recall, higher is better | .913490 | **.943916** | not repeated here |

Other current pre-Stop evidence:

- 5-minute Keyu WER `.082079`, DER `.088600`.
- correction-after-provisional p95 `8.756675 s` on the trio; `10.39 s` on Keyu 5m.
- combined base + rolling GPU RTF `.133–.157`; queue depth `<=1`; zero refusals.
- Source: `evidence/live-convergence-0824/M2-e2-exit/NOTES.md`.

This is now the main quality gap: trio WER is `.027411` worse than file and DER is `.009167`
worse than file before Stop.

### Post-Stop live and file

The terminal finalizer uses the same 150-second window / 120-second stride runner as file mode.
On the golden cases:

- 60-second trio: terminal live equals file to six decimals: WER `.103946`, DER `.102111`,
  speaker accuracy `.897889`.
- Keyu 5m: live/file WER `.050616`, DER `.057933`, speaker accuracy `.942067`.
- Adam 3m: live/file WER both `.126177`; terminal DER `.066222` vs file `.053222` because
  terminal seam ownership changes segment extent. Do not state universal DER identity.
- stop-to-final: about `2.59 s` warm on 60-second meetings; maximum `10.80 s` on the 5-minute
  case. Terminal decode RTF mean `.032575`, max `.037027`.

Post-campaign stress already performed:

- file arms byte-identical 5/5;
- three back-to-back Bill live sessions succeeded and published hash-identical surfaces;
- two Javier replays from m4mbp over Tailnet equaled local live/file quality;
- the default remote pacing bound failed once because 10 synchronous HTTPS posts/sec accrued
  lag; `--max-pacing-lag 10` succeeded. Batch frames or reuse the connection if remote capture
  becomes a product path.

## F3 — cross-project benchmark already completed, with one important limitation

Five fully referenced golden cases were copied byte-identically to m4mbp and scored with this
repo's evaluator. Macro means:

| system/surface | mode actually run | mean WER | mean DER | mean speaker accuracy |
|---|---|---:|---:|---:|
| MOSS terminal | paced live, then terminal finalization | .0977 | **.0861** | **.9139** |
| LiveTranscribe | file proxy | .1200 | .1394 | .8607 |
| ProjectClerk | file replica | **.0862** | .1764 | .8237 |

MOSS won DER on 4/5 cases. ProjectClerk's mean WER edge came from Bill Ackman, where Whisper
also beats MOSS file mode; that is a model-quality ceiling, not a live defect.

Limitations that must remain visible:

- LiveTranscribe and ProjectClerk columns were **file mode**, not pre-Stop live.
- LiveTranscribe live capture requires attended AV/TCC; ProjectClerk's live path is app-only.
- ProjectClerk was run through the surviving July `pcbench` pipeline replica, not its current
  app UI. Treat it as that pipeline lineage, not a certification of current ProjectClerk.
- Latencies use different models, hardware, and build types; they are provenance, not a speed
  ranking.
- Authoritative m4mbp heads verified at handoff time: LiveTranscribe `6a8d0c1fafe8` on
  `ralph/production`; ProjectClerk `4345b6619032` on `main`. Both user worktrees are dirty.
  Read committed content with `git show HEAD:<path>`; do not edit, clean, stash, or reset them.

Full table and raw-output provenance:
`evidence/live-convergence-0824/benchmark/REPORT.md` and `benchmark/results.json`.

## D1 — next work targets pre-Stop live, not terminal quality

Terminal quality has already converged structurally to file mode. Further terminal work is
latency/long-meeting work, not the current quality bottleneck. The next research question is:

> Can a reader get near-file text and speaker quality before Stop, with bounded corrections
> and without decoding every second of audio many times?

The mental model: the 2.5-second base span publishes quickly but sees little context. A longer
rolling witness re-hears the same audio and may replace provisional words. The problem is not
merely choosing a larger window; it is deciding **when a later view is trustworthy enough to
replace an earlier view**, including cases where word boundaries or speaker turns move.

## A1 — read-only audit and offline re-score

Before live traffic, run:

```bash
git status --short --branch
git rev-parse HEAD
tmux capture-pane -p -J -t MOSS:1.1 -S -120
tmux capture-pane -p -J -t MOSS:2.1 -S -120
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_campaign_report.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_plan_record.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_design_verdict.py
```

Verify the service runtime and deployed source revision before sending traffic. Do not restart
or touch the 4070 Ti merely to inspect state. The campaign production build is `22dc5b8`; later
commits are evidence/docs/verifiers.

## A2 — build one measurement harness for all three MOSS surfaces

The existing `live_service_replay.py` calls Stop immediately after its last frame and records
only the eventual terminal snapshot. Extend the **bench**, not production, so one paced session
records:

1. `pre_stop_immediate`: snapshot immediately after the final audio frame and before Stop;
2. `pre_stop_settled`: optional snapshot after already-admitted rolling work drains, still
   before Stop, with wait duration recorded;
3. `stop_return`: the asynchronous Stop response;
4. `post_stop_final`: snapshot after `finalization_status=final`;
5. `file`: same audio bytes submitted to `/api/jobs`.

Why record two pre-Stop snapshots? “The user finished speaking” and “the rolling queue has
finished correcting” are different moments. Collapsing them can make waiting look like model
quality. Never wait silently; record the wait as latency.

Add prefix checkpoints at 25%, 50%, and 75% only if the evaluator can slice the golden
reference at the same time boundary without seeing future truth. Otherwise omit them rather
than inventing a live-quality curve.

Required artifact fields:

- exact PCM path/bytes, case ID, duration, reference path;
- repo HEAD, deployed runtime descriptor/config/model, client host;
- every transcript surface in JSONL, not only hashes;
- session/event clocks, accepted/accounted samples, queue depth, failures;
- base, rolling, terminal, and combined GPU RTF; decode request count and decoded-audio work;
- first publication p50/p95, correction age p50/p95, stop-to-final p50/p95;
- WER, TBSA, DER, text coverage, content recall, speaker accuracy, matched-word speaker accuracy;
- per-case results plus macro and duration-weighted aggregates with explicit denominators.

## A3 — golden stress matrix

Use only fully referenced real cases for headline accuracy:

| case | duration | source |
|---|---:|---|
| Bill Ackman | 1m | `data/real/benchmark_diarization_1min/samples/lex_bill_ackman` |
| Javier Milei | 1m | `data/real/benchmark_diarization_1min/samples/lex_javier_milei` |
| Keyu Jin | 1m | `data/real/benchmark_diarization_1min/samples/lex_keyu_jin` |
| Adam Frank | 3m | `data/real/calibration_diarization_3min/samples/lex_adam_frank` |
| Keyu Jin | 5m | `data/real/benchmark_5m/lex_keyu_jin` |

All paths are beneath `prototypes/streaming-diarization/`. Exclude `acquired_*` partial or
masked references from aggregate quality.

Run sequentially with one inference request in flight:

- one discarded warm-up;
- two paired passes over all five cases, alternating case order;
- five back-to-back 1-minute sessions for stability;
- three 5-minute sessions only if the first two passes disagree or queue/RTF is unstable.

If deterministic runs are identical, say so; do not manufacture a confidence interval from
duplicate caches. Preserve cold and warm timing separately.

## A4 — peer comparison, in two evidence tiers

### Tier 1: reproducible now

Re-score the committed peer file outputs and MOSS surfaces through one evaluator. Reproduction:

```bash
moss_rescore_tmp=$(mktemp -d /tmp/moss-external-rescore.XXXXXX)
mkdir -p "$moss_rescore_tmp/lt" "$moss_rescore_tmp/pc"
for case in lex_bill_ackman lex_javier_milei lex_keyu_jin_1m lex_adam_frank_3m lex_keyu_jin_5m; do
  ln -s "$PWD/evidence/live-convergence-0824/benchmark/raw/lt-$case" \
    "$moss_rescore_tmp/lt/$case"
  ln -s "$PWD/evidence/live-convergence-0824/benchmark/raw/pc-$case" \
    "$moss_rescore_tmp/pc/$case"
done
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/score_external_benchmark.py \
  --lt-root "$moss_rescore_tmp/lt" \
  --pc-root "$moss_rescore_tmp/pc" \
  --output /tmp/moss-external-rescore.json
```

### Tier 2: actual live peers, only if operationally possible

Inventory committed docs/code over read-only SSH. For LiveTranscribe, inspect its refined-live
overlay and stop-finalization contracts. For ProjectClerk, identify whether current app code can
export a timestamped pre-Stop and post-Stop transcript for a deterministic audio source. If an
attended AV/TCC run is needed, arrange it explicitly; do not substitute file import.

For any actual peer live run, use the same five PCM files, export raw timestamped speaker rows,
and score them only in this repo. Preserve each product's own labels; evaluator mapping is
label-invariant. Separate quality from latency because hardware/model differ.

## A5 — prototype the next pre-Stop improvement; do not implement from intuition

Use `prototypes/streaming-diarization/`, print full state, and write `NOTES.md` before any
production edit. Rank candidates by measured quality gain, correction latency, and decoded-audio
work.

### O1 — geometry sweep

Measure at least current `10/10`, quality-oriented `15/10`, and lower-latency geometries whose
window plus stride is shorter. Prior evidence:

- `10/10`: shipped; trio WER `.131357`, correction p95 `8.756675 s`, +1.0x audio decode work.
- `15/10:lexical`: offline trio WER about `.1075`, but about 1.5x witness work and slower
  corrections.
- `10/5` overlap can improve correction age but doubles witness work; stitching policy matters.

Do not assume `8/4`, `6/6`, or any other arm wins. Decode them on the production model and score
the same full-reference cases. The owner previously accepted the 8.76-second delay for now, so a
latency-only win is insufficient; seek a material pre-Stop quality gain.

### O2 — selective overlapping witness

Default to cheap `10/10`; request overlapping context only near uncertain seams. Potential
signals are base-vs-witness lexical disagreement, missing boundary words, unparseable/empty base
spans, or a speaker turn crossing the owned interval. This must beat always-overlap on decoded
audio work while approaching its quality.

An isolated prior prototype exists on branch `prototype/window-disagreement-0825`, commit
`03972a2`, with notes under
`prototypes/streaming-diarization/window-disagreement-reconciliation/`. It found deterministic
window disagreement, but only seven unique material events; that is not enough to ship a router.
Do not cherry-pick blindly. Reproduce/extend after the campaign branch disposition is decided.

### O3 — whole-view reconciliation, not token voting

Port the safe principle from LiveTranscribe, not its exact machinery:

- compare independent decodes of the **same retained PCM**;
- align words by time and normalized lexical content;
- compare speaker partitions label-invariantly because `S01` names are local to each decode;
- choose one coherent segment/view for an owned interval, or abstain;
- never assemble a majority-vote sentence from incompatible hypotheses.

MOSS emits joint ASR + diarization, so re-decoding a witness window reruns both together. There is
no separate MOSS ASR lane to splice independently. Speaker names must be mapped by overlap/identity
after choosing the coherent view.

### O4 — speaker-boundary refinement

M3 measured that 63% of remaining speaker confusion came from segments straddling a true speaker
turn, 27% from sub-0.5-second microfragments, and only 10% from true identity misattribution.
Therefore prototype local boundary resegmentation around disagreed turns before changing the
speaker identity bank. The five-phase VAD ensemble from LiveTranscribe is not a default answer:
prior evidence found all five phase views can miss the same handoff.

## Decision gates for production work

Do not ship a pre-Stop algorithm unless it satisfies all of these on fresh, uncached model runs:

- improves trio and five-case pre-Stop WER materially against shipped `10/10`;
- no case regresses by more than `.02` absolute WER or DER without an explicit owner ruling;
- reports DER and matched-word speaker accuracy, not WER alone;
- correction p95 and first-publication latency are measured from event clocks;
- combined GPU RTF `<1`, one in-flight request, bounded queue, zero failed windows;
- decoded-audio work and request count are reported;
- file output remains byte-identical;
- reconciler never reads the reference/golden transcript;
- result uses at least the five fully referenced cases above, or says the evidence is too small.

Any new threshold, stitcher, router, or ownership policy remains a prototype until these gates are
met. Write **unmeasured** where the instrumentation or peer mode does not exist.

## Open human decisions; do not silently sign them

The campaign report remains mechanically complete but owner-unsigned. Four rulings cover five
unsigned gates: baseline 5m decoder reproducibility, the small M1 bound miss, acceptance of the
8.756675-second correction p95, and the Adam terminal-vs-rolling trade. Also outstanding:

- attended browser end-to-end test;
- portal render time under load;
- branch merge/push decision.

See `evidence/live-convergence-0824/CAMPAIGN_REPORT.md` and plan §18. Do not convert an unsigned
row into acceptance on the user's behalf.

## Expected deliverables

1. A preregistered three-surface stress plan with exact denominators and clocks.
2. A runnable bench harness; no production changes in this step.
3. Raw per-run JSONL plus one results JSON for pre-Stop, post-Stop, and file.
4. A cross-project report separating actual live measurements from file proxies.
5. A prototype `NOTES.md` with measured verdict for each candidate geometry/reconciler.
6. One recommended production change, or a clear “none passes” result.

## Suggested skills for the next session

- `$tmux-peer MOSS:1.1` — recover Claude's completed campaign reasoning and open rulings.
- `$diagnose` — if any fresh result differs from the checked-in baseline.
- `$prototype` — mandatory for geometry, reconciliation, speaker-boundary, or routing changes.
- `$aisight-xreview` — only when the owner explicitly requests another cross-review.

Scratch paths in commands above are local inputs/output destinations, not bundled evidence; retained outputs from the original Mac run are MacStudio-local (not in repo).
