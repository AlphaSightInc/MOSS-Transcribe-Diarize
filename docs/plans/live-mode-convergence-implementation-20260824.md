# Live-mode transcript convergence — review-gated implementation plan

**Status:** Proposed; **not authorized for implementation**

**Date:** 2026-08-24

**Applies to:** `MOSS-Transcribe-Diarize` live mode on the MacStudio frontend/backend with
joint MOSS inference on the RTX 4070 Ti

**Required before implementation:** independent technical review, evidence verification,
architecture decision approval, and explicit owner authorization

**Cross-review verification:** 2026-08-24 evening (Claude and Codex). The initial Claude pass
re-verified this repo's measurements and code references but checked the sibling LiveTranscribe
project against a stale MacStudio clone (all local refs end 2026-06-17). The Codex pass repeated that
check on the authoritative repo at `ga0@m4mbp` (HEAD 2026-08-11), corrected V4 and §13, and
reconciled the latency clocks with the prototype implementations; the Claude second round
re-verified every m4mbp citation over SSH. §3.3 and §3.5
record the resulting evidence. Appendix A lets a junior developer execute each phase without
re-deriving file locations, commands, or baselines.

## 0. Upfront synthesis

Live mode should become a **three-authority transcript**:

1. A short joint-MOSS decode publishes words quickly and is explicitly **provisional**.
2. A staggered 10–15 second joint-MOSS witness re-hears each region with context and advances
   an **authoritative rolling prefix**.
3. A stop-time 150/120 second windowed pass over complete retained audio publishes the
   **terminal final transcript**.

The current 2.5-second live path loses quality mainly because it repeatedly cuts continuous
speech at arbitrary points. Words near those cuts account for most of the live/file WER gap.
The gap repeats at every cut but does not grow with meeting age. The correction is therefore
not more text history in the prompt, more frequent identity sweeps, timestamp padding, or five
parallel VAD passes. The correction is to let a longer overlapping MOSS request own the
middle of its window, where the model has context on both sides.

Implementation must proceed in five independently reviewable phases:

- **E0 — measurement integrity:** repair replay serialization and establish honest metrics.
- **E1 — bounded decode salvage:** retain usable words already generated in malformed spans.
- **E2 — rolling text convergence:** longer witnesses advance a monotonic canonical prefix.
- **E3 — rolling speaker authority and optional 1-second preview:** longer witnesses own
  their speaker evidence; short windows never anchor final identities.
- **E4 — terminal convergence:** reuse file windowing over complete retained mixed audio.

Every medium/high-risk policy is prototype-gated before its production phase. A failed gate
stops that phase; it does not trigger compensating complexity.

---

## 1. Mission, user contract, and success

### 1.1 Mission

Make live transcription feel immediate while converging toward file-mode word and speaker
quality without unbounded meeting-history cost.

### 1.2 User-visible contract

The user accepts temporary mistakes if they are corrected. The interface must therefore make
three facts true:

- **Fast:** provisional words appear quickly.
- **Convergent:** older words may be silently replaced by a better rolling transcript.
- **Settled:** after finalization, export and the visible transcript use the same terminal
  surface.

The UI does not need to expose model internals. It does need an unambiguous lifecycle:
`provisional → rolling canonical → final`.

### 1.3 Proposed acceptance gates

These gates are proposals for reviewer approval, not claims that production meets them now.

| Code | Gate | Proposed threshold |
|---|---|---:|
| G1 | Mean rolling WER on the fully referenced real trio | `<= 0.15` |
| G2 | Per-case rolling WER | improves over current live on every case |
| G3 | Rolling content recall | `>= 0.94` |
| G4 | Corrected one-second speaker quality | within 2 points of corrected 2.5-second speaker error |
| G5 | Provisional first-word age per non-empty one-second span | p95 `<= 2.0 s` |
| G6 | Rolling correction after provisional publication | p95 `<= 6.0 s` |
| G7 | Two concurrent live sessions | combined inference RTF `< 1`, bounded queue |
| G8 | Terminal finalization | WER within `0.01` absolute of paired file mode |
| G9 | Regression | no file-mode output or metric regression |
| G10 | Accounting | accepted samples equal terminal accounted samples exactly |

Gate definitions a junior developer must not have to guess:

- **G4 comparator.** "Corrected N-second speaker quality" means the speaker error of the S1
  arm (witness-owned speaker evidence, §11.1) measured on that base in the same prototype run.
  G4 passes when S1-on-1.0s speaker error is within 2 absolute points of S1-on-2.5s speaker
  error on the primary trio, scored by evaluator v2's matched-word speaker accuracy and by
  `score_live_speaker_accuracy` (both reported).
- **Baselines for G1–G3.** Current live: WER `.1999`, recall `.9135`. Current file: WER `.1039`,
  recall `.9506`. Source of truth: `prototypes/live-file-gap-baseline-20260824/trio-60s/results.json`
  (the recall values are in `prototypes/live-file-gap-context/results.json` at
  `summary.arms.a0.means` / `summary.arms.a3.means`).
- **G5 clock.** Across every non-empty provisional span in the primary trio, first-word age is
  `provisional publication time − first spoken-word audio start`. It therefore includes the
  capture window, queue wait, and decode time. The all-span distribution is computed by
  `lane_rolling_terminal.py::_first_publication_latency`. The existing
  `lane_current.py::_first_publication` returns only the first non-empty span per case and remains
  a session-start diagnostic; the E3 harness must persist one G5 row per non-empty span before
  calculating p95.
- **G6 clock.** Across every changed rolling-owned region in the primary trio, correction age is
  `changed rolling-witness publication time − publication time of the provisional region it
  replaces`, matching
  `lane_rolling_terminal.py::_provisional_to_correction_latencies`. Unchanged witnesses do not
  enter this distribution.
- **Latency diagnostics.** Queue/decode lag from audio eligibility (the moment the final sample of
  a request window is accepted) is reported separately. Browser-inclusive capture-to-paint timing
  is measured by the E2 browser E2E and reported beside, never blended into, G5 or G6.
- **G7 measurement.** Two `live_service_replay` sessions paced at 1.0× against a quiet GPU
  (nothing else on the 4070 Ti), created by one orchestration process. Pass requires combined
  inference RTF `< 1`, zero dropped canonical commits, at most one queued-or-running refinement
  per session at every sample, and all endpoint/arbiter queues drained to zero after input stops.
  Report the endpoint counter deltas the multiview prototype already collects.

TBSA and DER remain reported for continuity, but they are not sufficient promotion gates until
the evaluator work in E0 is accepted.

---

## 2. First-principles mental model

### 2.1 What the system currently does

```text
16 kHz mixed PCM
      │
      ▼
WebRTC VAD + endpoint policy
      │ closes speech at silence or a 2.5 s hard cap
      ▼
one isolated MOSS request
      │ returns words + local speaker turns jointly
      ▼
WeSpeaker identity preparation
      │ maps local speakers to meeting identities
      ▼
immutable canonical span commit
      │
      ▼
portal snapshot / export
```

MOSS does **not** expose an independent ASR lane in this project. One MOSS decode jointly emits
words, timestamps, and within-window speaker labels. WebRTC VAD is external and determines the
audio span. WeSpeaker is also external and reconciles window-local speakers across the meeting.

### 2.2 Why a hard cut loses words

Suppose the speaker says:

> “the difference between the stock market and—”

and the 2.5-second cap falls inside “between.” One request hears the first half of the word and
the next request hears the second half. Neither request can infer as reliably as a request that
hears the complete phrase. The same problem affects a speaker handoff when one voice ends on one
side of a cut and another begins on the other.

The model is not slowing down from meeting history: it receives no meeting history. Each short
request starts fresh. A 60-minute meeting is therefore many repetitions of the same seam error,
not one progressively larger prompt.

### 2.3 Why an overlapping witness helps

For a 10-second window, trust only its central 5 seconds:

```text
window audio:   [ 2.5 s left context ][ 5 s owned region ][ 2.5 s right context ]
published text:                         ^^^^^^^^^^^^^^^^^^
```

The troublesome edges remain inside the request, but their words are not owned by it. The next
overlapping witness owns the next central region. Each point in the rolling canonical prefix has
exactly one owner.

Current MOSS/vLLM requests do not expose reusable audio-encoder or decoder state across windows:
an overlap is re-encoded and re-decoded. The design reuses retained PCM, each completed witness
decode across text/speaker strategies, and only exact-interval speaker embeddings; it does not
claim neural compute reuse. Window/stride selection therefore remains a measured quality/work
decision.

### 2.4 Why one-second preview can work only as preview

Measured one-second isolated MOSS requests cut first-word age from 3.04 to 1.00 seconds, but WER
worsened from `.200` to `.377` and DER from `.176` to `.457`. A 10-second witness later restored
WER to `.146`, independent of whether the provisional base used 1.0 or 2.5 seconds. It did **not**
restore one-second speaker quality because the prototype still reconciled through weak one-second
identity anchors.

Therefore:

- one-second words may be shown temporarily;
- one-second speaker identities must never become final authority;
- the longer witness must eventually own both its words and its speaker evidence.

---

## 3. Verified evidence and limits

### 3.1 Evidence that governs this plan

| Code | Measured result | Interpretation |
|---|---|---|
| F1 | File WER `.1039`; live WER `.1999` | live roughly doubles word error |
| F2 | File TBSA `.9106`; live `.8384` | headline gap, but scorer is extent-sensitive |
| F3 | 60 s TBSA gap `-7.2 pp`; 300 s `-7.1 pp` | no meeting-age drift |
| F4 | Interior live WER `.082` vs file `.072` | isolated-span interior is near file quality |
| F5 | Within 0.25 s of cuts, live WER `.483` | seam severance dominates |
| F6 | Straddling bigram survival `48.5%`; interior `89.4%` | cuts destroy lexical continuity |
| F7 | Rolling 10/5 WER `.129` in peer prototype; `.146` independently | architecture works; stitching remains unsettled |
| F8 | Seam5 WER `.218–.230` | per-seam five-second re-decode is rejected |
| F9 | Speech-gated malformed-output salvage WER `.200→.189` | useful zero-GPU first fix |
| F10 | Terminal full-minute WER `.104` | file-equivalent upper bound on 60-second cases |
| F11 | One-second + rolling WER `.146`, DER `.292` | text compensation works; speaker compensation does not yet |
| F12 | Identity-only best DER `.176→.156` | identity is secondary to missing/wrong words |

Primary corpus: three fully referenced 60-second real interviews, 180 seconds total. A single
five-minute case supports the duration conclusion. Results and denominators are recorded in:

- `prototypes/live-file-gap-baseline-20260824/README.md`
- `prototypes/live-file-gap-context/NOTES.md`
- `prototypes/live-file-gap-emptyspan/NOTES.md`
- `prototypes/live-file-gap-identity/NOTES.md`
- `prototypes/live-file-gap-timing/NOTES.md`
- `prototypes/streaming-diarization/live-multiview-prototype/NOTES.md`

### 3.2 Evidence limitations

- The primary quality denominator is only three fully referenced minutes.
- The two rolling prototypes use different truth-blind word-time ownership algorithms; the
  `.129–.146` range is not one production-ready number.
- Existing wall-clock results were sometimes measured under shared GPU contention.
- The rolling design has not been stress-tested end to end at two concurrent live sessions.
- Terminal convergence has only been measured on 60-second cases.
- Corrected rolling speaker authority has not been implemented or measured.
- Browser correction behavior and long-session DOM/snapshot cost remain unmeasured.

Every missing item appears as a gate below; none may be inferred from the existing results.

### 3.3 Corrected peer finding: terminal revision visibility

The secondary Jamie trace reports an applied terminal identity revision in its
`identity_finalized` event but shows no revision in the replay terminal snapshot. The runtime is
not reverting the correction. `live_service_replay._live_snapshot_from_dict` omits
`label_revision_version`, and `_commit_from_dict` omits `revised_transcript`, reconstructing their
defaults (`0` and `None`). The one-command reproducer is:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/live-file-roadmap-verification/verify_replay_roundtrip.py
```

It deliberately exits 1 until the adapter is fixed. Primary-trio scores are unaffected because
their terminal sweeps proposed no revisions; secondary identity artifacts are affected.

**Independently confirmed (second pass).** The server side serializes snapshots with
`dataclasses.asdict` (`app/live_service_runtime.py:81,230,253`), so it is field-complete by
construction; the loss is provably confined to the two hand-written client reconstructors
(`live_service_replay.py:891-909` `_live_snapshot_from_dict`, `:920-928` `_commit_from_dict`).
The replay trace's `terminal` event is written from the *reconstructed client object*
(`run_service_replay`, `live_service_replay.py:488`), which is why every replay-derived
terminal snapshot reads `label_revision_version=0` / `revised_transcript=null` regardless of
runtime truth.

**Blast radius (all prior replay artifacts).** Snapshot-derived revision fields are
untrustworthy in every existing replay trace: `prototypes/live-file-gap-baseline-20260824/`
(trio + 5-minute), `/private/tmp/moss-live-stress2-final.*`, `/private/tmp/moss-live-stress4.*`.
The `identity_finalized` *events* in those same traces are trustworthy (they do not pass
through the reconstructors). Two conclusions change:

- The 5-minute case's `identity_finalized` payload shows cumulative
  `identity_revision_version: 2` with zero terminal proposals — the 60-second cadence sweep
  **did fire and applied two label revisions mid-session at 300 s**. "Sweep inertness" is a
  fact only about 60-second sessions (terminal sweep proposed nothing on the trio), not about
  the mechanism in general.
- The earlier "no ASR repair: final sweeps produced no revised transcript" observations were
  made through this same lossy adapter and are evidence only where corroborated by
  `identity_finalized` events (the trio: corroborated; any longer session: re-acquire after
  A0.1).

### 3.4 Evaluator limitation

The current TBSA formula is:

```text
0.40 × text-speaker accuracy + 0.35 × text coverage + 0.25 × (1 − WER)
```

The first two terms currently credit temporal overlap without comparing hypothesis words. A
single 60-second segment containing only `"xx"` receives coverage `1.0`, mean TBSA `.6817`, and
DER `.1722`. Timestamp padding can therefore make live look file-quality while WER stays twice as
bad. This plan rejects timestamp padding and makes lexical metrics primary until evaluator v2 is
approved.

### 3.5 Independent cross-review verification record (2026-08-24, Claude then Codex)

An adversarial cross-review re-verified this plan's evidence base. Reviewers can replay each
check from the pointers below.

| Code | Claim verified | Verdict | How |
|---|---|---|---|
| V1 | Replay adapter drops revision fields (§3.3) | **Confirmed** | `verify_replay_roundtrip.py` exits 1; reconstructors read at `live_service_replay.py:891-928`; server `asdict` confirmed; contradiction reproduced from the baseline Jamie trace |
| V2 | Multiview prototype numbers (F7, F8, F10, F11) | **Confirmed** | `/tmp/moss-live-multiview-results.json` internally reconciles with its NOTES; its `current2.5` per-case WERs equal the deployed baseline to 4 decimals and `terminal150` equals file mode exactly — three independent implementations agree on every shared quantity |
| V3 | One-second degradation (F11), codex-only | **Confirmed independently** | fresh 30 s spot check, independent code: 2.5 s tiling WER `.2264` vs 1.0 s tiling `.2925` (ratio 1.29× ≈ the prototype's per-case Bill ratio 1.26×; the trio ratio 1.88× is driven by Milei at 3.1×). Repro: `prototypes/live-file-roadmap-verification/spotcheck_1s_vs_25s_spans.py` |
| V4 | LiveTranscribe dual-ASR overlay and five-phase / 20-view Jamie evidence | **Confirmed, with negative transfer result** | the first pass grepped `/Users/gao/Desktop/AI_Projects/LiveTranscribe` on MacStudio — a stale clone whose newest local ref is `origin/main` at `d0e2a068` (2026-06-17), predating this work, so its "not found" was true of the clone and wrong about the project; do not trust that clone for anything after June. Read-only verification on `ga0@m4mbp` found the authoritative repo at `/Users/ga0/Desktop/AI_Projects/LiveTranscribe`, HEAD `6a8d0c1` (2026-08-11). `RefinedLiveOverlayProductionWorkProvider.swift:320-360` builds a chunked-ASR candidate and whole-file-ASR witness; `RefinedLiveOSFPartitionSelection.swift:166` requires five views and `RefinedLiveOSFProductionRequestBuilder.swift:197-213` constructs their phase offsets. `docs/adr/0029-refined-live-overlay-display-authority.md:316-323` reports five matched A/B pairs. Crucially, `docs/evidence/overlap-stability-perturbation-0806/REPORT.md:31-32` says all 20 live Jamie views merged the handoff and phase-VAD alone was insufficient. §13 therefore uses this as evidence for uncertainty routing and against blanket phase views, not as proof that five-phase VAD repairs MOSS |
| V5 | Every load-bearing code reference in §6–§10 | **Confirmed** | `FrozenSpan` (`app/live_session.py:75`) carries no speech ratio; `InferenceArbiter` exposes exactly `submit_batch`/`submit_live_canonical`/`submit_live_provisional` (`app/live_arbiter.py:62,68,81`); empty-collapse seam at `app/live_adapters.py:307-311` ← `app/vllm_runner.py:274-278`; `tests/live_identity_accuracy.py` exists |

The `.129` (lexical stitcher, `prototypes/live-file-gap-context/proto_context_arms.py`) vs
`.146` (character/time-proportional stitcher, `live-multiview-prototype`) rolling range is a
real algorithmic difference, not noise; both are truth-blind. The lexical stitcher is the
best-known candidate and is named as the E2 grid's reference arm (§10.2).

---

## 4. Architectural decisions requiring review

### D1 — Three transcript authorities

**Decision:** provisional short-span output, monotonic rolling canonical prefix, terminal final
surface.

**Reason:** one authority cannot simultaneously minimize first-word delay and maximize context.

### D2 — Preserve immutable base commits

`CanonicalCommit.transcript` and its existing prefix chain remain the immutable record of what the
short path originally published. Rolling word correction does not overwrite that field.

**Reason:** audit history, label correction, replay, and current accounting depend on immutable
base commits.

### D3 — Separate word revisions from label revisions

Add `text_revision_version`; retain `label_revision_version`. Do not overload
`CanonicalCommit.revised_transcript`, whose current invariant is “same words, revised labels.”

**Reason:** a word replacement and a speaker relabel have different validation, evidence, and
failure modes.

### D4 — Monotonic rolling prefix, not arbitrary patches

Rolling convergence owns `[0, canonical_through_sample)`. Each accepted revision starts exactly at
the previous frontier and moves it forward. The unrevised short-span suffix remains provisional.

**Reason:** one owner per interval prevents duplicated text, holes, out-of-order corrections, and
oscillating overlaps.

### D5 — Longer witness owns its speaker evidence

The witness's local MOSS speaker segments select their own PCM intervals. WeSpeaker embeds those
owned intervals and maps them to the meeting album. It must never embed the complete mixed-speaker
window or leading context.

**Reason:** prior controlled evidence shows context audio can contaminate speaker embeddings and
collapse voices.

### D6 — Keep 2.5 seconds until rolling text ships green

Do not change the production hard cap in E0–E2. First land rolling correction on the current base.
Only E3 may promote one-second output, and only as provisional.

**Reason:** this separates two risks and preserves a stable speaker anchor while rolling text is
proved.

### D7 — Terminal re-ASR requires a new decision record

ADR-0002's shipped L1 and proposed L2 explicitly never re-run ASR. Rolling and terminal word
correction must be governed by a new ADR or an explicit amendment defining text-finalization
authority. They must not be smuggled into “identity sweep.”

### D8 — Current TBSA remains compatibility evidence, not sole promotion authority

Evaluator v2 runs beside current evaluation until reviewers accept a migration. Existing baseline
reports remain reproducible.

### D9 — Five-phase processing is uncertainty-routed only

Naturally overlapping rolling windows are the first multi-view evidence. Additional VAD/embedding
phases are allowed only for disagreement regions and only after a prototype demonstrates benefit.

### D10 — No production implementation before plan approval

Reviewers must close the questions in §17 and sign the acceptance record in §18. Until then, only
throwaway prototypes and read-only verification are authorized.

---

## 5. Target architecture

```text
                         ┌──────────────────────────┐
mixed PCM ──────────────►│ short endpoint + MOSS    │
      │                  │ 2.5 s now; 1 s candidate│
      │                  └────────────┬─────────────┘
      │                               │ immutable base commits
      │                               ▼
      │                  ┌──────────────────────────┐
      ├─────────────────►│ rolling converger        │
      │ bounded PCM      │ 10–15 s witness          │
      │ history          │ central owned region     │
      │                  └────────────┬─────────────┘
      │                               │ text revision + owned speaker PCM
      │                               ▼
      │                  ┌──────────────────────────┐
      │                  │ transcript authority     │
      │                  │ base + rolling prefix    │
      │                  │ + label projection       │
      │                  └────────────┬─────────────┘
      │                               │ effective transcript
      │                               ▼
      │                            portal/export
      │
      └── retained mixed tape ──► 150/120 terminal windowing ──► final surface
```

### 5.1 Transcript ownership at time T

```text
0                        rolling frontier                 accepted audio
|==============================|-------------------------------|
 rolling canonical authority         provisional base suffix
```

At terminal success:

```text
0                                                             end
|===============================================================|
                         final authority
```

### 5.2 Failure behavior

- Short decode failure: existing bounded live behavior remains authoritative for that span.
- Rolling failure: keep the current base/rolling surface; record the failed window; later windows
  may continue only from the existing monotonic frontier.
- Rolling stale result: refuse without changing the surface.
- Terminal tape incomplete/degraded: do not claim final file quality; export the rolling surface
  with explicit `finalization_status`.
- Terminal model failure: meeting remains successfully captured; finalization reports failure and
  retains the best rolling surface.

These are ordinary reachable failures, not defensive scaffolding.

---

## 6. Module and seam design

The design uses **deep modules**: complex planning, ownership, reconciliation, and validation sit
behind small interfaces. Tests exercise the same interfaces as callers.

### M1 — Live decode outcome repair

**Location:** deepen `moss_transcribe_diarize/app/live_span_bounds.py`; adjust callers in
`vllm_runner.py`, `live_adapters.py`, and `live_coordinator.py`.

**Interface concept:**

```python
classify_live_transcript(
    raw_text: str,
    *,
    sample_count: int,
    freeze_reason: str,
    speech_ratio: float | None,
) -> LiveTranscriptOutcome
```

`LiveTranscriptOutcome` is one of:

- parsed segments;
- salvageable missing-bound timestamp;
- refusal boilerplate;
- genuinely empty;
- unparseable and not safely salvageable.

The implementation owns parsing, bounded timestamp completion, refusal detection, and fixed-point
render validation. Callers must not repeat those rules.

Exact seams for the implementer (verified §3.5 V5):

- The collapse being replaced: `app/vllm_runner.py:274-278` raises `EmptyTranscriptionError`
  for zero tokens / empty text / zero parsed segments, and `app/live_adapters.py:307-311`
  converts it to `transcript=""`. After M1, the zero-parsed-segments case routes through
  `classify_live_transcript` instead of being flattened.
- The segment grammar to complete against: `TRANSCRIPT_SEGMENT` in
  `moss_transcribe_diarize/live_speaker_accuracy.py:22-26`; a salvageable span is one whose raw
  text parses to zero segments solely because the final closing timestamp is absent — complete
  it with the span duration (`sample_count / 16000`), then require parse → render → parse to be
  a fixed point.
- Refusal boilerplate corpus: `prototypes/live-file-gap-emptyspan/out/d3.json` (includes the
  observed digital-silence hallucination `"I'm sorry, I can't assist with that request."`).
- `FrozenSpan` (`app/live_session.py:75`) carries `id/epoch/start_sample/end_sample/reason`
  only — no speech ratio; `freeze_reason` comes from it, and `speech_ratio` (O2, §9.1) must be
  recomputed over the span PCM with `WebRtcSpeechProvider` (`app/live_provider_bundle.py`) if
  O2 is chosen.

**Dependency category:** in-process. No adapter.

### M2 — Rolling transcript converger

**Proposed location:** new `moss_transcribe_diarize/app/live_transcript_convergence.py`.

**Interface concept:**

```python
converger.accept_pcm(start_sample: int, pcm: bytes) -> tuple[RollingDecodeRequest, ...]
converger.observe_base(snapshot: LiveSnapshot) -> tuple[RollingDecodeRequest, ...]
converger.complete(request_id: int, outcome: InferenceTranscript) -> TextRevisionProposal | None
converger.stop(end_sample: int) -> TerminalDecodePlan
```

The implementation hides:

- bounded PCM retention;
- window/stride planning;
- request coalescing and stale-work recognition;
- word ownership and lexical overlap reconciliation;
- monotonic frontier advancement;
- correction latency and work accounting.

The external interface does not expose stitch policies. Those remain internal seams used by the
prototype and focused tests.

After E2 selects window length `W`, each session may retain at most `2 × W` seconds of rolling
PCM in memory: one immutable request payload plus one `W`-second ring for the newest/coalesced
view. The complete terminal tape is separate, explicitly authorized storage. The soak test records
the rolling-buffer high-water mark and fails if this bound is exceeded.

**Dependency category:** in-process logic plus remote-but-owned MOSS inference. Production uses
the existing vLLM runner adapter; tests use cached/in-memory decode adapters. That is a real seam
because both adapters exist.

### M3 — Session transcript authority

**Location:** deepen `moss_transcribe_diarize/app/live_session.py`.

Add one word-revision interface:

```python
LiveSession.apply_text_revision(proposal: TextRevisionProposal) -> TextRevisionOutcome
```

It validates:

- same session epoch;
- proposal starts at the current rolling frontier;
- proposal ends after its start and no later than committed audio;
- absolute segment samples stay within the owned interval;
- segments are ordered and non-overlapping;
- text revision base version is current;
- terminal finalization may replace the full rolling surface only once.

It owns and publishes:

- `text_revision_version`;
- `canonical_through_sample`;
- the current effective transcript surface;
- refusal counts by stable reason;
- `finalization_status`.

`committed` remains the immutable short-path history. `effective_transcript` is what the portal and
export display.

Anchors for the implementer: the label-revision precedent to mirror is
`LiveSession.revise_labels` (`app/live_session.py:539-563` — version bump only when a change is
applied); the published-text precedence rule to extend is `app/live_session.py:581`
(`revised_transcript` wins over `transcript`); the snapshot constructor that must carry the new
fields is at `app/live_session.py:630-646`. Server-side JSON is produced by `dataclasses.asdict`
(`app/live_service_runtime.py:81,230,253`), so adding dataclass fields serializes them
automatically — the hand-written replay reconstructors are the only place field addition can be
silently lost (see A0.1's regression test, which must be extended for every new field here).

### M4 — Rolling speaker resolver

**Proposed location:** internal to `live_transcript_convergence.py` until a second caller exists.

For each witness-local speaker:

1. select only its owned, timestamped PCM intervals;
2. apply the production evidence floor;
3. embed eligible speech with the existing WeSpeaker adapter;
4. reconcile against the current fingerprint album;
5. return stable meeting identity or abstain.

Do not create a new public port merely to make tests convenient. Test this through the converger
interface with the production encoder bench and a scripted test adapter.

### M5 — Inference scheduling

**Location:** deepen `moss_transcribe_diarize/app/live_arbiter.py` and runtime dispatch.

The arbiter today exposes exactly three admission methods — `submit_batch`,
`submit_live_canonical`, `submit_live_provisional` (`app/live_arbiter.py:62,68,81`). Add a
fourth, `submit_live_refinement(*, coalesce_key, payload)`, forming a coalescing
`live_refinement` queue with this per-session priority:

```text
unresolved short canonical work > newest rolling refinement > provisional-only work
```

Only one queued or running rolling witness per session. A newer eligible witness may replace an
older not-started request; it may not cancel a running MOSS request. Scheduler behavior must be
proved under two concurrent sessions before promotion.

### M6 — Terminal finalizer

**Proposed location:** reuse `app/windowed_transcription.py` through a small live adapter inside
`live_transcript_convergence.py`.

Input is the completed retained **mixed** track and its gap manifest. Planning remains 150-second
windows with 120-second stride. The finalizer returns one terminal `TextRevisionProposal`; it does
not mutate the session directly.

### M7 — HTTP/replay and portal adapters

**Locations:**

- `moss_transcribe_diarize/live_service_replay.py`
- `moss_transcribe_diarize/app/live_service_runtime.py`
- `moss_transcribe_diarize/app/live_transport.py`
- `moss_transcribe_diarize/app/live_portal.py`

Adapters serialize and display the authority module's result. They do not implement ownership,
stitching, salvage, or identity rules.

---

## 7. Data contracts

Exact names may change during review, but semantics must not.

### 7.1 Effective transcript segment

```python
@dataclass(frozen=True, slots=True)
class EffectiveTranscriptSegment:
    start_sample: int
    end_sample: int
    text: str
    canonical_speaker: str | None
    authority: Literal["provisional", "rolling", "final"]
```

Sample integers are authoritative; seconds are presentation values. `canonical_speaker=None`
renders as `S00`.

### 7.2 Text revision proposal

```python
@dataclass(frozen=True, slots=True)
class TextRevisionProposal:
    epoch: int
    base_text_revision_version: int
    source: Literal["rolling", "terminal"]
    start_sample: int
    end_sample: int
    segments: tuple[EffectiveTranscriptSegment, ...]
    decode_elapsed_sec: float | None
```

No new hash is added. Monotonic version, epoch, and exact owned sample interval determine whether
the proposal changes state.

### 7.3 Snapshot additions

```text
session.text_revision_version
session.canonical_through_sample
session.effective_transcript[]
session.finalization_status = not_started | running | final | failed | unavailable
```

Existing `committed`, `committed_prefix_hash`, and `label_revision_version` retain their meanings.
`revised_transcript` remains label-only until reviewers approve replacing the old surface entirely.

### 7.4 Events

Add events containing counts/timing, not transcript text:

- `decode_salvaged`
- `rolling_decode_queued`
- `rolling_decode_completed`
- `text_revision_applied`
- `text_revision_refused`
- `terminal_finalization_started`
- `terminal_finalization_completed`
- `terminal_finalization_failed`

Every completion event records window samples, owned samples, queue delay, decode elapsed time,
generated tokens, cap status, and inference RTF when trustworthy.

---

## 8. Phase E0 — measurement integrity

### A0.1 Repair replay reconstruction

Files:

- `moss_transcribe_diarize/live_service_replay.py`
- `tests/test_live_service_replay.py`

Change `_live_snapshot_from_dict` (`live_service_replay.py:891-909`) to read
`label_revision_version` (default 0 for old payloads) and `_commit_from_dict` (`:920-928`) to
read `revised_transcript` (default `None`). Add a raw server JSON → client object → JSON
round-trip covering both non-default fields — and make it **field-complete by construction**:
the test builds the server payload with `dataclasses.asdict` over fully non-default
`LiveSnapshot`/`CanonicalCommit` instances and asserts the round-trip is lossless, so any future
dataclass field silently dropped by the hand-written reconstructors fails the test without
editing it.

Gate: `verify_replay_roundtrip.py` changes from intentional exit 1 to exit 0; targeted runtime and
HTTP tests pass (`tests/test_live_service_replay.py`).

Then re-acquire the tainted replay corpus (the exact baseline drivers are checked in):

```bash
# paired 60-second trio + secondaries (~10 min, deployed stack must be up)
.venv/bin/python prototypes/live-file-gap-baseline-20260824/remeasure_live_vs_file.py \
  /tmp/moss-baseline-rerun-$(date +%Y%m%dT%H%M%S)
# paired 5-minute case (~6 min)
.venv/bin/python prototypes/live-file-gap-baseline-20260824/remeasure_5m_case.py \
  /tmp/moss-baseline5m-rerun-$(date +%Y%m%dT%H%M%S)
```

Both scripts fail fast if the backend (`https://127.0.0.1:7861`) or tunnel is down; see
Appendix A for the stack runbook. Run each driver twice under the same quiet-GPU provenance. For
the trio, file and live transcript hashes and metrics must match exactly between the two fresh
runs; the file arm must also match the checked-in baseline. If a fresh live arm differs from the
checked-in baseline, record the exact transcript/metric delta and stop to explain the changed
service or decoder provenance — do not call an unbounded difference "run noise." The re-acquired
5-minute terminal snapshot must show the revisions its `identity_finalized` event reports.

### A0.2 Preserve raw decode disposition

The current runner converts non-empty unparseable MOSS text into `""` (`app/vllm_runner.py:278`
raises on zero parsed segments; `app/live_adapters.py:307-311` catches and flattens), making the
trace claim the decoder returned no transcript; the honest label
(`decoder_returned_unparseable_transcript`) already exists in `app/live_coordinator.py` but is
unreachable. Preserve a typed disposition and generated-token facts through the coordinator so
the trace distinguishes truly-empty from unparseable from refused. Do not log raw words in
service events.

### A0.3 Prototype evaluator v2

Extend the standing bench, not production evaluation first:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_evaluators.py \
  --manifest prototypes/streaming-diarization/data/real/benchmark_diarization_1min/manifest.json \
  --output /tmp/moss-live-evaluator-v2.json
```

This command is **proposed and does not exist yet**.

Evaluator v2 must report:

- WER with insertion/deletion/substitution counts;
- content recall;
- WER by distance to short-span seams;
- lexically aligned matched-word speaker accuracy;
- DER on real reference speech regions;
- current TBSA/DER beside, not replacing, the new metrics.

Prototype gates:

- self-score exactly 1.0 on every axis;
- `"xx"` over 60 seconds receives zero lexical coverage and zero matched-word speaker credit;
- score invariant to splitting one hypothesis segment into adjacent same-speaker segments;
- live/file conclusions remain reproducible from saved hypotheses.

### E0 exit

Re-acquire the paired trio and secondary identity case after A0.1/A0.2. Reviewers verify
denominators and terminal revisions before E1 begins.

---

## 9. Phase E1 — bounded malformed-output salvage

### 9.1 Prototype question

Can safely supplying absent boundary timestamps recover speech without publishing silence
hallucinations?

The existing prototype measured VAD-gated salvage. One unresolved implementation choice remains:
the endpoint computes speech decisions but `FrozenSpan` does not retain aggregate speech ratio.
Before production, compare:

- **O1:** hard-cap span + safe grammar + non-refusal text;
- **O2:** safe grammar + recomputed WebRTC VAD speech ratio `>= 0.5` + non-refusal text.

Prefer O1 if it matches O2 on the full corpus because it needs no new state and directly targets
the observed hard-cap failure shape.

### 9.2 Prototype gate

Run all 184 saved spans (`prototypes/live-file-gap-emptyspan/spans/*.wav` plus the simulator
spans its `run_all.sh` reproduces; disposition table in `out/d3.json`) plus constructed
two-speaker hard-cap spans. Report every accepted and refused salvage with reason.

- no case-level WER regression;
- no refusal boilerplate published;
- no new words published on digital silence;
- parse → render → parse fixed point;
- speaker identity preparation receives only intervals the salvager actually emitted;
- zero extra MOSS requests.

### 9.3 Production change

Implement M1, update typed telemetry, and add table-driven tests from
`prototypes/live-file-gap-emptyspan/out/d3.json`.

### E1 exit

Paired live/file rerun proves expected WER movement and no file-mode change. If salvage is neutral
on the expanded corpus, keep the honest typed disposition and reject the salvage policy.

---

## 10. Phase E2 — rolling text convergence on the 2.5-second base

### 10.1 Prototype question

Which window/stride and truth-blind stitch policy preserve the rolling gain with the fewest joins
and least GPU work?

### 10.2 Required grid

| Window | Stride | Purpose |
|---:|---:|---|
| 10 s | 5 s | measured quality reference |
| 10 s | 10 s | half the witness audio work; fewer joins |
| 15 s | 7.5 s | more context with 2× overlap |
| 15 s | 10 s | proposed quality/cost compromise |

Stitch policies:

- character-proportional central ownership;
- uniform token-time central ownership;
- lexical overlap alignment with central ownership — **the reference candidate**: it is the
  best-known measured stitcher (trio WER `.1289` at 10/5 vs `.146` for time-proportional
  ownership on the same windows), and its working implementation is
  `prototypes/live-file-gap-context/proto_context_arms.py` (arm `a2`). The grid still runs all
  three because the cheaper strides may rank them differently at fewer joins.

The reconciler sees no reference. Truth enters only after the complete transcript is produced.

### 10.3 One proposed command

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_rolling_grid.py \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \
  --windows 10/5,10/10,15/7.5,15/10 \
  --stitches char,uniform,lexical \
  --runs 3 \
  --output /tmp/moss-rolling-grid.json
```

This command is **proposed and does not exist yet**.

It must print every decode window, ownership region, selected/dropped word, duplicate check,
latency, decoded-audio work, rolling-PCM high-water mark, endpoint counter delta, and final metric.

### 10.4 Selection rule

Choose the least expensive arm passing G1–G3 and all per-case gates. Do not select by TBSA alone.
If no arm passes, do not implement rolling production code.

### 10.5 Production sequence

1. Implement M2 with bounded PCM history and cached test adapter.
2. Implement M3 word-revision authority.
3. Add `live_refinement` scheduling in M5.
4. Wire current 2.5-second base commits into the converger.
5. Add snapshot/event serialization.
6. Update portal to render `effective_transcript` as one replacement surface.
7. Keep exports on current commits until terminal/effective export tests pass, then switch export
   once in the same reviewed change.

### 10.6 Resource gate

Stress one and two concurrent sessions with real-time PCM pacing. Measure:

- base first-publication p50/p95;
- rolling correction p50/p95;
- per-kind queue delay;
- base, witness, and combined GPU RTF;
- stale/coalesced refinement count;
- endpoint running/waiting requests;
- snapshot bytes and portal render time.

Rolling must never build an unbounded queue or delay unresolved short canonical work.

### E2 exit

Rolling text passes G1–G3, G6–G7, browser overwrite E2E, 30-minute soak, and exact accounting.
Only then may E3 test a shorter preview cap.

---

## 11. Phase E3 — rolling speaker authority and optional one-second preview

### 11.1 Speaker-authority prototype

Run the same rolling witness three ways:

- **S0:** current prototype — map through short-base identity anchors;
- **S1:** embed witness-owned speaker intervals and reconcile against the existing album;
- **S2:** S1 plus label-invariant disagreement routing between overlapping witnesses.

Never send prefix/context PCM into a speaker embedding. Cache an embedding only when its exact
sample interval and channel content are unchanged; changed witness segmentation means new
evidence. The prototype decodes every MOSS witness once and reuses that joint output and retained
PCM across S0–S2; only speaker intervals whose segmentation changed require new WeSpeaker work.

One proposed command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_speaker_authority.py \
  --manifest prototypes/streaming-diarization/data/real/benchmark_diarization_1min/manifest.json \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \
  --bases 2.5,1.0 --strategies s0,s1,s2 --runs 3 \
  --output /tmp/moss-speaker-authority.json
```

This command is **proposed and does not exist yet**. It must use the production MOSS runner,
production WebRTC VAD, and production WeSpeaker encoder; print every witness-owned sample
interval, cache hit/miss, label-invariant mapping, abstention, processing time, and per-resource
RTF; and keep reference truth outside reconciliation.

### 11.2 Gates

- G4 passes on the primary trio;
- 9-clip `tests/live_identity_accuracy.py` floor remains green;
- no speaker collapse on two-speaker mixed-window cases;
- every local speaker maps one-to-one or abstains;
- S00 duration does not increase;
- under the G7 two-session pacing contract, base + rolling MOSS + WeSpeaker processing RTF stays
  `< 1`, G5/G6 remain green, and refinement queue bounds remain intact.

### 11.3 One-second preview decision

Only after S1/S2 passes:

1. repeat the full rolling grid with 1.0-second preview;
2. measure first publication and correction under two concurrent sessions;
3. prove rolling final text is independent of provisional segmentation;
4. prove rolling speaker output meets G4;
5. update the endpoint cap only for the provisional path.

If speaker quality fails, retain 2.5 seconds. The rolling text architecture remains useful and no
fallback framework is added.

### 11.4 Microfragment identity work

Causal adoption of sub-evidence-floor S00 fragments from a nearby labelled neighbor is a separate
small candidate. It may proceed only after replay reconstruction is fixed and the 9-clip identity
bench shows no regression. Do not lower the sweep margin based on the current single-correction
example.

### E3 exit

The product owner chooses one of two measured surfaces:

- 2.5-second provisional + rolling canonical; or
- 1.0-second provisional + rolling canonical.

The choice is based on measured latency/quality, not architecture preference.

---

## 12. Phase E4 — terminal file-quality convergence

### 12.1 Preconditions

- New text-finalization ADR accepted.
- Retained mixed tape is complete and readable for the session.
- Tape capture correctness gates remain green.
- E2 rolling surface is already production-correct; terminal is an improvement, not the only
  usable transcript.

### 12.2 Prototype matrix

| Duration | Sessions | Required measurement |
|---:|---:|---|
| 1 min | 1 | reproduce existing file equality |
| 5 min | 1 | multiple 150/120 planning behavior |
| 30 min | 1 | linear finalization cost and memory |
| 30 min | 2 | queueing and resource contention |
| 60 min | 1 | long-session snapshot/export/browser behavior |

One proposed command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_terminal_matrix.py \
  --output /tmp/moss-terminal-matrix.json
```

This command is **proposed and does not exist yet**. Its checked-in defaults implement the table
without hidden scratch inputs: 1 minute uses the primary trio; 5 minutes uses
`benchmark_5m/lex_keyu_jin`; 30-minute single-session uses `benchmark_30m/lex_bill_ackman`;
30-minute concurrency runs that case beside `benchmark_30m/acquired_jamie_dimon` in one
orchestration process; and the 60-minute transport fixture concatenates those two 30-minute WAVs
in temporary storage, recording both input paths, durations, and the join sample. The acquired
concurrency arm and derived 60-minute fixture are for resource, accounting,
snapshot/export/browser, and latency evidence only—never lexical promotion denominators. The
harness runs paired terminal/file calls with identical audio bytes and prints window ownership,
queue/counter deltas, cold/warm latency, per-component and combined RTF, memory, snapshot bytes,
and finalization state transitions.

Report cold and warm model readiness separately. Terminal quality is scored against paired file
mode using identical audio bytes, model, prompt, decoding parameters, and evaluator.

### 12.3 Terminal behavior

1. Stop capture and drain short/rolling work.
2. Seal and verify tape accounting.
3. Set `finalization_status=running`; retain the rolling transcript as readable.
4. Run existing 150/120 `WindowedRunner` over the mixed tape.
5. Resolve terminal speaker identities using owned speech evidence.
6. Apply one terminal text revision covering `[0, meeting_end)`.
7. Set `finalization_status=final` and export the effective surface.

The stop HTTP request should not be forced to wait for long terminal finalization. Reviewers must
approve either asynchronous finalization with polling or a separately invoked `finalize` action.
Recommendation: asynchronous finalization with the existing snapshot polling model.

### E4 exit

G8–G10 pass on the duration/concurrency matrix. Terminal failures preserve and export the rolling
surface with an explicit non-final status.

---

## 13. Optional phase — uncertainty-routed multi-view

Five full VAD/speaker views are not a baseline feature. LiveTranscribe provides two relevant but
distinct precedents (§3.5 V4):

1. **RLO, a dual-ASR display overlay.** A chunked candidate and whole-file witness decode the same
   retained audio. Five matched display-off/on pairs reported mean/median WER deltas
   `-0.0170/+0.0170`, TBSA deltas `+0.0027/-0.0016`, and exact-word p95 latency regressions
   `+17.1%/+11.3%`, with every run below six seconds. This supports asynchronous witness
   correction, but it is display-only evidence from a different ASR stack, not a MOSS quality
   guarantee.
2. **OSF, five phase-shifted VAD/speaker views.** The Jamie experiment refuted the broad claim we
   would need for a blanket port: all 20 live views merged the handoff, and phase-VAD disagreement
   did not identify the assignment instability. Five views cannot recover a boundary the live VAD
   representation never expresses.

The transferable principle is therefore **multiple views as an uncertainty signal**, not five
always-on passes. This repo's overlapping rolling MOSS witnesses already provide independently
timed views of the same audio as paid work. The E3 S2 prototype should compare them
label-invariantly, route only measured disagreements to extra work, and reject this optional phase
unless that routing adds speaker quality economically.

After E3, use already-paid overlapping witnesses as views:

1. compare overlapping speaker allocations label-invariantly;
2. treat only exact unanimity among the available paid views as stable enough to skip extra work;
3. mark every disagreement, including a plurality or 4-of-5 near-consensus, as uncertainty—the
   LiveTranscribe perturbation found its 4-of-5 mode wrong in 2/2 observed cases, so no voting rule
   is authorized here;
4. run at most two additional phase views only for uncertain regions;
5. batch embeddings for throughput, without claiming compute was eliminated.

One proposed command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_uncertainty_views.py \
  --manifest prototypes/streaming-diarization/data/real/benchmark_diarization_1min/manifest.json \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \
  --policies none,targeted2,blanket5 --runs 3 \
  --output /tmp/moss-uncertainty-views.json
```

This command is **proposed and does not exist yet**. It reuses the E3 witness decodes and
unchanged interval embeddings, prints every uncertainty decision and added view, and reports
speaker quality, request count, embedded-audio seconds, wall time, and RTF for each policy.

Prototype gate: within the same prototype, run a blanket-extra-views arm as the comparison
ceiling; targeted (uncertainty-routed) views must match or beat that blanket arm's speaker quality,
use no more than two extra views for any routed region, and consume `<= 40%` of the blanket arm's
added embedding requests and embedded-audio seconds. Otherwise reject this phase.

---

## 14. Test and certification plan

### T1 — Pure/module-interface tests

- malformed-output disposition table;
- timestamp completion and refusal filtering;
- rolling window planning;
- exactly-one ownership for every canonical-prefix sample;
- lexical stitch duplicate/deletion cases;
- monotonic text revision acceptance/refusal;
- label revisions projected over rolling segments;
- terminal full replacement;
- bounded PCM retention and release.

Tests assert module outcomes through interfaces, not internal stitch state.

### T2 — Runtime seams

- real coordinator + scripted MOSS adapter;
- real runtime stop ordering;
- arbiter canonical/refinement priority and coalescing;
- rolling failure leaves current surface unchanged;
- stale result refuses without version movement;
- terminal tape degradation remains non-terminal to capture.

### T3 — HTTP/replay/portal

- raw JSON round-trip preserves base, label revisions, text revisions, and finalization status;
- portal replaces the canonical prefix without duplicate rows;
- reconnect reconstructs the same effective surface;
- terminal polling stops only after final/failed/unavailable;
- export text equals visible effective text.

### T4 — Real quality bench

- primary 3 × 60-second corpus;
- 5-minute Lex case;
- existing 9-clip identity bench;
- at least one rapid speaker-handoff case;
- at least one background-audio/microphone mixture;
- file-mode paired controls.

### T5 — Performance and soak

- warm one/two concurrent sessions;
- cold model readiness reported separately;
- 30-minute live pacing soak;
- 60-minute terminal finalization;
- snapshot bytes, JSON serialization, portal DOM/render time, process memory, GPU RTF, and queue
  depth over time.

If snapshot/DOM cost grows unacceptably, measure and design incremental transcript delivery in a
new prototype. Do not preemptively add paging or compatibility machinery.

### T6 — Release evidence bundle

Each phase produces:

- exact revision and environment;
- exact command;
- corpus denominator;
- per-case and aggregate metrics;
- first-publication/correction/finalization latency;
- GPU counters and RTF;
- queue/accounting evidence;
- browser screenshot or trace for visible correction;
- verdict: PASS, FAIL, or unmeasured.

---

## 15. Risks, countermeasures, and stop conditions

| Code | Risk | Level | Countermeasure / stop condition |
|---|---|---|---|
| R1 | stitch duplicates or deletes words | High | truth-blind grid; exactly-one ownership invariant; stop if G1–G3 fail |
| R2 | context contaminates speaker embedding | High | embed owned speaker PCM only; mixed-window collapse gate |
| R3 | word and label revisions conflict | High | separate versions; one session authority module; interface-level tests |
| R4 | rolling work delays first publication | High | canonical priority, one coalesced refinement/session, two-session stress gate |
| R5 | incomplete tape falsely claims final quality | High | explicit finalization status; tape accounting precondition |
| R6 | TBSA rewards timestamp inflation | High | lexical evaluator v2; WER/content gates; reject padding |
| R7 | salvage publishes silence hallucination | Medium | hard-cap/VAD + refusal prototype; no-silence gate |
| R8 | one-second identity remains weak | High | witness-owned speaker prototype; retain 2.5 seconds if gate fails |
| R9 | long-session snapshot/browser cost grows | Medium | 30/60-minute measurement; design only if measured red |
| R10 | new text re-ASR violates accepted ADR | High | new ADR/amendment required before E2 production work |

Global stop conditions:

- reference/corpus provenance is ambiguous;
- scorer self-test or degenerate controls fail;
- prototype reads truth during reconciliation;
- any promoted rolling/final authority regresses case-level WER without an explicitly accepted
  user trade-off; the one-second provisional preview may be worse only if G5 and the corrected
  rolling gates pass and the product owner accepts that temporary-quality trade-off;
- file mode changes unexpectedly;
- accepted/accounted equality fails;
- two concurrent sessions cannot sustain real time;
- terminal finalization depends on unavailable audio.

---

## 16. Explicit non-goals and rejected approaches

- No new ASR model or separate language-model lane.
- No transcript-tail prompt injection; measured WER regressed to `.244` with prompt echo.
- No per-seam five-second re-ASR; measured WER worsened.
- No timestamp padding to improve TBSA.
- No one-second canonical authority before E3 gates.
- No blanket five-phase computation.
- No lower identity sweep cadence. Scope of the evidence (corrected, §3.3): on the 60-second
  trio, cadence 60→20 s proposed zero corrections; at 300 s the deployed 60-second cadence
  already fires and applied two label revisions (`identity_revision_version: 2`), so cadence is
  not the bottleneck at any measured duration.
- No embedding from complete witness/context audio.
- No unbounded retained PCM in memory.
- No reprocessing from meeting inception after every update.
- No feature-flag, compatibility, migration, or retry framework beyond behavior required by the
  deployed live session and review-approved rollout.
- No security expansion; cooperating local operator remains the threat model.

---

## 17. Review questions that must be closed

| Code | Question | Recommendation |
|---|---|---|
| Q1 | Approve provisional → rolling → final authority? | Yes |
| Q2 | Approve immutable base commits plus separate effective surface? | Yes |
| Q3 | Approve separate `text_revision_version` and `label_revision_version`? | Yes |
| Q4 | Initial rolling window/stride and stitch policy? | Prototype 10/10 and 15/10 against measured 10/5, with the lexical stitcher (§10.2) as the reference arm |
| Q5 | Keep 2.5-second base through E2? | Yes |
| Q6 | Permit one-second output only after witness-owned speaker gate? | Yes |
| Q7 | Approve evaluator v2 beside current TBSA? | Yes |
| Q8 | Approve new text-finalization ADR/amendment? | Required before E2 implementation |
| Q9 | Terminal finalization lifecycle? | Asynchronous, snapshot-polled |
| Q10 | Is complete mixed-tape retention authorized for terminal finalization? | Must be explicitly decided |

Any rejected recommendation returns the plan for revision before implementation.

---

## 18. Review acceptance record

Implementation remains blocked until this section is completed by reviewers/owner.

```text
Evidence reproduction reviewed by: ____________________  date: __________
Architecture/module design reviewed by: ______________  date: __________
Evaluator/gates reviewed by: __________________________  date: __________
Resource/latency plan reviewed by: ____________________  date: __________
ADR change accepted: YES / NO                           date: __________
Tape-retention authority accepted: YES / NO             date: __________
Implementation authorized by: _________________________  date: __________
Authorized first phase: E0 / other: ___________________
```

Until the final line is signed, this document authorizes review and throwaway prototype work only.
That initial authorization permits only its named first phase. Every later phase requires a
completed row below after its predecessor and prototype gate pass.

### Campaign annotation — 2026-08-25 (unattended run, branch `ralph/live-convergence-0824`)

Appendix B §18 pre-authorized every phase below **conditionally**: a phase is authorized
provided its rescoped gates pass mechanically with evidence written, and morning review signs
the rows retroactively before any merge off the campaign branch. The campaign ran E0–E4 under
that authorization. **Every row below is therefore UNSIGNED, and so is the block above it** —
the gates are scored and the evidence is written; the signatures are morning review's to give.

Each row's clock is the commit date, in UTC, of the `gates.json` it cites; each tally and each
unsigned gate name is recomputed from that same file. Both are checked by
`prototypes/streaming-diarization/live-convergence/verify_plan_record.py`, which also fails if
any row acquires a signature. The reader's long form is
`evidence/live-convergence-0824/CAMPAIGN_REPORT.md`.

| Phase | Prototype/evidence bundle reviewed | Reviewer / date | Owner authorization | Status |
|---|---|---|---|---|
| E0 | `evidence/live-convergence-0824/M0d-paired-reacquisition/` | unsigned — morning review | Appendix B §18 (conditional) | gates passed 2026-08-25T05:21:46Z (4 of 5; `G2_live_transcript_reproducible` unsigned), awaiting morning sign-off |
| E1 | `evidence/live-convergence-0824/M1-e1-exit/` | unsigned — morning review | Appendix B §18 (conditional) | gates passed 2026-08-25T06:40:03Z (5 of 6; `G_M1_1_trio_live_wer_bound` unsigned), awaiting morning sign-off |
| E2 | `evidence/live-convergence-0824/M2-e2-exit/` | unsigned — morning review | Appendix B §18 (conditional) | gates passed 2026-08-25T10:24:53Z (7 of 8; `G_M2_4_correction_p95` unsigned), awaiting morning sign-off |
| E3 | `evidence/live-convergence-0824/M3-disposition/` | unsigned — morning review | Appendix B §18 (conditional) | gates passed 2026-08-25T11:24:13Z (14 of 14; none unsigned), awaiting morning sign-off |
| E4 | `evidence/live-convergence-0824/M4-e4-exit-2/` | unsigned — morning review | Appendix B §18 (conditional) | gates passed 2026-08-25T16:08:09Z (12 of 14; `G-M4-3` unsigned; `G-M4-4` unsigned), awaiting morning sign-off |
| Optional multi-view | — (not run) | — | not authorized — Appendix B §B.3 puts §13 out of campaign scope | Blocked |

Four rulings close the five unsigned gates; none is a code change, and each has its disposition
written in its own bundle. E0's `G2` asked two fresh live runs of the same audio to be
hash-identical and the five-minute case is not, because the deployed decoder is not
bit-reproducible at that length. E1's `G_M1_1` missed `.190` by `.0023`, attributable to one
decode flip that entered the instrument before E1 was written. E2's `G_M2_4` wanted a `6.0` s
correction p95 and no geometry in the preregistered grid can reach it — the bound needs
`L + S <= 12` and the grid's floors are `6.46` / `8.51` / `11.64` / `12.81` s. E4's `G-M4-3` and
`G-M4-4` are gates the campaign added to itself (terminal no worse than the rolling surface it
replaces); on `lex_adam_frank` alone, converging to the paired file arm costs `.003766` of word
error against rolling, which is the trade the owner ruled before the numbers existed.

**Two findings outlive these rows and belong to whatever campaign follows.** First, the
remaining speaker error decomposes as **63 % segments that straddle a reference turn** — an
extent question owned by the text geometry, not by identity — and **27 % sub-0.5-second
microfragments** below the evidence floor; a successor should start from that split rather than
from the confusion total. Second, **the deployed diarization metric pays a bonus for publishing
the same audio twice**: `evaluation.calculate_diarization` sums the overlap of every
(reference, hypothesis) pair, so reference seconds two hypothesis segments both claim are
credited twice and that much real `miss` disappears (`lex_adam_frank` file arm: `.053222`
becomes `.066222` once the duplication is resolved, all of it `miss`). That is §3.4's extent
artifact in a new shape — duplication rather than padding — and evaluator v2, which unions
hypothesis intervals first, does not move.

---

## 19. Proposed implementation order after authorization

```text
Review acceptance
    ↓
E0 replay + evaluator truth
    ↓
E1 bounded malformed-output salvage
    ↓
rolling grid prototype ──FAIL──► stop/revise design
    │ PASS
    ▼
E2 rolling text on 2.5 s base
    ↓
witness-owned speaker prototype ──FAIL──► retain 2.5 s base
    │ PASS
    ▼
E3 optional 1 s provisional
    ↓
terminal duration/concurrency prototype ──FAIL──► keep rolling export
    │ PASS
    ▼
E4 terminal file-quality convergence
    ↓
optional uncertainty-routed multi-view
```

Each production phase is a separately reviewable change with its own measured acceptance bundle.
No phase may borrow a later phase's expected benefit to pass its gate.

---

## Appendix A. Implementation reference (added 2026-08-24 second pass)

Everything in this appendix was verified against the working tree at `d910a06`. Line numbers
drift with edits — treat them as starting points and re-grep the named symbol.

### A.1 Deployed dev stack runbook

The measurement stack lives in tmux session `moss-dev-runtime` on MacStudio:

| Piece | What/where |
|---|---|
| Backend + frontend | `python -m moss_transcribe_diarize.app.web_cli --backend vllm --live ...` serving `https://127.0.0.1:7861` (self-signed TLS; also reachable as `https://macstudio.tailnet.aisight.us:7861`) |
| Model transport | SSH tunnel `127.0.0.1:18000 → gyauo@ga0-alienware-rtx4070ti…:127.0.0.1:8000` (`scripts/moss-vllm-tunnel.sh`) |
| Model server | vLLM `moss-vllm.service` (WSL Ubuntu on the 4070 Ti), model `OpenMOSS-Team/MOSS-Transcribe-Diarize`, `max_model_len` 16384 |
| Auth for `/api/**` | `Authorization: Bearer $(cat ~/.local/share/moss-transcribe-diarize/g3/shared-token)`; the live replay CLI takes `--bearer-token-file` with the same path |
| Bring-up reference | `scripts/g3-attended-session.sh` (full `web_cli` invocation), `ops/start-vllm.sh`, `ops/start-web.sh` |

Sanity checks before any measurement:

```bash
curl -s  http://127.0.0.1:18000/v1/models | head -c 200        # model reachable through tunnel
curl -sk https://127.0.0.1:7861/api/runtime | head -c 400       # deployed descriptor
```

Measurement rules: one in-flight vLLM request per harness (the GPU serializes; accuracy under
greedy decoding is deterministic and contention-immune, wall-clock is not); label any timing
collected while anything else uses the GPU as *contended*; certification timing (G5–G8) runs on
a quiet GPU. Do not create live sessions from two independent harness processes at once. The G7
and E4 concurrency benches are the deliberate exception: one orchestration process owns both
sessions and records their shared endpoint counters.

### A.2 Code map

| Concern | Where |
|---|---|
| Live span policy (2.5 s hard cap, 0.5 s silence, 0.1 s min speech) | `app/live_endpoint.py` (`EndpointPolicy`, `EndpointSpan`); VAD `app/live_provider_bundle.py` (`WebRtcSpeechProvider`, webrtcvad mode 1) |
| Per-span decode + token cap 68+ceil(86.4·s) | `app/live_adapters.py` (`RunnerBoundedWavInference`, `canonical_decode_token_cap`); empty-collapse `:307-311` |
| vLLM request + strict response validation | `app/vllm_runner.py` (`VllmRunner.transcribe`; `EmptyTranscriptionError` raises `:274-278`) |
| Session state, commits, revisions | `app/live_session.py` (`FrozenSpan:75`, `CanonicalCommit` ~`:163` with the "same words, revised labels" `revised_transcript` invariant, `UNATTRIBUTED_SPEAKER="S00":21`, `revise_labels:539-563`, published-text rule `:581`, snapshot `:630-646`) |
| Coordinator (decode → identity → commit) | `app/live_coordinator.py` (`_empty_transcript_reason:698`, unreachable honest label `:711`) |
| Identity album + sweep | `app/live_identity.py`, `app/live_identity_album.py` (score .35 / margin .10 / floor 0.5 s), `app/live_identity_sweep.py` (`SWEEP_INTERVAL_SECONDS=60`) |
| Inference scheduling | `app/live_arbiter.py` (`InferenceArbiter.submit_batch:62`, `submit_live_canonical:68`, `submit_live_provisional:81`) |
| Runtime bounds + HTTP | `app/live_service_runtime.py` (descriptor bounds incl. `hard_cap_samples=40000`; `asdict` serialization `:81,230,253`), `app/live_transport.py` (`/api/live/**` routes), `app/live_portal.py` (reader UI) |
| Replay client (E0 target) | `live_service_replay.py` (`_live_snapshot_from_dict:891`, `_commit_from_dict:920`, terminal-trace write `:488`) |
| File mode | `app/windowed_transcription.py` (150/120 `plan_windows`), `app/server.py` (`/api/jobs`), `app/jobs.py` |
| Scorers | `moss_transcribe_diarize/evaluation.py` (`calculate_tbsa`, `calculate_diarization`), `moss_transcribe_diarize/live_speaker_accuracy.py` (`TRANSCRIPT_SEGMENT:22`, `hypothesis_from_live_snapshot`, `score_live_speaker_accuracy`), `moss_transcribe_diarize/transcript_parser.py` |

### A.3 Corpora and baselines

| Corpus | Path | Valid for |
|---|---|---|
| Primary trio (60 s, fully referenced) | `prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples/{lex_bill_ackman,lex_javier_milei,lex_keyu_jin}/` | all lexical + speaker metrics |
| `acquired_*` 60 s samples | same directory | **identity diagnostics only** — references are partial (empty-text rows, 12–31 s coverage); metrics may be printed as explicitly partial diagnostics but never aggregated with the primary trio or used for promotion |
| 5-minute tier | `prototypes/streaming-diarization/data/real/benchmark_5m/` | duration behavior; `lex_keyu_jin` is the measured paired case |
| 3-minute / 30-minute tiers | `.../calibration_diarization_3min/`, `.../benchmark_30m/` | E4 duration matrix; the 60-minute transport fixture is a temporary concatenation defined in §12.2, not a quality corpus |
| Paired deployed baseline (2026-08-24) | `prototypes/live-file-gap-baseline-20260824/` (`trio-60s/results.json`, `keyu-5m/results.json`, drivers, traces) | the numbers every gate in this plan is written against |

Reference caveat (§3.4): references are coarse gapless turn intervals; WER and content recall
are the honest cross-arm metrics until evaluator v2 lands.

### A.4 Existing evidence benches (one command each)

```bash
# E0 defect reproducer (exit 1 until fixed)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python prototypes/live-file-roadmap-verification/verify_replay_roundtrip.py
# 1.0 s vs 2.5 s isolated-span spot check (independent implementation)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python prototypes/live-file-roadmap-verification/spotcheck_1s_vs_25s_spans.py
# Rolling/seam/terminal arms, lexical stitcher (source of the .1289 number)
.venv/bin/python prototypes/live-file-gap-context/proto_context_arms.py \
  --baseline prototypes/live-file-gap-baseline-20260824/trio-60s \
  --output /tmp/moss-context-arms-rerun.json
# Salvage forensics + policy table (~4 min)
bash prototypes/live-file-gap-emptyspan/run_all.sh
# Identity levers (no GPU decodes)
.venv/bin/python prototypes/live-file-gap-identity/proto_identity_levers.py
# Multiview lanes incl. 1 s base and terminal (source of the .146/.377 numbers)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-multiview-prototype/compare_live_multiview.py \
  --output /tmp/moss-live-multiview-rerun.json
```

### A.5 Definition of done, per phase

A phase is done when: its prototype gate table is green in a fresh run on a quiet GPU; its
production change ships with the tests named in §14 for that phase; the paired trio (and, from
E2 on, the 5-minute case) is re-acquired with the checked-in drivers and diffed against
`prototypes/live-file-gap-baseline-20260824/`; the evidence bundle of §T6 is written under
`evidence/`; and the phase's row in §18 is signed. File-mode outputs must be byte-identical
before and after every phase (greedy determinism makes this a hard check, gate G9).

---

## Appendix B. Owner execution decisions — 2026-08-24 night (authoritative overrides)

The owner reviewed this plan after the cross-review session completed and made the following
decisions. **Where this appendix conflicts with a section above, this appendix wins.** The
execution vehicle is a single autonomous Ralph AFK campaign
(`scripts/ralph-live-convergence/`, branch `ralph/live-convergence-0824`) running unattended
during sleep hours; its `prd.md` encodes these decisions as the acceptance ladder.

### B.1 Mission focus

The primary goal is a **breakthrough in live-mode quality on real audio against golden
transcripts**: WER, TBSA, content recall, DER, and speaker accuracy, converging toward paired
file mode. Latency/browser/scale certification beyond what quality work needs is deferred.

### B.2 Decisions (supersede the open questions)

| Ref | Decision |
|---|---|
| Q1–Q3, Q5, Q7, Q9 | **Accepted as recommended** |
| Q4 | Grid runs as specified; lexical stitcher is the reference arm |
| Q6 / §11.3 / E3 exit | **One-second preview is deleted from scope.** The hard cap stays 2.5 s and must be a named parameter (it already flows from `bounds_config`/descriptor); switching to 1.0 s later is a new calibration campaign re-running the E3 gates, not a config flip |
| Q8 | **The text-finalization ADR is accepted now.** The campaign's first E2 step writes `docs/adr/` content from D1–D7 verbatim; no further approval needed |
| Q10 | **Tape retention decided:** retain the complete mixed session tape (memory or disk) for the session's lifetime and delete it after terminal finalization evidence is written. At the ≤5-minute session cap this is ≤ ~10 MB PCM; no TTL or retention framework is warranted |
| §18 | **Conditional pre-authorization of all phases** for this campaign: each phase is authorized provided its (rescoped) gates pass mechanically on a quiet GPU with evidence written. Any hard gate failure stops the campaign and leaves that row unsigned. Morning review signs rows retroactively before any merge off the campaign branch |

### B.3 Scope overrides

| Plan clause | Override |
|---|---|
| All corpora | **No test audio may exceed 5 minutes.** Allowed: the 1-minute trio, `calibration_diarization_3min/lex_adam_frank`, `benchmark_5m/lex_keyu_jin` (plus other fully-referenced ≤5-min cases if needed). The 30/60-minute matrix (§12.2 rows 3–5) is deferred to a later campaign |
| G4 | **Rescoped** (recorded 2026-08-25 pre-M1: deleting the one-second preview orphaned G4's comparator, "corrected 1 s within 2 points of corrected 2.5 s"). Replacement M3 speaker gates: trio mean DER `<= .1393` with no per-case DER regression vs baseline live (bill `.2235` / milei `.1945` / keyu `.1112`); trio mean `speaker_accuracy >= .8437`; 5-minute-case DER `<= .0947`. Derivation: half-gap recovery toward the paired file arm (trio live `.1764` → file `.1021`; 5-min live `.1315` → file `.0579`) plus the measured identity ceiling (`prototypes/live-file-gap-identity/NOTES.md`). §1.3's G4 reporting requirement carries over: evaluator v2's matched-word speaker accuracy and `score_live_speaker_accuracy` both reported |
| G5 | Not applicable (no one-second candidate) |
| G7 | Rescoped: **one** live session must sustain real time with rolling enabled (combined RTF < 1, bounded queues, no dropped canonical commits). Two-session stress deferred |
| §10.6 / E2 soak | 30-minute soak → **5-minute soak** (the longest allowed corpus) |
| E2 browser overwrite E2E | Headless render/serialization test stays in the campaign; the attended browser check moves to morning review |
| §12.2 E4 matrix | Terminal finalization measured on trio + 3-minute + 5-minute cases only; G8 (terminal WER within .01 of paired file) unchanged |
| §13 optional multi-view | Out of campaign scope; revisit after the ladder completes |

### B.4 Access grants for the unattended campaign

- May restart the **local MacStudio** dev backend (`web_cli`, port 7861) and the SSH tunnel,
  using the existing runbook scripts only, in order to deploy campaign-branch code for paired
  re-acquisition. Must record every restart in the campaign journal.
- Must **never** touch the 4070 Ti host (no SSH mutations; the vLLM service is read-only
  infrastructure), never push to any remote, never commit outside branch
  `ralph/live-convergence-0824`, never merge.
- The GPU is assumed quiet during the run; certification measurements must still record the
  endpoint counter deltas that prove it.
