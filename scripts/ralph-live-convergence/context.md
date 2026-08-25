# Context - Live-mode convergence campaign

## Ground

- Repo: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize` — branch `ralph/live-convergence-0824`
- Read before editing: `docs/plans/live-mode-convergence-implementation-20260824.md`
  (the spec; **Appendix B overrides the body; Appendix A is the runbook + code map**),
  `AGENTS.md`, `docs/design-streaming-diarization.md` §2/§7.
- Key code paths and why they matter:
  - `moss_transcribe_diarize/live_service_replay.py:~842-935` — the payload reconstructors
    (field-complete since iteration 1; keep them so); terminal-trace write at `:488`.
  - `moss_transcribe_diarize/app/vllm_runner.py:_validate_transcription_response` +
    `app/live_adapters.py:307` — the decode seam. The disposition collapse is fixed (iteration 2);
    what remains here is M1: read `exc.text` at the adapter catch and route it through
    `classify_live_transcript`.
  - `app/live_span_bounds.py` — clamp-never-refuse precedent; M1 `classify_live_transcript` home.
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

(2026-08-25, after iteration 4)

- Deployed dev stack up: `web_cli` **pid 82706, restarted 2026-08-25 00:43:48 onto campaign
  code** (repo working tree @ `e291624`) at `https://127.0.0.1:7861` (bearer token
  `~/.local/share/moss-transcribe-diarize/g3/shared-token`), SSH tunnel `127.0.0.1:18000` →
  4070 Ti vLLM `OpenMOSS-Team/MOSS-Transcribe-Diarize`. Descriptor identical before and after
  the restart (`evidence/.../M0d-paired-reacquisition/restart-{pre,post}.txt`) — the build
  changed and nothing else. Restart again after any production change, and record it.
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
- **The raw unparseable text now stops at the adapter seam** (`exc.text`), deliberately not carried
  onto `InferenceTranscript`: telemetry must never see meeting words, and M1's
  `classify_live_transcript` is the one caller entitled to read it. That is the M1 wiring point.
- Refusal boilerplate is *not* distinguished yet -- it classifies as `unparseable_text`, correctly,
  because refusal detection belongs to `classify_live_transcript` (plan §6 M1). M1 adds a verdict
  on top of this vocabulary, not beside it.
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
- **F3 (new defect, top candidate): every 5-minute replay trace is truncated, the checked-in
  baseline included.** `bounds.max_events = 1000` is a `deque(maxlen=…)` at
  `app/live_service_runtime.py:499`, and `live_service_replay.py:446` drains once with
  `since_seq=0` *after* the session ends. A 5-minute session emits ~1600 events, so the first
  ~30 s is evicted before anyone reads it: traces start at frame 60 / span 13 and hold 114 of
  127 spans. Metrics are unaffected (the hypothesis comes from the terminal snapshot), but every
  span-level analysis of the 5-minute case reads a truncated window — M1's salvage corpus, M4's
  sample accounting (G10), and `_canonical_decode_rtf_evaluation`.
- **F4: extent jitter is provider-side and survives identical decodes.** On the trio, where every
  span and every decode matched, published boundaries still moved ±10-20 ms (one webrtcvad
  frame) on 3/26 keyu and 6/32 jamie segments, and one jamie segment changed speaker label. WER
  is blind to it; DER/TSA/coverage are not. A ±.002 per-case DER difference is inside this noise
  until the floor is quantified.
- Rest of the ladder (M1-M5) unimplemented; working tree carries the plan, evidence
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
4b. **F3 trace truncation** (NEW, highest-leverage open item). `bounds.max_events = 1000`
   (`app/live_service_runtime.py:499`) silently drops the first ~30 s of every 5-minute session's
   event stream because `live_service_replay.py:446` drains once with `since_seq=0` after the
   session ends. Fix belongs on the replay client — drain incrementally during the session using
   the `since_seq` it already has — not by raising the bound, which only moves the cliff. Gate:
   a fresh 5-minute trace starts at frame 0 / span 0 and holds all 127 spans; 60-second traces
   byte-unchanged; file mode untouched (no production module changes). M1's salvage corpus and
   M4's G10 accounting both read this stream, so it comes first.
4c. **Noise floor for per-case gates** (do before M2/M3 gate readings, not before M1). N>=4
   repeats of the 5-minute pair to turn "the 5-minute case can flip" into a spread. Needed
   because M1 gates "no per-case WER regression" and M3 gates per-case DER, and F4 shows
   extents move +-10-20 ms even when every span and decode match.
5. **M1 salvage**: port `prototypes/live-file-gap-emptyspan/` P1v policy into
   `classify_live_transcript` per plan M1 seams; table-driven tests from `out/d3.json`.
   Amended PRD adds: run the §9.1 O1-vs-O2 comparison first (prefer O1 on a full-corpus
   match); fixed-point + salvager-emitted-intervals-only checks are part of the gate.
6. **M2 ADR then grid**: first write the accepted text-finalization ADR from plan D1-D7 verbatim
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
