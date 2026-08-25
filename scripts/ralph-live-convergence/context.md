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
  - `app/live_session.py` — `FrozenSpan`, `CanonicalCommit` (`revised_transcript` invariant
    "same words, revised labels"), `revise_labels`, `_publish_span`. **The §6 M3 authority ships
    here since iteration 12**: `apply_text_revision` (seven validations in `_text_revision_refusal`),
    the four §7.3 snapshot fields, and the label projection
    (`_project_canonical_speaker` / `_base_segments` / `_build_effective_transcript`). Anything
    that changes what a reader is shown must bump `_surface_version`, or the effective-surface
    cache goes stale.
  - `app/live_transcript_convergence.py` — **M2, shipped iteration 11**: the rolling converger.
    Four methods (`accept_pcm` / `observe_base` / `complete` / `stop`), the selected 10/10
    geometry, bounded PCM ring, one witness in flight. `LiveSnapshot` satisfies its
    `BaseTranscriptSurface` protocol since iteration 12; `LiveCoordinator` is its runtime caller
    since iteration 14.
  - `app/live_arbiter.py` — **four queues since iteration 13** (plan §6 M5): batch >
    live_canonical > live_refinement > live_provisional. `submit_live_refinement` /
    `release_live_refinement` / the two `ArbiterSnapshot` refinement depths. Dispatching a witness
    *marks it running* inside `next_work`, so a caller that pops one owes a release — the runtime
    pump has been that caller since iteration 14.
  - `app/live_coordinator.py` — **the converger's runtime home since iteration 14**: an optional
    `rolling_decoder` brings a `RollingTranscriptConverger` with it, `accept_frame` feeds it PCM,
    `submit_prepared_work` and `submit_refinement` both call `observe_base`, and
    `capture/decode/submit/release_refinement` are the dispatch cycle. `submit_refinement`
    **releases before it plans** — reversing that loses a window to the arbiter's running-key
    refusal (see Current state).
  - `app/live_service_runtime.py` — dispatch since iteration 14: readiness and the stop drain count
    witnesses, `next_work` may return a refinement item, and `_process_refinement_item` is the
    non-terminal pump. `rolling_decoder_factory` is how a bundle supplies the window decoder.
    **Since iteration 15 it is also where every §7.4 event is written** — `_record_rolling_queued` /
    `_record_rolling_completed`, the `rolling_timing` table, and `decode_salvaged`. Events are
    recorded HERE and nowhere else (plan §6 M7: adapters serialize, they do not decide), from data
    the coordinator hands back on its result objects.
  - `app/live_portal.py` — the one page a reader ever sees. **Since iteration 16 it renders
    `effective_transcript`, not `committed`**: `renderTranscript` replaces the transcript node from
    the snapshot alone (no state across polls), `speakerLabel` re-applies the server's
    `display_speaker_label` rule to the canonical identity the surface carries, and
    `displaySeconds` reads the rate off `snapshot.descriptor.sample_rate` (a snapshot without one
    is refused). The `S00` literal is bound to `UNATTRIBUTED_SPEAKER` by a test.
  - `app/live_endpoint.py` — 2.5 s hard cap (`hard_cap_samples=40000` via bounds config; stays 2.5 s).
  - `app/live_identity*.py` — album (score .35 / margin .10 / floor 0.5 s) + sweep; M3 wires
    witness-owned evidence through the existing album, never context audio.
  - `app/windowed_transcription.py` — 150/120 file pipeline M4 reuses via a small adapter.
  - `moss_transcribe_diarize/live_surface.py` — **NEW iteration 17**: how a surface segment names
    its speaker (`UNATTRIBUTED_SPEAKER`, `display_speaker_label`, `published_speaker_label`), in a
    LEAF module because the F-cert reducer loads the scorer from a bare checkout with no `app`
    import available. `app/live_session.py` re-exports all three, so every existing caller is
    unchanged.
  - Scorers: `moss_transcribe_diarize/evaluation.py`, `moss_transcribe_diarize/live_speaker_accuracy.py`.
    The second is also **the export** (plan §10.5 step 7, since iteration 17):
    `hypothesis_from_live_snapshot` reads `effective_transcript` when the snapshot carries one and
    re-parses `committed` only for a pre-§7.3 snapshot. Import nothing from `app` into it.

## Current state

(2026-08-25, after iteration 18)

- Deployed dev stack up: `web_cli` **pid 44278, restarted 2026-08-25 05:52:14 onto the M2
  build** (repo working tree @ `4d6cb29`) at `https://127.0.0.1:7861` (bearer token
  `~/.local/share/moss-transcribe-diarize/g3/shared-token`), SSH tunnel `127.0.0.1:18000` →
  4070 Ti vLLM `OpenMOSS-Team/MOSS-Transcribe-Diarize`. Descriptor identical before and after every
  restart (`evidence/.../M0d-paired-reacquisition/`, `.../M1-e1-exit/`, `.../M2-e2-exit/`
  `restart-{pre,post}.txt`) — the build changed and nothing else. **The rolling witness is ON in
  the deployed service**: the bundle wires `rolling_decoder_factory` unconditionally, so any live
  session now plans, decodes and applies windows. Restart again after any production change, and
  record it.
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
- Rolling evidence: 10/5 central ownership → trio WER .1289
  (`prototypes/live-file-gap-context/proto_context_arms.py`, arm a2 — the plan calls this the
  "lexical" stitcher but it cuts by interpolated midpoint, i.e. it is the *char* policy; see the
  M2 grid); time-proportional stitcher → .146
  (`prototypes/streaming-diarization/live-multiview-prototype/`); seam5 refuted (worse than
  nothing); terminal = file exactly. **The §10.2 grid has now decided the production policy
  (iteration 10): `10/10`, trio WER .131861, 1.000× added decode audio.**
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
- **M2 STEP 1 DONE (iteration 9): the text-finalization ADR is written.**
  `docs/adr/0005-live-text-finalization-authority.md` carries plan D1-D7 **byte-for-byte** (spliced
  mechanically, not retyped) plus the authority D7 asked for, stated once: two producers (rolling
  converger over `[0, canonical_through_sample)`, terminal finalizer once per session), one seam
  (`LiveSession.apply_text_revision`), seven validations, four snapshot fields, seven events, zero
  silent rewrites. One override is recorded beside the verbatim text rather than edited into it:
  D6's "Only E3 may promote one-second output" is superseded by Appendix B Q6; D6's operative half
  (do not move the 2.5 s cap while rolling text is being proved) is now unconditional. The record
  also states what it does **not** authorize -- re-ASR inside an identity sweep, redefining
  `revised_transcript`, cap changes, evaluator-v2 promotion, extra VAD/embedding phases,
  tape retention (Q10 refines ADR-0003 and belongs there, at M4), and shipping an E2 arm whose
  gates fail. `verify_adr_text_finalization.py` exit 0; five mutations caught. Evidence:
  `evidence/live-convergence-0824/M2-text-finalization-adr/`.
- The verbatim check is **symmetric and plan-driven**: it parses which decisions are required out of
  the Appendix B Q8 row's own wording, so amending the plan's decisions fails the command until the
  record is amended too, and quoting one decision too many fails as loudly as one too few. No
  production code was touched, so the file-mode byte-identity check has nothing to compare and is
  not claimed.
- **Still owed to the new ADR: one pointer from `docs/design-streaming-diarization.md`.** Deliberately
  deferred to M5, which already edits that file for the dated campaign verdict -- one edit, not two.
  If M5 changes shape, the pointer still has to land somewhere or the record is orphaned.
- **M2 STEP 2 MEASURED (iteration 10): the §10.2 grid ran, all preregistered gates pass, the arm is
  selected.** `compare_rolling_grid.py` -- 4 geometries x 3 stitch policies x 3 runs, 143 distinct
  decodes per run, 114.8 s wall. **Eleven of twelve arms pass G1-G3** (only `10/5:uniform` misses
  G3 at recall .9346). **Plan §10.4 selects `10/10` -- a 10 s window on a 10 s stride**: trio WER
  .199870 -> **.131861**, content recall .9135 -> **.9439**, at **1.000** added decode-audio-second
  per audio-second (half the 10/5 reference arm's 1.833). Evidence:
  `evidence/live-convergence-0824/M2-rolling-grid/`; preregistration
  `prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M2-grid.md`.
- Controls landed EXACT, which is what makes the grid trustworthy: the base control (recorded 2.5 s
  span grid, decoded alone) reproduces the published live trio WER **.199870 / recall .913490**, and
  `10/5:char` reproduces `proto_context_arms` arm `a2` at **.128926 / .948477** -- every printed
  digit. **Noise floor at N=3 is ZERO**: all 12 arms and the base returned identical WER and recall
  on three independently decoded runs, extending iteration 8's N=2 trio finding.
- **The plan's own naming of the stitchers is wrong and the preregistration says so.** §10.2 calls
  the lexical policy "the reference candidate ... implementation is `proto_context_arms.py` (arm
  a2)", but a2 cuts by interpolated word midpoint against a central region -- that is the
  *character-proportional* policy. The published `.1289` belongs to `char`, and this grid attaches
  it there. The three names are kept; only the arm identity is corrected.
- **F1: the selected geometry has no overlap, so it has no stitcher.** At stride == window the
  three policies produce byte-identical word sequences (preregistered prediction P3, verified 9/9
  case-runs). Production consequence for M2 step 3: the converger needs **no** ownership
  arithmetic, no lexical alignment and no word-time interpolation -- a window's words replace
  exactly `[lo, hi)` and the frontier advances to `hi`. Materially less code than plan §6's M2 sketch.
- **F2: duplicated words at joins are real, measured, and policy-dependent.** At 10/10 every policy
  republishes a phrase at one join per run (bill, t=50 s: window [40,50] ends "...the. You know."
  and [50,60] starts "You know, it's many investors..."), because the speaker's phrase straddles the
  cut and zero overlap leaves no evidence any stitcher could use. Where there IS overlap, only
  `char` duplicates (1 join/run at 10/5 and 15/7.5); `uniform` and `lexical` duplicate nothing
  anywhere. This does **not** violate ADR-0005 D4 -- every arm has one owner per interval -- it
  shows that interval discipline alone does not prevent duplicated *words*.
- **F3: no arm in the plan's grid can pass G6 (rolling correction p95 <= 6.0 s) at full-window
  granularity.** Structural floor from measured decode latencies over changed regions only:
  10/5 **6.46 s**, 10/10 **8.51 s**, 15/10 11.64 s, 15/7.5 12.81 s. The arithmetic: with central
  ownership the oldest owned word has age `(L+S)/2`, so `L+S <= 12` is required and the plan's
  cheapest geometry is `L+S = 20`. **Cost and latency rank the geometries in opposite orders.**
  The preregistration fixed this floor as reported-not-selecting, so the selection stands; but M2
  cannot close on G6 with any grid geometry, and that is known before the code exists.
- **Two owner decisions are open on M2 step 2** (both in that NOTES.md, both with a recommendation,
  neither blocking): **D-M2-1** ship the §10.4-selected `10/10` (.1319, 1.000x) or pay 1.5x for
  `15/10:lexical` (.1075 -- within .0035 of the paired FILE arm's .103946 -- recall .9597, zero join
  duplicates)? Recommendation: ship 10/10, record 15/10:lexical as the measured upgrade path.
  **D-M2-2** G6 is unreachable inside the grid; recommendation is to measure it for real in the
  §10.6 soak and leave M2's row unsigned on it if it misses, as M0d's G2 and M1's G-M1-1 already are.
- The grid is replayable **with no GPU**: `--cache-dir evidence/live-convergence-0824/M2-rolling-grid/decode-cache`.
  The five-mutation sweep uses the same cache and issues zero MOSS requests.
- **M2 STEP 3a SHIPPED (iteration 11): the rolling converger is production code and it reproduces
  the selected arm exactly.** `app/live_transcript_convergence.py` (new) + the §7.1/§7.2 contracts
  on `live_session.py` (inert data, +54 lines) + 21 T1 tests. `verify_production_converger.py`
  drives the production class over the trio through the grid's own decode cache and lands on
  **trio WER .131861 / recall .943916**, per case .198864 / .096000 / .100719, six windows,
  **1.000x** added decode audio, proposals tiling `[0, 60 s)` exactly, PCM high-water 160000 of the
  320000 bound, **zero fresh MOSS requests**. Full suite 1033 passed / 2 skipped / 386 subtests
  (1012 before). File mode byte-identical to HEAD (`sha ad381d8b...`, the same digest iteration 7
  recorded). Five mutations in the production file, each caught, control clean before and after.
  Evidence: `evidence/live-convergence-0824/M2-converger-production/`.
- **F1 paid off: the module has no stitcher and no word-time interpolation.** At stride == window
  a window's words replace exactly `[lo, hi)` and the frontier advances to `hi`.
  `RollingGeometry` **refuses** stride < window (`UnmeasuredRollingGeometry`) — an overlapping
  geometry needs a stitcher, a stitcher needs a measured selection, and neither exists. Mutation M1
  removes that guard and WER goes .198864 -> .801136 on bill, so the refusal is load-bearing.
- **A refused proposal needed no state.** A window is planned only once the session's own
  `canonical_through_sample` reaches its first sample, so a proposal the session declines simply
  stops the grid instead of producing revisions it must keep refusing. That deleted a status
  instead of adding one.
- **A failed window stalls rolling for the session, by decision.** Plan §5.2 allows later windows
  "only from the existing monotonic frontier", and at zero overlap none begins there — continuing
  would mean inventing words for the gap or owning an interval with nothing in it, which D4
  forbids. So: keep the surface, record the window, plan no more; the base suffix stays provisional
  and complete. Measured occurrences at this geometry: **0 of 54 window decodes**. The
  carry-forward alternative (reprint the base's words over the failed region so the frontier can
  advance) is recorded as the thing to build **if the §10.6 soak ever observes a failed window**,
  not before. Mutation M5 shows only the T1 test can hold this — the corpus is blind to it.
- **M2 STEP 3b SHIPPED (iteration 12): the session is the text authority, and it attributes.**
  `LiveSession.apply_text_revision` + seven validations (`_text_revision_refusal`) + the four §7.3
  snapshot fields + the label projection, all in `app/live_session.py`; the replay reconstructors
  and the round-trip tripwire extended in the same change (the tripwire fired on the new fields
  before they were varied -- it works). 17 T1 tests in `tests/test_live_text_revision.py`.
  `verify_session_text_authority.py` drives the REAL objects end to end -- baseline spans through
  the real freeze/submit path -> production converger -> `apply_text_revision` ->
  `snapshot().effective_transcript` -> the grid's own scorer -- and lands on **trio WER .131861 /
  recall .943916**, per case .198864 / .096000 / .100719, 6 revisions each, **0 fresh MOSS
  requests**. Full suite 1050 passed / 2 skipped / 386 subtests (1033 before). File mode
  byte-identical (`sha ad381d8b...`, the same digest since iteration 7). Five mutations, each
  caught by the verifier AND a test. Evidence:
  `evidence/live-convergence-0824/M2-session-authority/`.
- **The grid's presumption is now a measured fact: the projection agrees with the timeline the arm
  was selected through on 51 of 51 rolling segments.** The rule is `SpeakerTimeline`'s -- most
  overlap wins, nearest committed speech when a stretch overlaps nothing, ties on the identity's
  own name -- and `S00` is a real candidate that can win, because the base publishes it honestly
  where identity abstained.
- **The projection is computed, not stored, and it is a fallback rather than the last word.** A
  revision keeps only its words; the speaker is recomputed from the base timeline whenever the
  surface is rebuilt, so a later `revise_labels` flows into the rolling prefix for free (T1 test).
  A producer that sets `canonical_speaker` itself is left alone -- which is exactly what E3's
  witness-owned evidence (plan D5) will do, so M3 needs no change here.
- **Ownership at the frontier is keyed on where a segment BEGINS.** A base segment straddling the
  frontier belongs to the revision that already owns its first sample (D4, no duplication); its
  tail is not lost because the next window decodes that audio again. This is invisible at the end
  of a trio case -- six 10 s windows tile the whole minute and no base suffix survives -- so the
  verifier samples the surface after every commit (98 surfaces, 66 with both authorities). Even
  then only `lex_javier_milei` has a base segment straddling a 10 s frontier: mutation M3 is caught
  by the corpus on 1 of 3 cases and by the T1 test unconditionally.
- **Terminal is exempt from the frontier rule, not from validation**: it replaces the surface, so
  it must own it from sample 0, once (`already_finalized`). `finalization_status` can only reach
  `final` today; `running`/`failed`/`unavailable` are E4's (§12.3) and have no producer yet.
- **Refinement scheduling shipped (iteration 13, §10.5 step 3)**: the rolling witness is
  schedulable below the 2.5 s canonical span and above provisional work, one queued-or-running
  witness per coalesce key, and a running MOSS request is never cancelled by a newer witness
  (the newer one is refused, `reason="live refinement already running"`). Measured with three
  sessions on ONE arbiter: 98 dispatches, canonical ahead of a waiting witness 14x, witness ahead
  of waiting canonical 0x, arm unchanged (trio WER `.131861`). Evidence:
  `evidence/live-convergence-0824/M2-refinement-scheduling/`.
- **M2 STEP 4 SHIPPED (iteration 14): the rolling witness runs inside the real runtime, and the
  driver is gone.** Frames go into `LiveServiceRuntime.accept_frame` and the arm comes out of
  `snapshot().effective_transcript`, through the deployed endpoint config, real `webrtcvad`, the
  real arbiter, the production canonical pump and the production decode seam. Each trio case runs
  **twice on one instrument** — no window decoder, then one: base **WER .199870 / recall .913490**
  (= the published live trio), rolling **.131861 / .943916** (= the §10.4 arm), every case exact to
  6 dp; 6/6 windows planned, dispatched and applied per case; 0 failed / 0 stale / 0 admission
  refusals; rolling PCM high-water 208000-240000 vs the 320000 bound; **0 fresh MOSS requests**.
  Full suite 1072 passed / 2 skipped / 386 subtests (1061 before). File mode byte-identical
  (`sha ad381d8b...`, unmoved across five production changes). Five mutations, all caught.
  Evidence: `evidence/live-convergence-0824/M2-runtime-wiring/`.
- **The 10 s window does not fit the deployed decoder, and that is why there are two adapters.**
  The manifest bounds the span decoder at `decoder_config.max_samples: 120000` (7.5 s); a window is
  160000 samples. The bundle now builds a second `RunnerBoundedWavInference` over the SAME runner,
  sized from `DEFAULT_ROLLING_GEOMETRY.window_samples`. Raising the manifest value instead would
  change `decoder_config_hash` -> provider manifest hash -> the deployed descriptor, to widen a
  bound that describes the base path. Do not "simplify" this to one adapter.
- **A witness holds the session's single in-flight inference slot while it decodes.** That is the
  deployment contract (one in-flight vLLM request per harness), not an oversight: rolling's cost is
  a serial cost, so a running window can delay the NEXT canonical span by one decode (~1 s). The
  arbiter still guarantees a witness is never dispatched while canonical work waits. §10.6's soak
  must measure this rather than assume it.
- **A rolling defect ends rolling, never the meeting** (ADR-0005 D1). The refinement pump logs
  (counts and names only), calls `stop_rolling`, and leaves the base path and the surface intact.
  Since iteration 15 that stop is on the event stream (`rolling_decode_completed` outcome
  `defect`, and `rolling_status` on the next `canonical_processed`).
- **M2 STEP 5 SHIPPED (iteration 15): the witness tells its whole story outside the process.**
  Five §7.4 event kinds -- every one with a producer today -- are recorded by
  `live_service_runtime.py` from data the coordinator returns: `rolling_decode_queued` (one per
  PLANNED window, `admitted=false` and `item_id: null` when the arbiter refused),
  `rolling_decode_completed` (one per DISPATCHED window on every path, carrying §7.4's whole record
  -- window samples, owned samples, queue delay, decode elapsed, generated tokens, cap status, RTF
  -- plus an `outcome` from a closed vocabulary), `text_revision_applied` / `text_revision_refused`,
  and `decode_salvaged`. `canonical_processed` also gained `rolling_status`. The §7.3 snapshot half
  needed no code but is now CHECKED (JSON round trip + replay reconstruction equality, per case)
  rather than assumed. `verify_rolling_events.py` exit 0 on nine gates, trio WER **.131861** /
  recall **.943916** unchanged, 0 fresh MOSS requests. Full suite 1079 passed / 2 skipped / 386
  subtests (1072 before). File mode byte-identical (`sha ad381d8b...`, unmoved across six
  production changes). Six mutations, all caught. Evidence:
  `evidence/live-convergence-0824/M2-event-serialization/`.
- **The accounting property is the design, not the field list**: one announcement per PLANNED
  window, one completion per ADMITTED window. A refusal is announced and never completed (nothing
  will complete it); a dispatch that never decoded -- `not_awaited`, `defect`, `session_terminal`
  -- is completed with the decode fields **null rather than zero**. So queued minus completed is a
  live queue depth and can never be a leak. The runtime keeps a `rolling_timing` table keyed by
  item id (the shape `canonical_timing` already had) so the completion can describe a window even
  when the coordinator never hands the request back.
- **G4's payload vocabulary is READ from production, not listed**: `RollingStatus`,
  `LiveTranscriptDisposition`, the finalization statuses, and the string literals inside
  `LiveSession._text_revision_refusal` and `LiveServiceRuntime._process_refinement_item` (36 names).
  A refusal name added to production extends the gate; a payload that starts carrying a meeting word
  does not. Do not replace it with a hard-coded list.
- **The completion's RTF is a real field with an unreal number in the GPU-free instrument**
  (~3e-5, queue waits 0.01-2.9 ms). Generated tokens per window ARE real (77-110 on bill). What the
  witness costs is §10.6's measurement, and iteration 14's D2 (a witness holds the single in-flight
  slot) is what that soak has to price.
- **`decode_salvaged` passed its gate on ZERO occurrences.** No span in the replay instrument
  reaches the salvage gate -- the grid's decode cache holds different answers for bill span 02 than
  the deployed 4070 Ti gave on 2026-08-25, which is iteration 4's "the deployed decoder is not a
  function" from a third direction. The corpus reading is a negative control; the positive control
  is a T2 test driving a genuinely unparseable answer through the production adapter.
- **Four of six mutations are caught by T2 ALONE** (a window nobody was waiting for, a refused
  admission, a refused revision, a salvaged span). Same producer-pacing shape as iterations 11-14:
  the corpus reading of the stream is necessary and not sufficient.
- **Defect found and fixed this iteration: plan-before-release loses a window.** `submit_refinement`
  originally planned the next window before releasing the one that had just answered; the arbiter
  refuses a newer witness while one is RUNNING for the same key (§6 M5, correctly), so the window
  was refused and lost, and the converger — still holding it in its one in-flight slot — stopped
  planning for the session. It fires only when the base is already a whole window ahead when a
  witness lands, so the **trio corpus does not reach it** (mutation M3: verifier exit 0, three T2
  tests fail). The `_rolling_admission_refusals` counter is what made it findable and is now a gate.
- **Three mutation branches the corpus cannot reach, three different reasons**: M2 (no
  `observe_base` after a revision) needs the base to have stopped committing; M3 needs the base a
  window ahead; M4 (session-qualified coalesce key) needs two sessions on one arbiter and the
  runtime builds one per session. All three are properties of producer pacing, and all three are
  pinned by T2 tests.
- **The offline runtime reproduces the deployed span grid exactly** — 24 / 32 / 24 frozen spans,
  identical to the checked-in baseline traces, with the deployed endpoint config and real
  `webrtcvad`. That is what makes a GPU-free end-to-end runtime verifier possible, and it
  re-confirms iteration 4's endpoint determinism from a different direction.
- **A base that falls a whole window behind stops rolling, statedly.** The ring is bounded at
  `2 x window`; reaching it means the audio a pending window needs is gone, so the converger names
  `pcm_evicted` and stops planning. The verifier's first draft hit exactly this (0 windows, all
  three cases) because its driver handed over the whole meeting before the pump thread ran once.
  It now paces the base within two spans, which is what real-time pacing produces.
- **M2 STEP 6 SHIPPED (iteration 16): the arm is on the screen, and the screen is one replacement
  surface.** `live_portal.py` renders `session.effective_transcript` instead of stitching
  `session.committed`: one row per surface segment, session-absolute seconds from the descriptor's
  declared rate, the `Sxx` token re-derived from the canonical identity with the server's own rule,
  and the provisional tail (which no authority owns yet) still shown after it. The status panel
  gained `text revisions` / `converged through sample` / `finalization`, each said only once there
  is something to say. `verify_portal_surface.py` exit 0 on seven gates: base trio WER **.199870** /
  recall **.913490** and rolling **.131861** / **.943916** read off the DOM, per case to 6 dp,
  screen equal to snapshot on every case; 0 fresh MOSS requests. Full suite 1082 passed / 2 skipped
  / 386 subtests (1079 before). File mode byte-identical (`sha ad381d8b...`, unmoved across seven
  production changes). Six mutations, all caught. Evidence:
  `evidence/live-convergence-0824/M2-portal-surface/`.
- **The replacement property is stated as PURITY, and that is what makes it checkable.** At every
  one of 726 polls the transcript node equalled an independent render of *that poll's snapshot
  alone*. A page that carried state across polls cannot satisfy that, which is why mutation M2
  (append instead of replace) is caught at the first poll after the first revision rather than at
  the end. Do not add render state (a diff, an animation buffer, a de-duplicator) without replacing
  that gate with something at least as strong.
- **The page needs the sample rate and must not assume it.** The surface carries sample integers;
  seconds are presentation. `renderSnapshot` refuses a snapshot whose descriptor declares no
  positive integer rate rather than printing a plausible wrong second (mutation M6 shows an assumed
  8000 puts segments outside the meeting). Every server-produced snapshot payload is
  `LiveServiceSnapshot.to_dict()`, so the field is always there.
- **Before this step the reader could not have seen a correction at all.** The old render printed
  one row per committed span on its own *span-relative* clock, so every row started near `[0]`.
  Session-absolute rows are what make a revision land in place.
- **F1 (identity, not render): the live album establishes one canonical speaker per span on the
  offline instrument** — 16 on a one-minute two-speaker interview, `S01`..`S16` on the screen. That
  is the deployed identity behaviour and exactly what E3/M3 exists to fix; recorded here because it
  is what makes the render's speaker-token gate look like a richer corpus than it is.
- **F2: the rolling arm prints materially fewer, longer rows than the base arm for the same audio**
  (bill 30 → 21, milei 28 → 14, keyu 26 → 16). A ten-second witness publishes sentences where
  twenty-four 2.5 s spans publish fragments. It is the first convergence result visible without a
  metric.
- **The provisional-tail mutation is caught by T2 alone.** This instrument's base path commits every
  span it freezes and never publishes a provisional suffix, so sixty seconds of real audio cannot
  see the live tail disappear; the `happy` scenario reads the transcript after a poll that has one.
  Fifth iteration of the same lesson (11-16): the corpus reading is necessary and not sufficient.
- **M2 STEP 7 SHIPPED (iteration 17): the export carries the surface, and §10.5 is complete.**
  `hypothesis_from_live_snapshot` — the one place that turns a served snapshot into the transcript
  the campaign scores, the F-cert harness reads and `remeasure_live_vs_file.py` saves — reads
  `effective_transcript` when the snapshot carries one, and re-parses the committed spans only for
  a snapshot from before §7.3 existed. `live_replay.py`'s `evaluator.jsonl` is schema 2, written
  from the same surface. `verify_export_surface.py` exit 0 on six gates: base trio **.199870** /
  **.913490** and rolling **.131861** / **.943916** *through the export*, per case to 6 dp; export
  == the portal DOM on 3 cases x 2 arms (§14 T3); five checked-in pre-surface `live-hypothesis.jsonl`
  reproduced byte for byte; 0 fresh MOSS requests. Full suite 1091 passed / 2 skipped / 392 subtests
  (1082 / 386 before). File mode byte-identical (`sha ad381d8b...`, unmoved across eight production
  changes). Six mutations, all caught. Evidence:
  `evidence/live-convergence-0824/M2-export-switch/`.
- **The surface reading and the committed reading agree on a session nobody revised** — word for
  word, speaker for speaker, every timestamp inside ONE sample (`6.25e-5` s), scores equal to 6 dp
  on the base arm of all three cases. That measurement is why the switch is unconditional (prefer
  the surface whenever the field exists) rather than gated on `text_revision_version > 0`: two live
  readings of a current snapshot would be a branch a reader has to reason about, for nothing.
- **The display rule now lives in `moss_transcribe_diarize/live_surface.py`, a leaf module, and
  `app/live_session.py` re-exports it.** The first attempt imported it from `app.live_session` into
  the scorer and the test tier caught it in one run: `scripts/ralph-afk/live-canary-clauses.py`
  loads `live_speaker_accuracy.py` straight out of a bare checkout with `-S` and no installed
  package, so ANY `app` import breaks the F-certification reducer. Treat that as a standing
  constraint on `live_speaker_accuracy.py`: siblings only.
- **`published_speaker_label` is the total form of `display_speaker_label`** — `None` and an
  identity this snapshot never established both read as `S00`, because neither may be rendered as a
  guess. The strict primitive still refuses, and both callers that write a label still use it.
- **Four of six mutations are caught by the T3 tests ALONE** (unestablished identity, no corpus
  clamp, the fallback ignoring a sweep's correction, whitespace rows). Each has a stated reason:
  the trio corpora establish every identity their surfaces carry, their sessions end inside their
  own corpus window, no checked-in baseline carries a relabelled span (0 of 5 bundles, 0 of 235
  commits), and the deployed session drops empty segments before the surface. Sixth iteration of
  the same lesson (11-17).
- **The deployed `web_cli` is STILL on the M1 build** (pid 22561 as of iteration 13; verify before
  relying on it). §10.5's order no longer protects anything — step 7 is done — so the restart onto
  this build is now the FIRST thing the M2 exit measurement does, and it must be recorded in
  progress.txt when it happens.
- **M2 EXIT MEASURED (iteration 18): 7 of 8 gates pass, M2 closes on everything but G-M2-4.**
  Service restarted onto the M2 build (pid 44278), four warm-decoder passes 09:55:14-10:14:29Z,
  gates by `verify_m2_exit.py` (definitions preregistered in `PREREGISTRATION-M2-exit.md`).
  PASS: trio rolling WER **.131357** (bound .150; grid projection .131861), per case
  .204545 / .096000 / .093525 vs baseline live .2614 / .1440 / .1942 (deltas -.0568 / -.0480 /
  -.1007), content recall **.943916** (bound .940, = the grid's digits), five-minute WER
  **.082079** (bound .0985; paired file .050616), combined base+witness RTF **.133-.157** with
  rolling depth never above 1 / 0 admission refusals / 0 stale / 0 failed windows / high-water
  168000-208000 of 320000, accounting exact on 8/8 sessions, file mode byte-identical (5 cases x
  2 passes). **FAIL: G-M2-4 correction-after-provisional p95 8.756675 s > 6.0 s.** Full suite
  1091 passed / 2 skipped / 392 subtests. Eight artifact mutations, each flipping its own gate.
  Evidence: `evidence/live-convergence-0824/M2-e2-exit/` (re-scorable with no GPU from its own
  `passes/`).
- **G-M2-4's miss was preregistered before the converger existed** (iteration 10's F3): with
  central ownership the oldest owned word has age `(L+S)/2`, so `L+S <= 12` is required and NO
  geometry in the plan's grid qualifies (10/5 floor 6.46 s, selected 10/10 8.51 s, 15/10 11.64 s,
  15/7.5 12.81 s). Measured 8.757 s trio / 10.39 s five-minute, mean 4.76 s, max 10.89 s. It is
  not a queue problem and not a regression - depth <= 1, zero refusals, base publication latency
  unchanged. Row **unsigned**, same disposition as M0d's G2 and M1's G-M1-1; no `.stop`, because
  none of plan §15's global stop conditions fired (no case-level WER regression, file mode
  unchanged, accounting exact, scorer self-tests green, no truth read). **D-M2-3 open for the
  owner**: accept 10/10 with ~8.8 s corrections, or authorise an unmeasured `L + S <= 12`
  geometry and re-run the §10.2 grid. Adding an arm now is what the preregistration forbids.
- **The five-minute case is reproducible now.** Both passes returned identical WER / DER / recall
  / segment counts on all four scored cases, including the five-minute one, which spread
  .0014 WER / .0030 DER at the M1 exit. Fewer, longer decodes give the deployed decoder fewer
  chances to flip: 128 span decodes plus 30 window decodes, and the published surface is
  dominated by the 30. Candidate 4c (5-minute noise floor) is answered at N=2 for this build.
- **Speaker quality moved without any E3 work, and it moves M3's comparators.** Trio live DER
  .127333 / .117333 / .089167 (mean **.111278**, baseline live .2235 / .1945 / .1112) and
  duration-weighted speaker accuracy .8727 / .8827 / .9108 (mean **.888722**, M3's floor .8437);
  five-minute DER **.0886**, already inside M3's `<= .0947`. Longer surface segments shrink the
  extent artifact. **M3 must restate its gates against this measurement**, or it will grade
  itself against a surface nobody serves.
- **The witness's serial cost is priced (iteration 14's D2).** A running window holds the
  session's single in-flight slot, so a base span can wait behind it: canonical queue wait p50
  0.62-0.76 ms everywhere, but p95 136-214 ms and max 649-654 ms on `lex_javier_milei`, max
  251-266 ms on the five-minute case. Never dropped, never overtaken, and well inside the 2.5 s
  span cadence. Rolling's own queue wait is the mirror: p50 .016 ms, max 133 ms (a window waiting
  for canonical work). §10.6's other quantities are in `gates.json` under `_soak_10_6`: snapshot
  bytes 12.8K (1 min) / 51.7K (5 min), trace 752 KB, base RTF .09-.12, witness RTF .030-.048.
- **M3's gates are now written and measured against (iteration 19).**
  `PREREGISTRATION-M3.md` states 14 gates, each against BOTH the PRD bound and the M2 exit
  measurement, binding on whichever is stricter - a strengthening in every row, no PRD bound
  relaxed. It fixes the arms (S1; S2 only if S1 fails), the clocks, 7 predictions, and the
  disposition rule (an unsigned row unless a plan §15 global condition fires).
- **E3's ceiling is a measured number, not a hope.** `measure_m3_baseline.py` decomposes the
  deployed DER: false alarm is .000000 everywhere, and only CONFUSION is a label a speaker
  authority could have got right - miss is speech nobody published, which no embedding recovers.
  Trio DER .111278 over a confusion-free floor of **.094833**, so a perfect speaker authority
  wins at most **.016445**; the five-minute case at most **.005900**. `lex_bill_ackman` holds
  .037167 of the trio's .049334 confusion (75.3 %); `lex_javier_milei`'s confusion is exactly
  .000000, so ANY DER movement on that case is a regression by construction.
- **S00 and collapse have baselines now**: S00 seconds .73 (3 fragments, 0.16-0.33 s, at the 29 /
  40 / 50 s turn boundaries) on bill, .56 (1 fragment) on the five-minute case, .00 elsewhere -
  all below the 0.5 s matching floor, i.e. plan §11.4 microfragments, not M3's. Exactly ONE
  collapsed two-speaker window in the whole bench: bill [20.0, 30.0), where the second voice is
  detected but published as S00. Two collapse screens are reported because the deployed 10 s grid
  is alignment-dependent - `lex_javier_milei`'s only reference turn falls exactly on a window
  boundary and produces 0 mixed windows aligned vs 3 sliding. **Gates use the sliding screen**
  (window 10 s, hop = the deployed hard cap read from each pass's manifest).
- Rest of the ladder (M3 arms, M4-M5) unimplemented; working tree carries the plan, evidence
  prototypes, and this scaffold.

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
# E2 step 1: is the text-finalization ADR still the plan's D1-D7 verbatim? (exit 0 = yes)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_adr_text_finalization.py
# E2 step 2: the §10.2-§10.4 rolling grid (add --cache-dir <bundle>/decode-cache for no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_rolling_grid.py \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \
  --windows 10/5,10/10,15/7.5,15/10 --stitches char,uniform,lexical --runs 3 \
  --output /tmp/moss-rolling-grid.json
# its five mutations, each caught by its own guard (zero MOSS requests)
prototypes/streaming-diarization/live-convergence/mutate_rolling_grid.sh \
  evidence/live-convergence-0824/M2-rolling-grid/decode-cache /tmp/grid-mutations
# E2 step 3a: does the SHIPPED converger reproduce the grid's selected arm? (exit 0 = yes, no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_production_converger.py
# its five mutations, in the production module, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_production_converger.sh /tmp/converger-mutations
# converger interface tests
.venv/bin/python -m pytest tests/test_live_transcript_convergence.py -q
# E2 step 3b: does the SHIPPED session authority publish that arm, and attribute it? (exit 0, no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_session_text_authority.py
# its five mutations, in live_session.py itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_session_authority.sh /tmp/authority-mutations
# text-revision authority tests (seven validations, projection, terminal)
.venv/bin/python -m pytest tests/test_live_text_revision.py -q
# E2 step 3c: does the refinement queue schedule the witness without delaying the base? (exit 0, no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_refinement_scheduling.py
# its five mutations, in live_arbiter.py itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_refinement_scheduling.sh /tmp/scheduling-mutations
# refinement scheduling tests (priority, one-per-session, release lifecycle)
.venv/bin/python -m pytest tests/test_live_arbiter_refinement.py tests/test_live_vad.py -q
# E2 step 4: does the real RUNTIME run the witness and land on the selected arm? (exit 0, no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_runtime_rolling.py
# its five mutations, in live_coordinator.py / live_service_runtime.py, restored on exit
prototypes/streaming-diarization/live-convergence/mutate_runtime_rolling.sh /tmp/rolling-mutations
# runtime wiring tests (dispatch, release, stop-waits, non-terminal failure, salvage gate closed,
# and since iteration 15 the §7.4 event serialization tier)
.venv/bin/python -m pytest tests/test_live_rolling_wiring.py -q
# E2 step 5: does the witness tell its whole story on the event stream? (exit 0, no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_rolling_events.py
# its six mutations, in live_coordinator.py / live_service_runtime.py, restored on exit
prototypes/streaming-diarization/live-convergence/mutate_rolling_events.sh /tmp/event-mutations
# E2 step 6: does the READER see the arm, and is the screen one replacement surface? (exit 0, no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_portal_surface.py
# its six mutations, in live_portal.py itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_portal_surface.sh /tmp/portal-mutations
# portal render tests (the surface, the replacement, S00, the missing rate, the headless browser)
.venv/bin/python -m pytest tests/test_live_portal.py -q
# E2 step 7: does the EXPORT carry the surface the reader saw? (exit 0, no GPU, node required)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_export_surface.py
# its six mutations, in live_speaker_accuracy.py / live_surface.py, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_export_surface.sh /tmp/export-mutations
# export tests (export == screen on a real runtime, the fallback, S00, the clamp, the refusals)
.venv/bin/python -m pytest tests/test_live_export_surface.py -q
# E2 EXIT: four warm-decoder passes against the running service, then the eight gates
prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m2-exit-<stamp>
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m2_exit.py \
  --fresh-root /tmp/m2-exit-<stamp> --output /tmp/m2-gates.json
# re-score the checked-in M2 exit passes instead (no GPU, no service)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m2_exit.py \
  --fresh-root evidence/live-convergence-0824/M2-e2-exit/passes
# its eight mutations, on a COPY of the passes (originals untouched)
prototypes/streaming-diarization/live-convergence/mutate_m2_exit.sh \
  evidence/live-convergence-0824/M2-e2-exit/passes /tmp/m2-mutations
# 9-clip identity floor (M3)
.venv/bin/python -m pytest tests/test_live_identity_real_corpus.py -q
# full suite checkpoint (before closing a milestone)
.venv/bin/python -m pytest tests/ -q
```

```bash
# M3 comparator table + instrument self-test (no GPU, no service; the bounds M3 is gated against)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py --output /tmp/m3.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py --selftest
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
6. ~~**M2 step 1: the text-finalization ADR**~~ - DONE iteration 9 (see Current state). Appendix B
   Q8's precondition for E2 implementation is satisfied and mechanically checked.
6b. ~~**M2 step 2: the §10.2-§10.4 grid**~~ - MEASURED iteration 10, all preregistered gates pass.
   Selected arm: **`10/10`** (10 s window, 10 s stride, no stitcher). Two owner decisions recorded
   (D-M2-1 cost-vs-quality, D-M2-2 the unreachable G6), neither blocking. Do NOT re-run the grid
   hoping for a different arm; N=3 spread is exactly zero and the selection rule was preregistered.
6c. ~~**M2 step 3 item 1: the M2 converger**~~ - SHIPPED iteration 11, reproduces the selected
   arm at 6 dp (see Current state). Do NOT re-open the geometry: `RollingGeometry` refuses an
   overlapping stride on purpose, and changing it means re-running the §10.2 grid.
6d. ~~**M2 step 3 item 2: M3 word-revision authority**~~ - SHIPPED iteration 12 (see Current
   state). The seam, the seven validations, the four §7.3 fields, the label projection and the
   extended replay tripwire all landed together, and the arm reproduces end to end through the
   real session. Do NOT re-open the projection rule: it agrees with the timeline the arm was
   selected through on 51 of 51 segments, and changing it means re-running the §10.2 grid.
6e. ~~**M2 step 3 item 3: `submit_live_refinement`**~~ - SHIPPED iteration 13 (see Current
   state). Do NOT re-open the priority order or add a capacity knob: the order is plan §6 M5's
   verbatim and the per-key rule is the bound (bundle NOTES D1/D2 record what each decision cost).
6f. ~~**M2 step 3 item 4: wire base commits into the converger**~~ - SHIPPED iteration 14 (see
   Current state). Do NOT re-open the two-adapter decision or the release-before-plan ordering:
   the first is forced by the manifest's span bound, the second is a measured defect fix that the
   trio corpus cannot see.
6g. ~~**M2 step 3 item 5: snapshot/event serialization**~~ - SHIPPED iteration 15 (see Current
   state). Do NOT add the three `terminal_finalization_*` events here: they are E4's and have no
   producer, and an event kind with no producer is a contract rather than a serialization. Do NOT
   replace G4's read-from-production vocabulary with a literal list.
6h. ~~**M2 step 3 item 6: the portal renders the surface**~~ - SHIPPED iteration 16 (see Current
   state). The PRD's "headless portal render/serialization test" landed with it: three new T2 tests
   in `tests/test_live_portal.py`, one of them driven entirely by real server payloads. Do NOT add
   render state across polls (a diff, an animation buffer, a join de-duplicator) without replacing
   the purity gate with something at least as strong, and do NOT let the page assume a sample rate.
6i. ~~**M2 step 3 item 7: the export switch**~~ - SHIPPED iteration 17 (see Current state). §10.5
   is complete. Do NOT gate the switch on `text_revision_version > 0`: the two readings agree on an
   unrevised session, measured, and a conditional export is a branch for nothing. Do NOT import
   anything from `moss_transcribe_diarize.app` into `live_speaker_accuracy.py` - the F-cert reducer
   loads it from a bare checkout with `-S`.
6j. ~~**M2 EXIT**~~ - MEASURED iteration 18, 7 of 8 gates pass (see Current state). The open
   item is G-M2-4 and it needs an owner ruling (D-M2-3), not more code: no geometry in the
   preregistered grid can pass a 6.0 s correction p95, and adding one is what the preregistration
   forbids. Do NOT re-run the passes hoping the latency falls; the floor is arithmetic. The §10.6
   soak quantities were read off the same five-minute passes (Appendix B's rescope) and are in
   `M2-e2-exit/gates.json` under `_soak_10_6`; only portal render time is still outstanding and
   it is the attended browser item.
7. ~~**M3 step 1: restate the comparators**~~ - DONE iteration 19.
   `PREREGISTRATION-M3.md` + `measure_m3_baseline.py`, verdict in
   `evidence/live-convergence-0824/M3-preregistration/`. Do NOT re-derive the bounds when an S1
   number arrives: every gate is fixed against both the PRD bound and the M2 exit, binding on
   whichever is stricter, and the PRD forbids moving one after a number is seen. Do NOT gate on
   the deployed collapse screen; it reports 0 mixed windows on `lex_javier_milei` for alignment
   reasons alone.
7b. **M3 step 2: the S1 arm - NEXT**: plan §11.1 S1 (2.5 s base only), embeddings strictly from
   witness-owned local speaker intervals (plan D5), reconciled against the existing album; the
   §6 M4 resolver is internal to `live_transcript_convergence.py` "until a second caller exists".
   The prototype (`compare_speaker_authority.py`) must print every embedded interval, cache
   hit/miss, mapping, abstention and per-resource RTF, and must decode each witness ONCE and
   reuse it - only changed segmentation earns new WeSpeaker work. Score it with
   `measure_m3_baseline.py --passes-root` against the 14 preregistered gates. Read the ceiling
   first: at most .016445 trio DER is available and three quarters of it is in one case, so an
   arm that "improves" by more than that is measuring something else. S2 only if S1 fails, and
   record that S2's premise (overlapping witnesses) does not exist at the selected 10/10
   geometry.
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
