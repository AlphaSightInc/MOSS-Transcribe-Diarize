# WP32 spec/backend adversarial review

Reviewed exact two-dot diff `37979e53..d8fa767f` in the assigned worktree, with COMMON, WP32 and execution-plan sections 1–2. Production changes untouched. No GPU, service, network, deployment, or cross-worktree mutation.

## Confirmed finding

**S-F1 — P2: microphone-only terminal truncation disappears from integrated telemetry.**

- Location: `moss_transcribe_diarize/app/live_lane_decode.py:339-371` (especially template selection and accounting replacement at 339–350).
- Requirement: WP32 item 3 requires review of lane telemetry; execution-plan section 1 R5 requires acceptance through Stop and saved/exported output, with honest observed result. Existing terminal accounting explicitly records `possibly_truncated` (`live_transcript_convergence.py:1109`).
- Reachable trigger: the system terminal decode completes normally while the microphone decoder reaches its output cap. Each native finalizer correctly records its own result. Aggregation selects the system result as template and never combines the truncation flags.
- Reproduction: `spec_probe.py` invokes the actual `finalize_lanes`, actual `TerminalTranscriptFinalizer`, and actual session publication with a deterministic runner returning the ordinary `possibly_truncated` field. Controls: neither lane truncated → false; system-only → true. Falsifier: microphone-only → **false**, expected true. All three proposals apply and become `final`; flag correctness **2/3**.
- Required change: OR `possibly_truncated` across lane results and add an asymmetric regression. Review other template-only fields (`window_diagnostics`, failure diagnostics, seam counters) for their declared aggregate meaning; do not silently assert their totals. No production fix applied because WP32 authorizes only trivial defects.
- Evidence: `spec_probe.py`, `spec_probe.json`. Probe intentionally asserts reproduction of the current defect, not desired behavior.

## Review rows

| ID | Subject / line evidence | Verdict | Required change / limit |
|---|---|---|---|
| S01 | `phase2.py:874-893,961-983,1080-1113`: outcome joins/write predicates retain account and authority generation | PASS | No owner bypass introduced. |
| S02 | `phase2_file.py:326-359,424-455,502-509`: failure/notice producers | PASS | Fixed strings/type-safe codes; private provider exception text is not retained. |
| S03 | `phase2_url.py:74-92`: HTTP errors translated | PASS | 403/404/timeouts get fixed messages; other errors generic. |
| S04 | `phase2_url.py:34-39,98-121`: scheme, redirects, User-Agent | PASS with explicit boundary | UA changed to fixed Mozilla-compatible value. HTTP(S)-only and bounded manual redirects unchanged. Private-network destinations were already allowed; no new SSRF protection claim. |
| S05 | `phase2_audio.py:287-294`: FFmpeg recovered-prefix notice | PASS | Constant notice only; raw stderr and source paths not copied. |
| S06 | `live_capture_guard.py:20-46`, `live_transport.py:953-965`: capture telemetry | PASS | Fixed labels, boolean/numeric signal statistics. Snapshot remains behind existing adapter authorization. |
| S07 | `live_session.py:847-875`, `phase2_live.py:1312-1317`: lane labels | PASS | Revision labels enum-constrained; published source labels derive from the two internal lanes. Absent lane stays absent in saved document. |
| S08 | `phase2.py:2018-2037`: new file admission endpoint | PASS | Account authentication precedes capacity work; size-only route names no meeting and exposes no foreign resource. |
| S09 | `phase2.py:2129-2147`, `phase2_speaker_identity.py:184-205,229-261,305-321`: saved rename | PASS | Owned handle opened first; fallback preserves account/generation/status predicates; name operations serialize. Foreign rename test returns 404. |
| S10 | `live_lane_decode.py:245-320`: terminal lane parallelism | PASS on reviewed seam | Separate lane tapes/preparers; independent locals; deterministic ordered assembly; single publication after both jobs. Test proves two jobs overlap and no early publication. |
| S11 | `live_identity.py:93-109`, `live_provider_bundle.py:633-647,1016-1023`: lane albums/readers | PASS | Fresh lane provider state; revision readers read settled canonical references and own their pending vectors. |
| S12 | `speaker_identity.py:602-630`, `file_identity_album.py:80-153`: parallel interval embeddings | PASS with provider limit | Session selected before interval fanout; ordered map keeps reduction order; albums/sweeps local to resolve and serial. Failure test checks abstention plus no surviving workers. Real ONNX concurrency/bitwise equivalence not rerun. |
| S13 | `live_service_runtime.py:1176-1214`, `live_coordinator.py:1144-1149`: terminal exceptions/release | PASS | Exceptions convert to failed finalization; finally releases mixed and both lane tapes and wakes waiters. |
| S14 | `live_transport.py:246-269`, `live_service_runtime.py:900-995`: accepted Stop lease | PASS with boundedness limit | Lease authority ends once capture closes; background drain survives caller deadline. Stop drain remains `end_time=inf`, already present at base; correctness depends on provider completion/failure. No new absolute server deadline established. Focused 12-case lease suite passes including caller deadline, disconnect, failure, restart. |
| S15 | `live_lane_decode.py:249-256,321-355`, `phase2_live.py:794-811`: tape exhaustion | PASS | Missing lane tape keeps its committed words; both missing gives unavailable; aggregated gap count drives constant persisted notice. Unit exhaustion cases pass. Parent full suite covers HTTP/MP3 durability. |
| S16 | `ops/tls/renew.py:24-37,43-47,61-83,123-126` | PASS | Config parsed as literal; subprocess argv lists, no shell; token passed by file environment; error logging only exception type. No host operation performed. |
| S17 | `scripts/mvpfix-qualify.sh:4-21`, `tools/qualify/run.py:119-156,235-284` | PASS on config injection | Quoted shell executable/arguments and Python argv lists; configured ladder path is an explicit operator-selected Python script. No shell interpolation from config. |
| S18 | `tools/qualify/run.py:79-84,159-164,413-418` | QUALIFIED privacy boundary | Bundle intentionally retains local checkout path, dirty relative paths, loopback URLs, optional comparison path. Therefore metadata is **not universally path/URL-free**. It is local engineering evidence, not meeting telemetry. Raw provider logs remain ignored scratch. No secret-value exposure demonstrated. |
| S19 | `runner_composition.py:99-109,184-198`, `tests/phase2/test_runner_composition.py:174-190` | PASS legacy selection | `file_identity='legacy'` constructs the previous `IdentityResolver(IdentityResolverConfig())`; terminal gets legacy resolver over the same decoder. Constructor/isolation test passes. No real ASR base/head byte comparison run. |
| S20 | `live_coordinator.py:604-610`, `live_service_runtime.py:1182-1190`, `live_session.py:907-943` | QUALIFIED mono compatibility | No-lane work uses old producer/finalizer path; mono same-lane interval rules remain. New digital-silence refusal deliberately changes zero-input behavior. Full byte compatibility across all old documents/exports cannot be claimed; parent independently reviews export shape. |
| S21 | `live_lane_decode.py:339-371` | FAIL S-F1 | Asymmetric truncation flag loss, above. |

Summary: 18 PASS (some explicitly scoped), 2 QUALIFIED, 1 FAIL. None is proof of attended/browser/GPU acceptance.

## Commands and falsifiers

Before probes: expected failure = private exception leakage, foreign-owner access, lane-state mixing/early publication, abandoned workers, lease-induced Stop interruption, changed legacy constructor, TLS config execution. A failure would become a cited lead finding; no speculative hardening proposed.

Import check with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` resolved inside the assigned worktree.

Focused command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=evidence/mvpfix/wp32/spec-test-tmp tests/phase2/test_file_failure_reasons.py tests/phase2/test_saved_speaker_naming.py tests/phase2/test_accepted_stop_lease.py tests/test_live_lane_decode.py tests/test_file_resolver_performance.py tests/phase2/test_runner_composition.py tests/phase2/test_tls_preparation.py
```

Result: **108 passed, 2 skipped, 4 warnings, 12.29 s**, retained `spec_tests.log`. Skips are explicit real 6-/30-minute audio fixture opt-ins, not passing evidence. Generated fixture/audio directory removed after test completion; only content-free log and synthetic probe retained.

Truncation probe command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/mvpfix/wp32/spec_probe.py
```

No newly proposed algorithm, threshold, or policy. Review probe is throwaway evidence only. Fresh `/new` ten-row verification belongs to parent WP32 orchestration.
