# MOSS comparison baseline (recorded, zero GPU)

**Use H1 #3 deployed quality as the six-case comparator.** It ran 6 public cases twice (forward, then reverse), 12 sessions, 1,239.987 audio seconds and 116 successful rolling windows at 1.0x. SHA `8d8fb682884bd29369879698d8233a1b281b77d7`. Source: `/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/r6-h1c-20260924T013646Z/20260924T013946Z-8d8fb68/raw/deployed-collector/artifacts/quality/content-free-metrics.json`. Complete numeric per-case, category, and weighted values are in `evidence/P62/moss-baseline.json`.

## Same-population H1 macro

Each value is the unweighted mean of 12 case passes; cases have unequal durations. `immediate` is the snapshot immediately before Stop, `settled` is drained rolling work before Stop, and `final` is the completed post-Stop surface. Production definitions: `live_service_replay.py`, `measure_three_surfaces.py:320`, `live_speaker_accuracy.py`, `evaluation.py`, `evaluator_v2.py`, and `phase2_acceptance_external.py:3634`.

| Metric | Surface | H1 macro | H1 bound | Definition |
| --- | --- | ---: | ---: | --- |
| immediate_wer | immediate | 0.164458 | ≤0.166655 | Word error rate from production text alignment. |
| settled_wer | settled | 0.137097 | ≤0.140442 | Same word error rate after rolling work drains. |
| recall | settled | 0.931782 | ≥0.929636 | `score_v2` content recall on matched reference words. |
| time_speaker_attribution | settled | 0.877554 | ≥0.876970 | `calculate_tbsa` composite time and speaker attribution. |
| diarization_error_rate | settled | 0.144626 | ≤0.161430 | **Ruled D45b DER**: raw DER less only S00 confusion under that axis's fixed optimal speaker mapping. |
| diarization_error_rate_raw | settled | 0.171344 | no bound | Raw transcript-time DER from production diarization scorer. |
| matched_speaker_accuracy | settled | 0.904807 | ≥0.911512 | `score_v2` matched-word speaker accuracy; H1 exception needs separate qualification. |
| reference_speech_der | settled | 0.121778 | ≤0.134804 | Ruled DER on reference speech intersected with WebRTC VAD speech regions. |
| reference_speech_der_raw | settled | 0.145963 | no bound | Raw value on that reference-speech axis. |
| final_wer | final | 0.095074 | ≤0.095074 | Word error rate after terminal whole-recording revision. |

Bounds come from `moss_transcribe_diarize/phase2_acceptance.py:246`; they are H1 acceptance bounds, **not** the new Gemini D6 bars. H1's settled DER macro 0.144626 is a ruled value; raw is 0.171344. The Gemini D6 live bar is strictly below 0.145, final DER at most 0.110. H1's final **DER is not among the cited 8 acceptance metrics**. Derived directly from its 12 retained per-case final DER values, the final macro is **0.110022** (duration-weighted **0.107954**); the macro narrowly exceeds the new 0.110 bar.

H1's matched-word speaker accuracy (0.904807) is below its 0.911512 strict bound. The qualification rule at `phase2_acceptance.py:256` admits a documented relative-tolerance exception within 5% for a complete clean run; keep that exception visible when comparing results.

Duration-weighted settled values use each case pass's audio seconds as weights, over the same 1,239.987 seconds: DER 0.134373 ruled / 0.164951 raw; reference-speech DER 0.113826 ruled / 0.141626 raw; WER 0.127700; time-speaker attribution 0.883404; content recall 0.937357; matched-word speaker accuracy 0.906832. They are **not interchangeable** with the H1 macro or D6 macro bar. Per-category and all 12 per-case numbers are preserved in `moss-baseline.json`.

The scorer-equivalence receipt `evidence/P62/scorer-equivalence.json` re-scored retained Bill Ackman pass-1 speaker intervals with production `_quality_speaker_intervals`: raw DER 0.140000, D45b ruled DER 0.121167, reference-speech raw 0.124172, ruled 0.105337; all diagnostic fields exactly match H1. The retained intervals permit speaker-timing equivalence; they omit words, so word error rate cannot be reconstructed from that receipt alone.

## Other recorded MOSS facts

| Population | Recorded result | Comparison limit |
| --- | --- | --- |
| Early MacStudio local 50 s probe at `c6124fcc` | First text 2.34 s; coverage p50 2.29 s; label p50 2.49 s. Reported in `docs/handoffs/auto-mvp-0911-handback.md:241`. | Original scratch probe is outside this checkout. Its clock subtracts the first emitted segment start; the P6.2 bucket latency clock is different. Directional only. |
| Real E1, 302 s, 3 system voices plus 1 synthetic microphone voice, SHA `8d8fb682` | At Stop: 11 visible labels, 13 canonical speakers, 32.360 visible slice boundaries/min, 0 rolling decode failures. | No timed reference, so no DER/WER. System-plus-mic population differs from H1's silent microphone. Source: `.../dx-replay/real-E1-001/{summary,analysis}.json`. |
| Real E2, same 302 s family | 11 visible labels, 13 canonical speakers, 32.384 boundaries/min, 0 rolling failures. | Same limits. Source: `.../dx-replay/real-E2-001/{summary,analysis}.json`. |
| Real E3, same 302 s family | 6 visible labels, 7 canonical speakers, 20.635 boundaries/min, **30 rolling failures**. | This changed runtime behavior and is not the baseline. Source: `.../dx-replay/real-E3-001/{summary,analysis}.json`. |

The `dx-combined` directory contains 17 `summary.json` arms; every one reports `mode: stub` and changed E3 settings. Their `analysis.json` numbers are **not** a real-decoder MOSS baseline. No physical mic or private operator recording is used here.

## Gemini word-offset anomaly accounting

Lead note `bc567bb2`: `common/gemini_common.py` now reports `WindowResult.timing_anomalies={clamped,dropped}` after repairing invalid word offsets. This pane makes no Gemini calls, so it has no per-call anomaly denominator:

| Arm | Gemini calls | Clamped per call | Dropped per call |
| --- | ---: | ---: | ---: |
| P6.2 MOSS baseline and loopback stub | 0 | UNMEASURED | UNMEASURED |

When the Gemini runtime is measured, report each call's `clamped` and `dropped` counts and the total per-call rates from its own ledger; the generic HTTP quality receipt cannot infer those internal parser counts.

## Corpus custody and comparability

The committed H1 corpus manifest has SHA `80fc15bd730f7aa44d8a69aa6e7e00aaf43ed54e2af8a03abc2c8934d7438d7c`. On this checkout, the Bill Ackman and Keyu Jin reference JSONL files **do not match** that manifest, although all 6 audio files do. Their manifest-matching versions are in Git at `966d250b^`. `run_quality.py` restores only those 2 references into scratch and re-runs the production input verifier; it never changes the worktree corpus. This is necessary to score the H1 truth set.

The optional `--mic` arm changes the population and does not emit an H1-comparable 12-session projection. Stub text is meaningless and its scored numbers are plumbing evidence only. A future Gemini runtime must keep the public HTTP snapshot/event/Stop shape before this harness can measure it.

Lead corpus ruling (2026-09-28): `accept6` is primary. The complete-reference extension uses `gold9`, the 300 s `benchmark_5m` lex Bill Ackman, Keyu Jin, and Javier Milei cases, and the complete 1800 s `long30m` lex Bill Ackman case. `bench5m acquired_*` references are sparse (example: acquired Alphabet covers 78.9/300 s); `long30m acquired_jamie_dimon` covers 374/1800 s. Their DER, miss, and WER are diagnostic only. This pane's H1 collector does not score those tiers.
