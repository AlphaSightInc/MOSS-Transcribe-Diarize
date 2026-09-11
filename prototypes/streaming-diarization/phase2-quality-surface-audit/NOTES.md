# Phase-2 quality surface investigation — 2026-09-11

**Verdict: premature-settling risk is verified; a convergence-algorithm regression was not reproduced. The complete Account/provider (a)/(b) verdict remains unresolved without round-5 per-case traces or a fresh end-to-end replay.**

This is an offline investigation at `ab6fdc3d` plus diagnostic-only changes. No deployment-host operations or provider requests. `QUALITY_BOUNDS`, its validation comparisons, and identity policy were not changed. The supplied bound provenance is accepted, not re-investigated.

## F1 — What the collector actually scores

All eight metrics read `snapshot.session.effective_transcript` through `live_speaker_accuracy.hypothesis_from_live_snapshot`; only old snapshots lacking that field use committed spans. Phase-2 macro assembly and validator independently use the same surface mapping.

| Metric | Capture | When |
|---|---|---|
| immediate_wer | pre_stop_immediate WER | After all frames, before settle wait and before Stop |
| settled_wer | pre_stop_settled WER | After canonical queue drains or 30-second timeout, before Stop |
| recall | pre_stop_settled content_recall | Same |
| time_speaker_attribution | pre_stop_settled tbsa | Same |
| diarization_error_rate | pre_stop_settled der | Same |
| matched_speaker_accuracy | pre_stop_settled matched_word_speaker_accuracy | Same |
| reference_speech_der | pre_stop_settled reference_speech_der | Same |
| final_wer | post_stop_final WER | After Stop and terminal-state polling, up to 300 seconds |

Evidence: `phase2_acceptance_external.py::quality_corpus`, `_quality_projection`; `phase2_acceptance.py::_validate_quality`; `live-surface-optimization/measure_three_surfaces.py::SurfaceCaptureService`; `live_service_replay.py::_await_terminal_finalization`.

## F2 — “Settled” and “final” do not guarantee successful convergence

The wait condition is `pending_work_items`, which `LiveServiceRuntime._pending_work_items` deliberately counts as canonical work only. `_has_unresolved_work_locked` separately includes rolling queued/running work. Thus the collector can stop waiting while rolling corrections remain. A 30-second timeout also still produces a “settled” capture. Neither behavior is an immediate/settled field mix-up.

The same canonical-only wait predates the campaign: it is not by itself proof of a new regression or the cause of all eight misses. Immediate WER is captured before this wait and cannot be repaired by waiting longer.

Terminal polling treats `final`, `failed`, `unavailable`, and `not_started` as settled lifecycle states. Failed/unavailable terminal passes can therefore be scored under `final_wer` using their retained rolling surface. There is no assertion in quality_corpus that finalization_status must equal final. This could explain a final-WER shortfall, but round-5 status is unknown locally. No gate was changed.

## F3 — Stop addendum: a failed Stop cannot yield a completed quality macro

Controlled invocation of the real SurfaceCaptureService with Stop raising produced pre_stop_immediate and pre_stop_settled, propagated the exception, and produced no post_stop_final. The focused producer test also proves a replay failure prevents a 12-case aggregate/content-free metrics artifact.

Quality replay creates fresh sessions, invokes Stop with deadline=5 seconds, and propagates transport/service exceptions. The collector does not swallow that exception or reuse another predicate’s transcript. Therefore, under this code, a returned 12-session quality macro contradicts “quality Stop never completed.” This does not prove successful finalization: failed/unavailable finalization remains possible.

`meeting_modes_history_restart` is a different path: it reuses `_live_id("a")`, waits for a file/URL batch, then sends Stop with no JSON body. The shared route defaults omitted deadline to zero seconds. A pending drain can therefore return HTTP 409. A stale/shared session may also fail; the old message discarded the status and body, so the exact host refusal cannot be reconstructed from that message alone.

`audio_durability_download` calls that same history predicate when its prerequisite meeting lists are empty. Its identical Stop message is not independent evidence of a second failing Stop. The observer-history failure does not identify a quality session. operator_control is independent, per the second addendum.

Changes retain Stop HTTP status and its zero-deadline context. The Stop request itself was not changed. Next quality results retain content-free capture times, queue/span counts, accepted/accounted samples, revision counters, wait/drain state, and finalization status. Threshold rejection now reports every measured value, direction, and unchanged bound; the bare failure was a boolean gate rejection, not a lost exception.

## F4 — Current convergence replay, all six frozen cases

Command: `.venv/bin/python prototypes/streaming-diarization/phase2-quality-surface-audit/probe.py`.

The probe extends the standing verify_production_converger/sweep bench. It streams each frozen WAV in 8,000-sample frames through the CURRENT RollingTranscriptConverger, using the two retained sweep decode caches, the existing frozen canonical speaker timeline, and the retained canonical tail where no full rolling window exists. No new identity policy, reference-driven selection, or provider calls. All 122 planned windows completed; zero failed/stale windows. Both passes agree.

**Scope:** this executes current convergence planning/parsing/proposals, but uses the bench’s accepting session stub and frozen upstream identity/decoder output. It does NOT replay current Account scheduling, current identity embeddings, or a fresh terminal model decode. Successful proposal replay is not end-to-end production qualification.

| Case | Windows/pass | Archived immediate WER, rescored now | Archived settled WER, rescored now | Current drained rolling WER | Archived final WER, rescored now |
|---|---:|---:|---:|---:|---:|
| mono_javier_intro_50s | 5 | 0.194690 | 0.159292 | 0.106195 | 0.097345 |
| interview_bill_ackman_60s | 6 | 0.267045 | 0.204545 | 0.198864 | 0.159091 |
| interview_keyu_jin_60s | 6 | 0.143885 | 0.115108 | 0.100719 | 0.064748 |
| interview_adam_frank_180s | 18 | 0.146893 | 0.133710 | 0.122411 | 0.126177 |
| discussion_jamie_dimon_180s | 18 | 0.111498 | 0.094077 | 0.094077 | 0.069686 |
| discussion_rtfl_90s | 8 | 0.135922 | 0.135922 | 0.135922 | 0.053398 |

The archived columns are a scorer/extraction control, not a newly generated transcript. Rescoring preserved their original macro results. The current drained rolling WER matches the campaign’s Stop-return WER case by case; those corrections are still producible from the saved decodes.

| Case | Current recall | Current time-speaker attribution | Current DER | Current matched-speaker accuracy | Current reference-speech DER |
|---|---:|---:|---:|---:|---:|
| mono_javier_intro_50s | 0.911504 | 0.928601 | 0.059800 | 0.911504 | 0.036515 |
| interview_bill_ackman_60s | 0.926136 | 0.878405 | 0.126667 | 0.920455 | 0.111092 |
| interview_keyu_jin_60s | 0.985612 | 0.905494 | 0.097333 | 0.985612 | 0.083476 |
| interview_adam_frank_180s | 0.951036 | 0.913315 | 0.079889 | 0.951036 | 0.066209 |
| discussion_jamie_dimon_180s | 0.945993 | 0.919907 | 0.092453 | 0.930314 | 0.081181 |
| discussion_rtfl_90s | 0.922330 | 0.800622 | 0.430644 | 0.834951 | 0.352785 |

Current drained macro: WER **0.126364667**, recall **0.940435167**, time-speaker attribution **0.891173083**, DER **0.147450417**, matched-speaker accuracy **0.922312000**, reference-speech DER **0.121527500**. These six values clear their unchanged numeric limits; this conditional bench is not eligible evidence for the Account gate.

**Javier is not disproportionately bad in this replay:** its WER is 0.106195; Bill Ackman is worst at 0.198864. RTFL is worst on speaker attribution (DER 0.430644). Round-5 per-case scores and current microphone recordings are unavailable here; their distribution cannot be inferred from a macro. The user’s microphone split cannot honestly be attributed to this monologue result.

## F5 — Decision and remaining evidence

The isolated convergence replay does not trigger the brief’s “bench also fails to converge” condition. No bisected regression commit is claimed. A full binary verdict would require the actual round-5 snapshots/events (including terminal_finalization_wait and terminal failures), or a fresh Account-versus-legacy replay against a locally available provider. The local sweep service/provider ports have no listeners; no host access was attempted. The standalone proto_real_replay uses different golden corpora and policy grids, so it cannot substitute for the specified six-case comparison.

Needed from the host owner, copied locally: quality/content-free-metrics.json and quality/pass-{1,2}/<case>/run-001/trace.jsonl, plus retained Stop response status/details for the shared history predicate. Inspect rolling queued/completed/refused events and terminal finalization state before choosing a product fix. Do not weaken a bound.

## F6 — Requested independent probe fixes

- vLLM: recognize the deployed vllm:kv_cache_usage_perc gauge, while retaining the previously supported gpu_cache_usage_perc name. Use actual finite values, maximum across engines. Missing/non-finite gauges still fail.
- MP3: write downloaded bytes to a mode-0600 temporary seekable file, probe it, then delete it. Duration remains mandatory. A real encoded MP3 and missing-duration negative tests cover the behavior.

## Validation

`.venv/bin/python -m pytest tests -q`: 1,219 passed, 2 skipped, 37 subtests passed. The new metric/MP3 tests first reproduced the defects (four failures); they then passed. `npm --prefix frontend test`: 155 passed. AST comparison confirms QUALITY_BOUNDS and _validate_quality are unchanged. No host deployment or qualification claim. Raw content-free replay numbers are in results.json.

## Additional source finding

The external browser regression check still expected workspace section order [file, live, history], while UX commit ab6fdc3d adds voiceprints as the fourth section. Corrected the stale expected order to include voiceprints. It did not cause round 5, which used 513c9d5f. The existing real-browser workspace test checks the four-section order on desktop and mobile.
