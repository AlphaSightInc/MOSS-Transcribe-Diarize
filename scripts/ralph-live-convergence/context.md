# Context - Live-mode convergence campaign

## Ground

- Repo: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize` — branch `ralph/live-convergence-0824`
- Read before editing: `docs/plans/live-mode-convergence-implementation-20260824.md`
  (the spec; **Appendix B overrides the body; Appendix A is the runbook + code map**),
  `AGENTS.md`, `docs/design-streaming-diarization.md` §2/§7.
- Key code paths and why they matter:
  - `moss_transcribe_diarize/live_service_replay.py:~880-975` — the payload reconstructors
    (field-complete since iteration 1; keep them so). `_drain_service_events` (~`:290`) is the
    event-stream cursor added in iteration 5; the trace is written from what it collected, so
    any new read of the stream must go through it rather than calling `service.events` again.
  - `moss_transcribe_diarize/app/vllm_runner.py:_validate_transcription_response` +
    `app/live_adapters.py:~330` — the decode seam. The disposition collapse is fixed (iteration 2)
    and the salvage call is wired (iteration 7): the catch reads `exc.text` and asks
    `classify_live_transcript`, but only for `UNPARSEABLE_TEXT` — a zero-token decode has no
    answer to repair even when its payload carries parseable text (regression test exists).
  - `app/live_span_bounds.py` — clamp-never-refuse precedent; now also home to
    `classify_live_transcript` (iteration 7). Any future question of the form "what may this
    span publish?" is answered there, not at a caller.
  - `app/live_session.py` — `FrozenSpan:75`, `CanonicalCommit` (~:163, `revised_transcript`
    invariant "same words, revised labels"), `revise_labels:539-563`, published-text rule `:581`,
    snapshot ctor `:630-646`. M2 adds `apply_text_revision` + §7.3 fields here.
  - `app/live_arbiter.py:62,68,81` — the three submit methods; M2 adds `submit_live_refinement`.
  - `app/live_endpoint.py` — 2.5 s hard cap (`hard_cap_samples=40000` via bounds config; stays 2.5 s).
  - `app/live_identity*.py` — album (score .35 / margin .10 / floor 0.5 s) + sweep; M3 wires
    witness-owned evidence through the existing album, never context audio.
  - `app/windowed_transcription.py` — 150/120 file pipeline M4 reuses via a small adapter.
  - Scorers: `moss_transcribe_diarize/evaluation.py`, `moss_transcribe_diarize/live_speaker_accuracy.py`.

## Current state

(2026-08-25, after iteration 8)

- Deployed dev stack up: `web_cli` **pid 22561, restarted 2026-08-25 02:11:11 onto the M1
  build** (repo working tree @ `b15503a`) at `https://127.0.0.1:7861` (bearer token
  `~/.local/share/moss-transcribe-diarize/g3/shared-token`), SSH tunnel `127.0.0.1:18000` →
  4070 Ti vLLM `OpenMOSS-Team/MOSS-Transcribe-Diarize`. Descriptor identical before and after both
  restarts (`evidence/.../M0d-paired-reacquisition/restart-{pre,post}.txt` for the M0d build,
  `evidence/.../M1-e1-exit/restart-{pre,post}.txt` for this one) — the build changed and
  nothing else. Restart again after any production change, and record it.
- Paired baseline (deployed stack, 2026-08-24): trio FILE WER .1039 / TBSA .9106 / DER .1021 /
  spk_acc .8979 vs LIVE .1999 / .8384 / .1764 / .8236; 5-min keyu FILE .0506/.0579(DER) vs
  LIVE .1464/.1315. Artifacts + drivers: `prototypes/live-file-gap-baseline-20260824/`.
  Re-acquired on campaign code 2026-08-25 (M0d): file arms byte-identical; live per case
  bill WER .2727 / DER .2237, milei .1440 / .1945, keyu .1942 / .1122; 5-min live
  .1464-.1477 / DER .1130-.1100. Two named deltas: bill live WER .2614 → .2727 is one decode
  flip (one extra published segment), and 5-min live DER .1315 → .1130 is real — the M0a fix
  restored `revised_transcript`, so the scored hypothesis finally carries the label revisions
  the session applied. **The PRD's preregistered comparators (.2614 / .1440 / .1942) stand
  unchanged**; the re-acquisition explains their noise, it does not move them.
- Root causes (measured, `prototypes/live-file-gap-{context,emptyspan,identity,timing}/NOTES.md`):
  seam severance dominates (boundary WER .483 vs interior .082≈file); 5/80 spans are parser
  discards of correct words (missing closing timestamp; salvage ceiling = 1/3 of coverage gap
  at zero GPU); identity misassignment 0.00 s (S00 = sub-0.5 s fragments, ceiling
  spk_acc .8437 via adoption+margin); TSA/coverage/DER carry extent artifact — WER + recall
  are the honest text metrics until evaluator v2.
- Rolling evidence: lexical stitcher 10/5 → trio WER .1289
  (`prototypes/live-file-gap-context/proto_context_arms.py`, arm a2); time-proportional
  stitcher → .146 (`prototypes/streaming-diarization/live-multiview-prototype/`); seam5
  refuted (worse than nothing); terminal = file exactly. Grid (§10.2) decides the production
  policy; decode volume target ≤ ~2× audio.
- **M0a CLOSED (iteration 1).** `verify_replay_roundtrip.py` now exits 0. The replay client
  dropped three fields, not two: `CanonicalCommit.revised_transcript`,
  `LiveSnapshot.label_revision_version`, and `LiveServiceDescriptor.live_protocol` (v2
  capabilities silently reverted to defaults). All three restored in
  `live_service_replay.py:_commit_from_dict/_live_snapshot_from_dict/_descriptor_from_dict`;
  `ReplayReconstructorRoundTripTest` in `tests/test_live_service_replay.py` is the tripwire
  (JSON round-trip equality + `_assert_varies_from_defaults`, which fails on any *new*
  defaulted field left unset, so this defect class cannot recur silently). Mutation-checked:
  deleting any one restored line fails the test. Evidence:
  `evidence/live-convergence-0824/M0a-replay-roundtrip/`.
- **M0b CLOSED (iteration 2).** The three no-speech endings are no longer one. `EmptyTranscriptCause`
  (`no_generated_tokens` / `empty_text` / `unparseable_text`) lives on `app/transcription_outcome.py`
  and rides on `EmptyTranscriptionError` together with the raw answer and the token count; the
  adapter catch at `live_adapters.py:307` keeps `empty_cause` + real `generated_tokens` on
  `InferenceTranscript`; `live_coordinator._decode_empty_reason` believes a reported cause and
  falls back to the transcript rule for decoders that report none; `canonical_decode_generated_tokens`
  is now on `CoordinatorWorkResult` and the `canonical_processed` event. All 7 saved real decodes
  that the baseline lost now report `decoder_returned_unparseable_transcript` with their true token
  counts (13-24) and still publish `""` -- observation changed, policy did not. Five mutations
  caught; file-mode decoder output byte-identical to HEAD (worktree A/B, elapsed excluded).
  Evidence: `evidence/live-convergence-0824/M0b-decode-disposition/`.
- **The raw unparseable text still stops at the adapter seam** (`exc.text`), never carried onto
  `InferenceTranscript`: telemetry must never see meeting words. Since iteration 7 the one caller
  entitled to read it -- `classify_live_transcript` -- is called right there, and what leaves the
  seam is either a completed transcript or a named refusal.
- Refusal boilerplate is still classified as `unparseable_text` at the decoder, correctly: that is
  the observation. The *decision* about it is the salvage gate, which refuses every observed
  hallucination because they all sit on silence-frozen spans -- no phrase list ships (see M1).
- Replay traces written **before** this fix still read as "zero revisions / never corrected";
  `identity_finalized` events never went through these reconstructors and stay trustworthy.
  The 5-minute run's cadence sweep applied 2 label revisions — M0d re-acquisition must show
  them in the terminal snapshot now.
- **M0c CLOSED (iteration 3).** Evaluator v2 exists as a prototype and passes all four A0.3
  gates. `prototypes/streaming-diarization/live-convergence/evaluator_v2.py` (scoring only) +
  `compare_evaluators.py` (driver, exit 0 iff gates pass) + `cases.json` (corpus contract:
  which saved hypotheses, which corpus, which group mean, plus the means the plan published).
  Q1 self-score 1.0 on every axis 5/5; Q2 the `"xx"` control earns recall .0000 / matched-word
  speaker .0000 while the deployed scorer gives it coverage 1.0000 / TBSA .6817 / DER .1722
  (independently reproducing plan §3.4 to 4 dp); Q3 same-speaker split invariance 10/10;
  Q4 legacy recomputation exact 10/10 and the plan §1.3 published means (.1039/.9506/.1999/.9135)
  reproduced 4/4. Five mutations caught. Evidence:
  `evidence/live-convergence-0824/M0c-evaluator-v2/`.
- v2 trio means from saved hypotheses: file WER .1039 / recall .9506 / matched-word spk .9506 /
  DER(speech regions) .0679 vs live .1999 / .9135 / .9059 / .1393. 5-min case file
  .0506/.9726/.9726/.0449 vs live .1464/.9302/.8796/.1113.
- Seam severance reproduced by a second implementation over a different seam set: pooled trio at
  the 0.40 s band, live boundary WER .3290 vs interior .1404 (density 2.34); file .0631 vs .1246
  (density 0.51). `live-file-gap-context/diagnosis.json` got 2.72 / 0.75. Same conclusion.
- v2's DER over *reference intervals* equals the deployed DER exactly on every fully-referenced
  case; restricting to VAD speech regions is the only difference and it removes the silence
  charge inside gapless turns (milei live .1945 -> .1116). Time-based DER stays extent-sensitive
  by nature -- `matched_word_speaker_accuracy` is the non-gameable speaker axis, and M3 must
  report both (plan §1.3 G4).
- Evaluator v2 is a **prototype**: no production module reads it, and M1-M4 gates still name the
  deployed metrics. Promotion is a later, separately reviewed change.
- **M0d MEASURED (iteration 4), 4 of 5 gates pass; M0 does NOT close.** Four sequential passes
  (trio ×2, 5-minute ×2) on the restarted service, then
  `verify_paired_reacquisition.py`. G1 file-byte-identical PASS (5/5 cases × 2 runs);
  G3 5-minute terminal snapshot shows the revisions `identity_finalized` reports PASS
  (A 2==2, B 1==1; baseline 0 vs 2 — the M0a defect retired); G4 service-runs-campaign-code
  PASS (240/240 `canonical_processed` carry `canonical_decode_generated_tokens`, baseline
  control 0/115); G5 single provenance PASS. **G2 fresh-vs-fresh live hash-identical FAILS on
  the 5-minute case** (all four 60 s cases pass). Evidence:
  `evidence/live-convergence-0824/M0d-paired-reacquisition/`.
- **G2's cause is measured, external, and has no in-repo lever: the deployed decoder is not a
  function.** `probe_decode_determinism.py` sends the identical multipart greedy request 12×
  through the same `VllmRunner` the service uses: after a ~3-minute idle gap, 12 requests gave
  2 distinct outputs (request 0: 20 tokens; 1-11: 37); repeated immediately while warm, 12/12
  identical. Live issues ~24 small requests per minute of audio where file issues one large
  one, which is exactly why file arms reproduce byte-for-byte and live arms do not. The 4070 Ti
  host is read-only by PRD constraint; greedy, model and prompt are frozen. G2 as worded is not
  achievable. Its M0(d) row stays **unsigned pending an owner ruling** (PRD: "a hard gate
  failure leaves its row unsigned") — the campaign is not stopped, because nothing in the
  convergence approach is refuted by a 1-in-115 decode flip.
- Endpointing is deterministic and that is now proven, not assumed: `diff_live_runs.py` finds
  **zero differing spans** across all three trio pairs, and on the 5-minute pair 114/114 span
  bounds identical with the earliest divergence at exactly one span (55: 24 vs 26 generated
  tokens). The other 51 differing spans are pure identity cascade (49× `identity_revision_version`,
  2× `identity_status` abstain→prepared) — one decode flip changed the parsed speaker turns,
  hence the embedding evidence, hence the album, producing 3 speakers/2 revisions vs 4/1.
- **F3 CLOSED (iteration 5): replay traces are complete again.** The replay client read the
  service event stream once, with `since_seq=0`, *after* the session ended, while the service
  holds events in `deque(maxlen=bounds.max_events)` (1000 deployed,
  `app/live_service_runtime.py:499`). A 5-minute session emits 1113 events, so 113 were evicted
  first: every 5-minute trace ever written, the checked-in baseline included, started at frame 60
  / span 13 and held 114 of 127 spans while looking well formed. `_drain_service_events` now
  drains once per accepted frame with the cursor the client already had, and a gap raises
  `ServiceReplayEventLossFailure` instead of being written into the artifact. Fresh 5-minute
  pass: 1113 events contiguous from seq 0, frame 0, spans 0-126, all 127 (`gates.json` 5/5).
  What must fit inside `max_events` is now one frame period of events (1-3 in production), not
  a whole session. Client-side only: no service restart, descriptor unchanged, file mode
  untouched, and the live portal never had the defect (it always polled with a moving cursor).
  Non-overflowing traces are unchanged — `probe_replay_trace_shape_identity.py` shows HEAD vs
  working tree differ only in the four clock-stamped fields two HEAD runs also differ in.
  Evidence: `evidence/live-convergence-0824/M0e-trace-completeness/`.
- **The truncation was censoring the RTF gate.** `_canonical_decode_rtf_evaluation` reads that
  stream: on the complete 5-minute trace p95 goes .2320 -> .2624 and measurements above the 1.0
  bound go 1 -> 3 (still passes). Every over-bound measurement is a SHORT span — span 0 is 0.08 s
  of audio decoded in 0.244 s (RTF 3.04) while 2.5 s hard-cap spans sit at .085-.13. Fixed
  per-request overhead, not slow decoding; M2/M3 must keep that shape in view for the G7 budget.
  The checked-in baseline's `keyu-5m/live/run-001/trace.jsonl` stays truncated (it is the frozen
  comparator); its README now says so and points at the complete trace.
- **F4: extent jitter is provider-side and survives identical decodes.** On the trio, where every
  span and every decode matched, published boundaries still moved ±10-20 ms (one webrtcvad
  frame) on 3/26 keyu and 6/32 jamie segments, and one jamie segment changed speaker label. WER
  is blind to it; DER/TSA/coverage are not. A ±.002 per-case DER difference is inside this noise
  until the floor is quantified.
- **M1a ANSWERED (iteration 6): the salvage gate is O1 (hard-cap freeze), not O2 (recomputed
  VAD >= 0.5).** Plan §9.1 run over the full §9.2 corpus -- 184 saved spans (trio 80 + jamie 27
  + adam-3min 77) plus 5 constructed two-speaker hard-cap spans, **zero MOSS requests**. Only 10
  spans parse to zero segments, so only 10 carry a gate decision; O1 and O2 agree on 9 and
  disagree on exactly one: `lex_javier_milei#31`, `[0.00][S01]And.` on a 0.24 s `stop_flush`
  tail (speech ratio 1.000). Both gates project to trio WER **.188506** and v2 content recall
  **.926748**; O2's entire margin is `text_coverage` +.0014 / composite +.0011, bought by
  publishing one word that earns **no** LCS credit -- the plan §3.4 extent artifact, not
  recovered speech. It is WER-neutral only by alignment accident (the reference reads
  "...brought inflation down **to** its lowest...", so `and` turns a deletion into a
  substitution). O1 also needs no new state: it reads `FrozenSpan.reason`, where O2 must re-run
  WebRTC VAD over retained span PCM on the decode-completion path. Evidence:
  `evidence/live-convergence-0824/M1a-salvage-gate-comparison/`; preregistration
  `prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M1a.md`.
- The prototyped completion rule needs **no interpolation**: merge adjacent same-speaker chunks
  (lossless), supply absent *outer* bounds from the span, fill an interior boundary only from a
  timestamp the decoder actually emitted, and **refuse** when two different speaker labels have
  no timestamp between them. It reproduces the older P1v projection to 4 dp
  (composite .8553 / coverage .8828 / TSA .8587 / WER .1885 under O2 == P1v), so the strictness
  costs nothing here and removes the invented cross-speaker interval plan D5 forbids feeding to
  identity. Salvage output on the corpus is exactly two spans:
  `[0][S01]The difference between, you said the stock market.[2.5]` (bill 02) and
  `[0.15][S01]Last year, we had you on the video board at Chase.[2.5]` (jamie 22).
- The gate is load-bearing, measured: ungating salvage moves milei WER .1440 -> .1520 with
  content recall flat at .9267 (mutation M3). The **refusal phrase list is not**: its marginal
  load is 0 under both gates, because every hallucination sits on a `leading_silence` freeze at
  speech ratio 0.000, and 0 of 163 hard-cap spans produced one. §9.3 should ship the gate, not a
  locale-specific string table (AGENTS.md); if review keeps it, keep it as corpus data, not
  literals in the module.
- Freeze reason and speech ratio are different predicates, not proxies: over 184 spans
  `hard_cap` 163 (ratio .416-1.000, 1 below the O2 floor), `leading_silence` 12 (.000-1.000, 11
  below), `end_silence` 6 (.409-.917, 2 below), `stop_flush` 3 (.938-1.000, 0 below). They agree
  on the salvage decision because the zero-parse spans sit where the predicates coincide.
- F5 (recorded, not chased): a *partially* parseable span silently drops its trailing turn --
  `[0.10][S01] I think so[1.20][1.25][S02] and I agree` publishes turn 1 and loses turn 2 with no
  empty-span signal. **Not observed** in the 77 raw decodes available; invisible in the trio/jamie
  corpus because those texts are post-parse renders. Constructible is not reachable (AGENTS.md).
- **M1 PRODUCTION SHIPPED (iteration 7); the E1 exit gate has NOT run.**
  `classify_live_transcript` + `LiveTranscriptOutcome`/`LiveTranscriptDisposition` live in
  `app/live_span_bounds.py`; the adapter catch routes `exc.text` through it; `salvage_disposition`
  rides on `InferenceTranscript` -> `CoordinatorPreparedWork.decode_salvage` ->
  `CoordinatorWorkResult.canonical_decode_salvage` -> the `canonical_processed` event.
  `verify_production_salvage.py` exit 0: the SHIPPED module reproduces the adjudicated O1 column
  over all 184 corpus spans + 5 constructed spans (174 parsed / 2 salvaged / 8 refused_gate).
  Full suite 1012 passed, 2 skipped, 386 subtests. File-mode decoder A/B vs a HEAD worktree
  byte-identical (sha ad381d8b...). Five mutations caught. Evidence:
  `evidence/live-convergence-0824/M1-salvage-production/`.
- Two deliberate deviations from the plan §6 M1 sketch, both measured, both recorded in that
  NOTES.md: (1) no `speech_ratio` parameter -- plan §9.1 conditions it on O2 and O2 lost, so it
  would have no reader; (2) no refusal-boilerplate phrase list -- zero marginal load over the
  corpus (all six hallucinations sit on `leading_silence`, which the gate refuses; 0 of 163
  hard-cap spans produced one) and AGENTS.md rules locale-specific string tables out of general
  logic. Residual accepted and pinned by a test: boilerplate on a hard-cap span would publish.
- One behaviour trap found while wiring, worth remembering: `_validate_transcription_response`
  raises `NO_GENERATED_TOKENS` **before** it looks at the text, so a response whose payload holds
  a perfectly parseable transcript alongside `completion_tokens: 0` reaches the catch with usable
  text. Salvage is offered only `UNPARSEABLE_TEXT` for exactly that reason.
- `HARD_CAP_REASON` now exists in `app/live_endpoint.py` and is the one spelling of the freeze
  reason the salvage gate reads. A second spelling would silently open or close the gate.
- **M1 E1 EXIT MEASURED (iteration 8): 5 of 6 gates pass; M1 does NOT close.** Service restarted
  onto the M1 build, four warm-decoder passes (`run_paired_passes.sh`), gates by
  `verify_m1_exit.py`. PASS: G-M1-2 no per-case regression (bill −.02273, milei 0, keyu 0),
  G-M1-3 file byte-identical (5 cases × 2 passes), G-M1-4 zero extra MOSS requests
  (24/32/24/27/128), G-M1-5 nothing a refused span said was published (0 rows inside 22 refused
  spans; 4/4 salvaged spans found as the positive control), G-M1-6 identity saw only salvager
  intervals (4 salvaged spans, all reproduced from the corpus, intervals equal). **FAIL:
  G-M1-1 trio live WER .192294 > .190.** Evidence: `evidence/live-convergence-0824/M1-e1-exit/`;
  six artifact mutations each caught by their own gate.
- **The G-M1-1 miss is .0023 and is not M1's.** `attribute_wer_delta.py` re-scores the real bill
  hypothesis without one segment at a time: the salvaged span `[5.00,7.50]` is worth
  **−.034091** — plan §9.1 projected −.0341 — and a `[49.75,50.00] S00 "You know."` fragment is
  worth **+.011363**. A per-segment diff of baseline → M0d → M1 shows M0d added that fragment
  (before M1 was written) and M1 added nothing but the salvaged span. It sits in bill span 19,
  samples 760000-800000, the exact span `probe_decode_determinism.py` caught giving 20 vs 37
  tokens; this run decodes it at 37. Bill without it is .227273 and the trio mean is **.188506**
  = the §9.1 projection to 6 dp. **Owner ruling needed: score G-M1-1 on the frozen 2026-08-24
  instrument (passes, .188506) or as deployed (fails, .192294).** Row unsigned, same disposition
  as M0d's G2; no `.stop` — M2's gate is `<= .150` on the same trio, strictly stronger, and the
  campaign is not blocked either way.
- Salvage fires on exactly the two spans §9.1 predicted (`lex_bill_ackman#02`,
  `acquired_jamie_dimon#22`) and nowhere else. The **5-minute case salvages nothing**: its six
  zero-parse spans are all non-`hard_cap`, the gate refuses all six, and its WER is unmoved
  (.147059 mean, .147059 on the M0d build). M1's whole live surface is two spans in two cases.
- **Noise floor, first N=2 reading (candidate 4c, partly answered).** Two trio passes produced
  **identical published text** on all four cases; only extents moved (±10-20 ms on 1 bill, 1
  milei, 4 keyu segments — F4). The 5-minute case still spreads: WER .146375/.147743 (.0014),
  DER .113033/.110 (.0030). So the trio needs no repeat budget for M2/M3 gate readings; the
  5-minute case does.
- **M0d's 5-minute decode count of 115 was the truncated trace, not a decode count.** The M0e
  complete trace and both M1 passes all read 128 `canonical_processed`. Any future comparator
  drawn from `M0d-paired-reacquisition/gates.json` for the 5-minute case must use M0e instead.
- The **last span of a meeting emits no `span_frozen` event** (flushed on stop), but
  `canonical_processed` carries `committed_samples` + `frozen_span_sample_count`, which place
  it. `lex_javier_milei#31` — the 0.24 s `stop_flush` tail M1a adjudicated — is refused and
  publishes nothing, confirmed from those two fields.
- A gate over *published words* must be anchored to the span that produced them: the corpus
  holds the one-word decode `[0.00][S01]And.`, and "and" appears in any minute of English
  speech. G-M1-5 asks whether a refused span published a row inside its own bounds, with the
  salvaged spans as a positive control so it cannot pass vacuously.
- Rest of the ladder (M2-M5) unimplemented; working tree carries the plan, evidence prototypes,
  and this scaffold.

## Validation

```bash
# stack sanity (also the loop preflight)
bash scripts/ralph-live-convergence/preflight.sh
# M0a defect reproducer (exit 0 = fixed)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python prototypes/live-file-roadmap-verification/verify_replay_roundtrip.py
# M0b disposition on the 7 saved real lost decodes (all -> unparseable, published text still "")
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/replay_saved_decode_dispositions.py
# file-mode decoder A/B against any checkout (identical output = file mode untouched)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/probe_file_mode_decode_identity.py <repo-root>
# targeted tests for touched modules (narrow first)
.venv/bin/python -m pytest tests/test_live_service_replay.py -q
.venv/bin/python -m pytest tests/test_live_session.py tests/test_live_coordinator.py -q
# paired re-acquisition (trio + 5-min), against the RUNNING service
.venv/bin/python prototypes/live-file-gap-baseline-20260824/remeasure_live_vs_file.py /tmp/rlc-trio-$(date +%H%M%S)
.venv/bin/python prototypes/live-file-gap-baseline-20260824/remeasure_5m_case.py /tmp/rlc-5m-$(date +%H%M%S)
# M0c evaluator v2 gates (exit 0 = all four A0.3 gates pass)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_evaluators.py --output /tmp/v2.json
# M0d four paired passes (detached; ~19 min) then the gates
prototypes/streaming-diarization/live-convergence/run_paired_reacquisition.sh /tmp/m0d-<stamp>
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_paired_reacquisition.py --fresh-root /tmp/m0d-<stamp>
# where do two live runs of the same audio first disagree? (also flags a truncated trace)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/diff_live_runs.py <trace-A> <trace-B>
# is the deployed decoder bit-reproducible for an identical greedy request?
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/probe_decode_determinism.py --repeats 12
# does incremental event draining change a trace that never overflowed? (exit 0 = no)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/probe_replay_trace_shape_identity.py
# M1a salvage-gate comparison, plan §9.1 (exit 0 = all seven gates pass; zero MOSS requests)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_salvage_gates.py --output /tmp/m1a.json
# does the SHIPPED salvage classifier still decide what plan §9.1 measured? (exit 0 = yes)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_production_salvage.py
# M1 (plan E1) exit: four warm-decoder passes against the running service, then the six gates
prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m1-exit-<stamp>
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m1_exit.py --fresh-root /tmp/m1-exit-<stamp>
# what is a per-case WER delta actually made of? (re-scores without a named segment)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/attribute_wer_delta.py \
  <live-hypothesis.jsonl> --case lex_bill_ackman --drop 49.75:50.0
# salvage tests (table over the 10 zero-parse decodes + 5 constructed spans, and the seam)
.venv/bin/python -m pytest tests/test_live_transcript_salvage.py tests/test_live_pipeline_seams.py -q
# 9-clip identity floor (M3)
.venv/bin/python -m pytest tests/test_live_identity_real_corpus.py -q
# full suite checkpoint (before closing a milestone)
.venv/bin/python -m pytest tests/ -q
```

## Candidates

1. ~~**M0a replay-adapter fix**~~ — DONE iteration 1 (see Current state). Remaining M0
   work is 0b/0c/0d below.
2. ~~**M0b typed disposition**~~ — DONE iteration 2 (see Current state). Refusal is M1's,
   by design.
3. ~~**M0c evaluator v2 prototype**~~ — DONE iteration 3 (see Current state). Promotion into
   `moss_transcribe_diarize/` is deliberately NOT done and is not an M0 item.
4. ~~**M0d paired re-acquisition**~~ — MEASURED iteration 4, 4 of 5 gates pass. G2 is the one
   open item and it needs an owner ruling, not more code (see Current state). Do NOT re-run the
   four passes to try for a green G2; the cause is an external decoder and re-rolling until it
   passes would be tuning the instrument to the answer.
4b. ~~**F3 trace truncation**~~ — DONE iteration 5, all five gates pass (see Current state).
   M1's salvage corpus and M4's G10 accounting can now read a complete 5-minute event stream.
4c. **Noise floor for per-case gates** — PARTLY ANSWERED iteration 8 at N=2: the trio is
   text-identical across passes (extents only), the 5-minute case spreads WER .0014 / DER .0030.
   What is still open is only the 5-minute spread at N>=4, and it is cheap to fold into M2's own
   soak rather than run on its own. Do it when M2 needs a per-case 5-minute verdict.
5. ~~**M1 production salvage (§9.3)**~~ — SHIPPED iteration 7 (see Current state). What remains
   of M1 is only the E1 exit gate, which is candidate 5b.
5b. ~~**M1 E1 exit: paired rerun**~~ — MEASURED iteration 8, 5 of 6 gates pass. G-M1-1 is the
   one open item and it needs an owner ruling, not more code (see Current state). Do NOT re-run
   the passes hoping the pre-M1 decode flip goes away; that is tuning the instrument to the
   answer, and the preregistration forbids it.
6. **M2 ADR then grid - NEXT**: first write the accepted text-finalization ADR from plan D1-D7 verbatim
   (Appendix B Q8); then run `compare_rolling_grid.py` per plan §10.3, starting from
   `proto_context_arms.py`'s lexical stitcher; then production per plan §10.5 order.
7. **M3 S1 speaker authority** prototype (`compare_speaker_authority.py` per plan §11.1,
   2.5 s base only) → production wiring.
8. **M4 terminal finalizer** per plan §12.3 + M4 gates on trio/3-min/5-min (the owner-directed
   prerelease amendment also gates terminal DER within .020 of the paired file arm per case and
   requires §12.2 cold/warm model-readiness reporting).
9. **M5 evidence + records** per PRD.

## Non-candidates

- One-second preview / cap changes (Appendix B deleted it; 2.5 s stays; parameterization only).
- Any audio > 5 minutes; 30/60-minute matrix; two-session stress (deferred by Appendix B).
- Optional uncertainty-routed multi-view (§13) — after the ladder, separate campaign.
- Threshold tuning of endpoint policy (prior sweep NO_POLICY_CHANGE; not a lever here).
- Sweep-margin/cadence identity changes beyond M3's witness-owned evidence (C2b needs the
  9-clip gate anyway and identity ceiling is already reachable via M3's design).
- Attended browser E2E (morning review item); any deploy beyond the local dev service;
  touching the 4070 Ti host; pushing; leaving the campaign branch.
