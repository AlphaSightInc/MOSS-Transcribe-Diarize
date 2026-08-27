# Plan — recover rolling convergence, rebaseline 10/10, then decide 15/10 lexical

**Status:** implementation-ready; no implementation authorized by this document alone  
**Date:** 2026-08-25  
**Recommended executor:** Codex `/goal`, in two bounded goals separated by owner decision D-M2-3  
**Controlling evidence:** `evidence/live-policy-sweep-20260825/G4-root-cause/NOTES.md` and
`evidence/live-policy-sweep-20260825/REPORT.md`

## 1. Outcome

First remove the observed reason deployed 10/10 stops correcting after about 40 seconds on the
Jamie discussion. Then acquire a new deployed 10/10 baseline on the same six real clips. Only
after that baseline exists does the owner decide whether correction age `<= 6 s` is a hard product
constraint. If accuracy wins that decision, run a separately preregistered, deployed
10/10-versus-15/10-lexical comparison.

The first production change is deliberately smaller than Claude's proposed two-part fix:

1. **Normalize rolling decoder segments before publication** with the already measured terminal
   overlap rule. This directly repairs the reproduced Jamie refusal.
2. **Name a refused normalized proposal and stop rolling cleanly.** Do not silently let it turn
   into `pcm_evicted`.
3. **Do not advance `canonical_through_sample` without an accepted replacement surface.** That
   field means rolling owns the entire prefix. Advancing it without segments removes provisional
   base segments from `effective_transcript` (`live_session.py:858-877`) and conflicts with
   ADR-0005 D4.

A base-text carry-forward remains a valid contingency, but it is a new publication policy. Build
it only if a real proposal still refuses after normalization, and only after a prototype proves
that it preserves every base word, speaker label, timestamp boundary, and ownership invariant.

## 2. Verified starting facts

- **F1 — Reproduced cause:** Jamie rolling window 4, `[640000,800000)`, contains two different
  local-speaker segments overlapping by 2,720 samples. `LiveSession` refuses the proposal as
  `segments_out_of_order`.
- **F2 — Existing repair:** `resolve_terminal_overlaps` moves the later segment's start to the
  previous end. On the retained probe it loses 0 of 24 words and makes the proposal admissible.
- **F3 — Failure propagation:** only an accepted revision advances `canonical_through_sample`.
  The next 10/10 window therefore cannot plan; the two-window PCM ring eventually reports
  `pcm_evicted` and rolling remains absent for the rest of the meeting.
- **F4 — Not GPU contention:** a quiet-GPU reproduction has canonical p95 RTF `.359` and the same
  refusal sequence.
- **F5 — Benchmark consequence:** the old deployed 10/10 Jamie row covers only about 40 seconds,
  while both 15/10 shadows cover the full 180 seconds. The `.1445 -> .1084` macro WER comparison
  is not an honest arm delta until 10/10 is fixed and rerun.
- **F6 — Guard-band alternative rejected:** Claude's fresh 15/7.5 guard-band arm measured macro
  WER `.1139` at `1.84x` decode cost versus lexical `.1084` at `1.35x`. It is not a successor arm.

## 3. Decisions and boundaries

- **D1 — Executor:** use `/goal`, not the completed Ralph campaign. This is one serial causal
  chain with an owner stop in the middle. The existing Ralph run is complete and its context is
  large; its launcher also commits/checkpoints each iteration while this worktree contains
  user-owned untracked evidence.
- **D2 — Current root fix:** reuse one general overlap normalizer for terminal and rolling
  proposals. Keep `LiveSession._text_revision_refusal` strict.
- **D3 — Refusal semantics:** a normalized proposal that is still refused transitions rolling to
  an explicit `proposal_refused` state, records the stable reason, releases its ring, preserves the
  provisional suffix, and schedules no later witness.
- **D4 — No pointer-only skip:** never mutate `canonical_through_sample`,
  `text_revision_version`, or `_revision_segments` merely to move the planner. A refusal changes no
  reader-visible text.
- **D5 — Conditional carry-forward:** prototype only after an observed post-normalization refusal.
  It may ship only through the existing `apply_text_revision` seam and only if its replacement
  surface is exactly word/label preserving over the refused interval. Otherwise rolling stops and
  terminal finalization remains the recovery authority.
- **D6 — Candidate order:** if D-M2-3 authorizes an accuracy-first bake-off, test **15/10 lexical +
  speaker-map**. Do not spend another run on stable-anchor or guard-band first.

Out of scope:

- changing the 2.5-second provisional hard cap;
- weakening any of `LiveSession`'s proposal validations;
- changing terminal finalization, identity policy, file mode, or peer applications;
- feature flags, compatibility wrappers, migrations, or a general retry framework;
- treating post-Stop terminal accuracy as pre-Stop rolling accuracy;
- committing, pushing, or cleaning unrelated user-owned files.

## 4. Goal 1 — G4 repair and honest deployed 10/10 baseline

### A0 — Adopt state without absorbing unrelated work

Record in the new evidence root:

- branch, HEAD, `git status --short`, and production-file diff;
- SHA-256 of the production patch plus SHA-256 of every touched production file; HEAD alone does
  not identify an uncommitted deployed build;
- service PID/start time and deployed application revision;
- runtime descriptor before the change;
- remote model identity and vLLM running/waiting queue depths;
- corpus manifest and all six audio/reference hashes;
- exact source evidence paths for F1-F5.

Use a new root such as:

```text
evidence/live-g4-recovery-20260825/
```

Do not copy the corpus or existing raw traces. Point to their immutable paths. Stop if a tracked
production file needed by this plan already has an unrelated edit.

### A1 — Six-corpus normalization prototype, then red regression

The terminal resolver was measured on duplicate segments from overlapping file windows. Jamie is a
different shape: overlapping speakers inside one rolling decode. Before production edits, extend
the standing bench with a truth-blind audit over **every retained 10/10 decode in both six-case
passes**, not only Jamie.

One proposed command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/audit_rolling_normalization.py \
  --sweep evidence/live-policy-sweep-20260825 \
  --output evidence/live-g4-recovery-20260825/normalization-prototype.json
```

For every proposal, print and retain input/output segments, merge/drop/displacement counts, word
stream before/after, session refusal before/after, and score deltas after reconstructing the full
surface. Prototype gates:

- every ordinary disjoint proposal is byte-identical;
- every observed proposal becomes admissible through the real session seam;
- no observed proposal drops a word;
- full-surface WER and speaker scores do not regress;
- Jamie window 4 moves the later start by 2,720 samples and preserves 24/24 words.

Record the verdict in `NOTES.md` beside the prototype and in the new evidence root. Stop if any
gate fails; do not broaden the resolver from intuition.

After the measured verdict, add a deterministic red regression using the retained Jamie window-4
decode:

1. Feed its two parsed segments into the rolling proposal path.
2. Prove the current path returns `segments_out_of_order`.
3. Apply the shared resolver.
4. Assert:
   - output segments are ordered, advancing, disjoint, and within `[640000,800000)`;
   - displaced samples equal `2720`;
   - merged and dropped counts are zero;
   - input and output word sequences are identical, 24 words;
   - the normalized proposal passes the real `LiveSession.apply_text_revision` seam.

Also add table-driven constructed shapes already held by terminal tests: disjoint, touching, same-speaker
overlap, cross-speaker overlap, contained segment, identical extent, unsorted input, and chains of
three. These are contract tests, not measurement. The rolling test must call the same resolver as
terminal; do not duplicate its algorithm.

### A2 — Production normalization

Make one rule producer-neutral:

1. Rename `TerminalSeamResolution` / `resolve_terminal_overlaps` to producer-neutral names in
   `app/live_transcript_convergence.py`; update all internal callers and tests. Do not leave an
   alias because no external compatibility consumer exists here.
2. In `RollingTranscriptConverger._segments_of`, retain each parsed local speaker long enough to
   normalize `(speaker,start,end,text)` tuples before converting them to
   `EffectiveTranscriptSegment`.
3. Preserve the current interval, truth blindness, token order, and speaker projection behavior.
4. Carry `merged`, `dropped`, and `displaced_samples` into the rolling completion record and the
   `rolling_decode_completed` event. No event may contain transcript text.
5. Leave `LiveSession._text_revision_refusal` unchanged. The producer sends valid inert data; the
   session remains the sole authority.

Expected files:

- `moss_transcribe_diarize/app/live_transcript_convergence.py`
- `moss_transcribe_diarize/app/live_coordinator.py`
- `moss_transcribe_diarize/app/live_service_runtime.py`
- `tests/test_live_transcript_convergence.py`
- `tests/test_live_rolling_wiring.py`
- `tests/test_live_terminal_finalizer.py`

Touch `live_session.py` only if a data-only telemetry field belongs on `TextRevisionProposal`.
Do not change its validation or surface-building behavior.

### A3 — Truthful refusal terminal state

The current converger counts a decoded proposal as completed before the session accepts it. When
that proposal is refused, it remains nominally `rolling` until buffer overflow renames the cause
`pcm_evicted`. Repair the status, not the frontier:

1. Add `RollingStatus.PROPOSAL_REFUSED = "proposal_refused"`.
2. Give `RollingTranscriptConverger` one method that accepts the stable refusal reason after
   `apply_text_revision` returns false. It freezes planning, clears retained PCM, and increments a
   dedicated refusal count. Persist `proposal_refusals` and `last_proposal_refusal` in
   `RollingConvergerAccounting`; do not leave the cause only in one transient event. It does not
   alter window-completed, window-failed, decoded-audio, or session text state.
3. Call it from `LiveCoordinator.submit_refinement` only for an actual rolling proposal refusal.
4. Preserve the original `text_revision_refused` event; the completed-window event must report
   `proposal_refused`, the refusal reason, zero later windows, and zero retained PCM.
5. `accept_pcm` after any non-rolling terminal refinement state must still validate contiguous
   sample offsets and advance accepted-sample accounting, but retain zero PCM and plan nothing.
   Base capture cannot stop merely because refinement stopped.
6. Stale completions and decoder-no-answer paths retain their current semantics.

Required regressions:

- injected post-normalization refusal changes rolling status to `proposal_refused`, not
  `pcm_evicted`;
- the base `effective_transcript`, canonical commits, committed-prefix hash,
  `text_revision_version`, and `canonical_through_sample` are byte/value identical before and
  after refusal;
- no next refinement is queued;
- feeding more than two windows of PCM after refusal keeps the same status/reason, retains zero
  samples, advances accepted samples exactly, and never converts the cause to `pcm_evicted`;
- the base path continues publishing and accepted/accounted session samples remain exact;
- terminal finalization still runs and can replace the complete surface;
- event vocabulary is derived from production and includes the new state;
- replay round-trip tests are extended if any serialized snapshot/result field changes.

### A4 — Focused and repository validation

Run in this order, widening only after the prior layer passes:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/test_live_transcript_convergence.py \
  tests/test_live_text_revision.py \
  tests/test_live_rolling_wiring.py \
  tests/test_live_terminal_finalizer.py

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_live_service_replay.py

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/
```

Then run the retained Jamie probe through the production classes with cached/raw decoder output.
It must plan and apply windows 0-4, report the window-4 displacement, and queue window 5 when the
base frontier permits. No GPU result is required for this code-path proof.

Hard stop if any of these occur:

- any word is dropped from the Jamie window;
- the resolver invents a boundary not present in the overlapping inputs;
- a refusal changes the reader-visible surface or canonical frontier;
- terminal behavior changes;
- full-suite result regresses from the adopted baseline.

### A5 — Deploy exact code and rerun deployed 10/10

Restart the existing development service onto the reviewed production diff and capture
pre/post descriptors plus PID/start-time/command/cwd proof. Persist the production patch SHA-256
and every touched production-file SHA-256 beside the restart record. Do not change model, endpoint,
identity settings, or the 10/10 geometry.

Run exactly the same prepared six-case corpus, actual-live only, two paced passes in alternating
order:

- monologue: Javier 50 s;
- two-person: Bill 60 s, Keyu 60 s, Adam 180 s;
- multi-person: Jamie 180 s, RTFL 89.9935 s.

Extend the existing sweep driver with a narrow `--actual-only` mode rather than re-running the
15/10 shadows or peers. One proposed command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/moss_sweep.py \
  --corpus evidence/live-policy-sweep-20260825/corpus \
  --output evidence/live-g4-recovery-20260825/deployed-10-10 \
  --passes 2 \
  --actual-only
```

The driver change is benchmark-only and must preserve the old default behavior.

### A6 — G4 recovery gates

All are hard gates:

- **G1 — Exact execution:** 12/12 actual-live sessions, 1,239.987 observed audio-seconds; exact
  accepted/accounted samples; all raw surfaces retained.
- **G2 — Full rolling coverage:** every full 10-second window plans, decodes, and completes in
  order. Expected per pass: Javier 5, Bill 6, Keyu 6, Adam 18, Jamie 18, RTFL 8. A sub-10-second
  tail remains provisional until terminal by design.
- **G3 — Root-cause closure:** zero `segments_out_of_order`, zero other text-revision refusals,
  zero `pcm_evicted`, zero `proposal_refused`, zero failed windows, zero stale completions, zero
  admission refusals, zero terminal failures.
- **G4 — Jamie witness:** the cached regression records displacement `2720`, loses zero words,
  applies, and queues window 5. Fresh deployed decodes need not reproduce the same segmentation;
  each live Jamie pass must instead complete windows 0-17 with no refusal or eviction.
- **G5 — Runtime:** combined pre-Stop inference RTF `< 1`; at most one queued-or-running refinement;
  endpoint/model queues drain to zero.
- **G6 — Surface:** post-fix 10/10 WER, content recall, TBSA, legacy DER, matched-word speaker
  accuracy, reference-speech DER, first-publication age, changed-region correction age, drain wait,
  and Stop-to-final latency are reported per case, macro, category, and duration-weighted mean.
- **G7 — Provenance:** service code revision, runtime descriptor, model identity, and corpus hashes
  are exact and stable across both passes.

Do not require transcript byte identity across passes; prior evidence says long greedy decodes are
not bit-stable. Report both passes and fixed denominators.

### A7 — Rebaseline report and D-M2-3 packet

Write one report that separates:

1. **Before/after defect evidence:** rolling extent and refusal/eviction behavior.
2. **New deployed 10/10 baseline:** the only valid comparator for a future deployed 15/10 arm.
3. **Old shadows:** historical context only; do not recompute a promotion delta against the
   crippled pre-fix Jamie row.
4. **Latency clocks:** changed-region provisional-to-correction age must be separate from
   shadow word-availability age and browser paint.

Add a dated verdict to `docs/design-streaming-diarization.md` §7 covering the shared-normalizer
prototype, explicit refusal-state behavior, full G4 gate result, and new deployed 10/10 baseline.
Point to raw evidence; do not duplicate its large tables. ADR-0005 remains unchanged because the
session validation and continuous accepted-authority contract remain unchanged.

Then stop for the owner ruling:

### D-M2-3 — Is `<= 6 s` changed-region correction p95 binding?

- **O1 — Binding hard gate.** Do not deploy a full-window 15/10 candidate. Existing structural
  evidence says none of 10/10, 15/10, or the measured overlap geometries can satisfy six seconds.
  End this goal with a new prototype question for a shorter or partial correction geometry.
- **O2 — Accuracy-first with explicit latency budget.** Authorize Goal 2. The owner must write the
  maximum acceptable changed-region correction p95; do not infer it from the old shadow clock.

Recommended wording for the owner record:

```text
D-M2-3 = O1|O2. Changed-region correction p95 is [hard <=6 s | allowed up to ___ s].
If O2, accuracy materiality is max(.01 absolute WER, 2x Goal-1 control-pass WER spread), and
first-publication non-inferiority is max(.5 s, 2x Goal-1 control-pass p95 spread).
First publication remains a separate live-mode constraint. Signed/date: ___
```

Goal 1 is complete when the post-fix baseline and this decision packet exist. It must not begin
15/10 production work without the signed O2 ruling.

## 5. Goal 2 — conditional deployed 15/10 lexical bake-off

Run only after D-M2-3 = O2.

### B0 — Preregister before code or inference

Freeze:

- exact post-fix 10/10 evidence root and denominators;
- exact six-case corpus hashes;
- 15-second window, 10-second stride, lexical overlap alignment, and session-speaker projection;
- two fresh deployed 15/10 passes, alternating case order, on the same quiet GPU;
- a fresh 24-session ABBA comparison: 10/10-A, 15/10-A, 15/10-B, 10/10-B, six cases per block;
- changed-region correction p95 over pooled changed rolling-owned regions across all 12
  observations per arm, using nearest-rank p95; also report per-case, category, and legacy-trio
  distributions;
- first-publication p95 over every non-empty provisional span across all 12 observations per arm;
- owner-supplied correction p95 ceiling;
- the D-M2-3 accuracy-materiality and first-publication non-inferiority formulas, evaluated from
  Goal 1's control-only evidence before any candidate inference;
- accuracy/resource gates and stop rules below.

Reference truth remains scorer-only. The reconciler cannot read it.

### B1 — Production-path prototype

Before production code, absorb the measured lexical reconciler into a throwaway adapter around
the production `RollingTranscriptConverger` contracts. The saved stitcher is a batch whole-view
algorithm; this prototype must prove it can become a causal monotonic publisher.

The contract to test:

1. Maintain separate cursors: decode-window starts are `0,10,20,...`; the accepted publication
   frontier starts at `0` and never moves backward.
2. The first `[0,15)` decode may propose `[0,15)`. Each later `[d,d+15)` decode uses `[d,d+5)` as
   read-only lexical context and may propose only `[frontier,d+15)`, normally ten new seconds.
3. Align the new window's overlap words against already published words; aligned duplicate prefix
   words are context, never republished. Every later proposal starts exactly at the session's
   current frontier and never rewrites the five seconds behind it.
4. Enumerate every segment or token straddling the frontier. An aligned straddler may stay owned by
   the earlier view. An unmatched straddler has no pre-authorized causal rule: stop the prototype
   unless one measured rule preserves the word without inventing a timestamp boundary or rewriting
   prior authority.
5. Admit only complete 15-second windows before Stop. After the last full window, keep the remaining
   sub-15-second tail provisional until terminal finalization.

Replay all saved six-case 15/10 decodes and print every cursor, owned interval, alignment,
selected/dropped word, straddler, window eligibility clock, and final surface. Require two distinct
equivalence checks:

- **content/ownership:** exact equality to the saved lexical content on identical decodes, while
  every proposal satisfies the live session's frontier contract;
- **speaker:** after the real session's base labels settle, final speaker projection equals the
  saved settled-speaker surface. Report intermediate causal speaker surfaces separately; they are
  not required to equal a future-informed shadow at every prefix.

Pass only if both checks succeed, one-owner intervals hold, joins do not duplicate words, and Stop
admits no clipped window. If the batch stitcher cannot be expressed causally, stop or amend
ADR-0005 through owner review; do not implement a second lexical algorithm from memory.

### B2 — Production implementation

Implement only the measured 15/10 lexical policy:

- `RollingGeometry` admits the exact 15/10 geometry selected by the owner; no arbitrary geometry
  framework or runtime feature flag;
- decode cursor and accepted publication frontier remain separate internal facts;
- the converger hides lexical overlap ownership behind its existing four-method interface;
- local witness speakers are projected through the existing session speaker-map path;
- one witness is queued/running per session;
- normalization from Goal 1 runs after lexical reconciliation and before session validation;
- events expose window, owned interval, alignment outcome, normalization counts, work, and timing,
  never transcript text;
- 10/10 remains the explicit control policy in tests and the frozen Goal-1 source tree; do not add
  a compatibility branch or arbitrary runtime strategy registry.

Expected files are limited to the rolling module, coordinator/runtime event contracts, the exact
production policy construction seam, and their tests. Validate in layers:

```bash
# T1 — causal planner/reconciler and authority
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/test_live_transcript_convergence.py tests/test_live_text_revision.py

# T2 — scheduling, runtime, event accounting
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/test_live_rolling_wiring.py tests/test_live_service_runtime.py

# T3 — consumer and terminal invariants
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/test_live_service_replay.py tests/test_live_portal.py \
  tests/test_live_export_surface.py tests/test_live_terminal_finalizer.py \
  tests/test_live_terminal_lifecycle.py

# T4 — retained six-case, zero-GPU production-class verifier
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/verify_causal_15_10.py \
  --sweep evidence/live-policy-sweep-20260825

# T5 — repository regression
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/
```

Also prove the paired file-mode and terminal outputs are unchanged on the retained fixtures.
Mutation checks must catch: decode cursor coupled to publication frontier, lexical trim omitted,
retroactive overlap republished, normalization omitted, and refusal telemetry lost.

### B3 — Isolated source provenance

Prepare two isolated source trees from the same reviewed Goal-1 base: fixed 10/10 control and
15/10 lexical candidate. Do not switch behavior with a runtime feature flag. Persist for each tree:

- base HEAD;
- complete patch SHA-256;
- every touched production-file SHA-256;
- service command/cwd, PID, start time, and pre/post descriptor for every restart.

Keep both trees until review so every ABBA block is reproducible. A service restart may claim only
the tree named by its `ps`/cwd proof.

### B4 — Fresh deployed head-to-head

Execute **24 fresh actual-live sessions** in preregistered ABBA block order: 10/10-A, 15/10-A,
15/10-B, 10/10-B. Each block contains all six cases in its preregistered forward/reverse order.
Restart whenever the source tree changes and discard one warm-up before every block. Use the same
quiet GPU and collect immediate pre-Stop, settled pre-Stop, and post-Stop surfaces with identical
scorers and clocks.

Compare 10-A with 15-A, 10-B with 15-B, and the fixed two-pass aggregates. Goal 1's baseline is a
drift diagnostic, not the promotion denominator. The prior shadows are research context only.

### B5 — Promotion gates

- **P1 — Accuracy:** two-pass six-case macro WER improvement meets the D-M2-3 frozen materiality
  formula versus the fresh ABBA 10/10 control; every category mean is non-worse; no case worsens by
  more than `.02` absolute WER or DER; macro matched-word speaker accuracy is no worse by more than
  `.02`. Content recall and reference-speech DER are also reported.
- **P2 — Latency:** changed-region correction p95 is within the owner-signed D-M2-3 ceiling. First
  publication p95 meets the frozen D-M2-3 non-inferiority formula versus fresh ABBA 10/10 and is
  reported against the historical product gate separately. Use B0's fixed denominators and
  nearest-rank p95; never select a friendlier population after inference.
- **P3 — Integrity:** exact sample accounting, all eligible windows completed, no refusals,
  evictions, failed/stale windows, terminal failures, or dropped canonical commits.
- **P4 — Resources:** combined RTF `< 1`, bounded one-refinement queue, quiet endpoint before/after,
  and explicit decoded-audio/model-call cost versus 10/10.
- **P5 — Stability:** both pass-matched comparisons improve WER directionally and independently
  satisfy P2-P4; P1 materiality applies to the fixed two-pass aggregate. Raw disagreement is
  reported rather than averaged away.
- **P6 — Scope:** file mode, terminal finalization, identity policy, provisional cap, and corpus are
  unchanged.

If all gates pass, recommend 15/10 lexical for review; do not silently change production defaults
or merge. If any gate fails, retain post-fix 10/10 and write the failed denominator and reason.

In either outcome, append the dated causal-prototype and deployed ABBA verdict to
`docs/design-streaming-diarization.md` §7 with evidence pointers. Amend ADR-0005 only if B1 cannot
preserve D4, the plan stops, and the owner explicitly authorizes a new authority decision; a failed
prototype alone does not rewrite the ADR.

## 6. `/goal` launch contracts

Use two goals so the owner decision is real rather than simulated.

### Goal 1 objective

```text
Execute docs/plans/live-g4-recovery-and-arm-decision-20260825.md through A7 only.
Fix the observed rolling overlap refusal without weakening LiveSession validation or advancing
canonical authority without published segments; deploy and rerun the two-pass six-case actual-live
10/10 baseline; write the D-M2-3 decision packet. Preserve unrelated work, do not commit or push,
and stop before all 15/10 production work.
```

### Goal 2 objective, only after signed D-M2-3 = O2

```text
Execute Goal 2 of docs/plans/live-g4-recovery-and-arm-decision-20260825.md using the signed
D-M2-3 latency ceiling and Goal 1's deployed 10/10 evidence as the frozen comparator. Prototype,
implement, deploy, and measure only 15/10 lexical; do not promote, merge, commit, or push.
```

## 7. Final handoff contents

Each goal returns:

- exact branch/HEAD and production diff;
- exact commands and test counts;
- runtime/model/corpus provenance;
- denominators, raw artifacts, per-case and aggregate metrics;
- the corresponding dated `docs/design-streaming-diarization.md` §7 verdict;
- every failed or unmeasured gate without substitution;
- service/process/queue state after cleanup;
- decision reached and the single next authorized action.
