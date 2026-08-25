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

(2026-08-25, after iteration 2)

- Deployed dev stack up: `web_cli` (pid ~32906) at `https://127.0.0.1:7861` (bearer token
  `~/.local/share/moss-transcribe-diarize/g3/shared-token`), SSH tunnel `127.0.0.1:18000` →
  4070 Ti vLLM `OpenMOSS-Team/MOSS-Transcribe-Diarize`. Service currently runs pre-campaign
  code; restart with campaign code is required before end-to-end paired reruns (record it).
- Paired baseline (deployed stack, 2026-08-24): trio FILE WER .1039 / TBSA .9106 / DER .1021 /
  spk_acc .8979 vs LIVE .1999 / .8384 / .1764 / .8236; 5-min keyu FILE .0506/.0579(DER) vs
  LIVE .1464/.1315. Artifacts + drivers: `prototypes/live-file-gap-baseline-20260824/`.
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
- Rest of the ladder (M0c-M5) unimplemented; working tree carries the plan, evidence
  prototypes, and this scaffold. `prototypes/streaming-diarization/live-convergence/` now
  exists (the campaign's throwaway-experiment home per the PRD) and holds the two M0b probes.

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
3. **M0c evaluator v2 prototype** under `prototypes/streaming-diarization/live-convergence/`
   per plan A0.3 gates. Validate: self-tests listed in PRD M0c.
4. **M0d paired re-acquisition** (needs service restart onto campaign branch first — record it).
   Validate: byte-identical file arms; hash-identical fresh live pairs; 5-min revisions visible.
5. **M1 salvage**: port `prototypes/live-file-gap-emptyspan/` P1v policy into
   `classify_live_transcript` per plan M1 seams; table-driven tests from `out/d3.json`.
6. **M2 grid** (`compare_rolling_grid.py` per plan §10.3, starting from
   `proto_context_arms.py`'s lexical stitcher) → then production per plan §10.5 order.
7. **M3 S1 speaker authority** prototype (`compare_speaker_authority.py` per plan §11.1,
   2.5 s base only) → production wiring.
8. **M4 terminal finalizer** per plan §12.3 + M4 gates on trio/3-min/5-min.
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
