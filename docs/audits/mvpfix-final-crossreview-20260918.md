# WP32 final integrated cross-review — 2026-09-18

**Review complete; not an unqualified acceptance.** Protected numeric values,
frame contract and reference tokens survived. One new terminal-accounting defect,
one confirmed pre-existing capture recovery defect, and one legacy byte-compatibility
divergence remain. A weakened optional-summary gate and historical mutation-evidence
overclaim need explicit qualification. No production fixes made.

Branch `mvpfix/wp32-final-crossreview`; reviewed
`37979e539f04d4ea740a1a94d021cd3bb894a0e2` →
`d8fa767f3ccbb577584643d7e23f80f55d92b2f5` (WP29 included).
Exact command: `git diff 37979e53..d8fa767f -- moss_transcribe_diarize frontend/src tests ':!**/frontend_assets/**'`.
106 files, 5,783 insertions, 378 deletions; TLS, qualification and visual-pack
scripts additionally inspected where brief explicitly requires them.

Mental model: each lane owns its words and voice evidence; one session assembles
them and ends capture; owner-bound storage preserves the result. Correctness needs
both the assembled result and its warnings to retain facts from **both** lanes.
Tests passing does not make skipped measurements or discarded warnings true.

## Standards axis

Independent detailed audit: [standards.md](../../evidence/mvpfix/wp32/standards.md).
12 invariant rows adjudicated; 0 protected numeric/token/parser regressions.
19 deletion-bearing test files classified exhaustively: 5 unit expectation
replacements justified by copy/saved-naming contracts; 0 Python assertions removed;
4 former E2E demo predicates replaced by stronger reference scoring; 0 added xfails.
WP10/WP12/WP17/WP27 fixture corrections have source-backed explanations.

- **F4 — Weakened gate, conditional acceptance risk:** `tests/e2e/verify_workspace.py:387,707`
  turns missing relay models into SKIP and exit 0. Counts remain honest, even 0/1
  PASS. Lead must inspect SKIP counts; if exit status alone grants acceptance,
  restore non-success for an unmeasured required row. This is not evidence that
  the summary product is broken. Two additional WP28 real-fixture cases are new
  opt-in skips, not removed coverage.
- **F5 — Historical evidence limitation:** `evidence/mvpfix/wp12/fixture-mutations.txt:116,136`
  has two terminal failures caused by a malformed mutation omitting required
  `gaps`, rather than valid refusal behavior. Three valid assertion controls,
  two invalid terminal controls: do not report 5/5 effective mutation kills.
  If that efficacy claim is needed, repair and repeat only those controls.

## Spec axis

Independent backend audit: [spec_review.md](../../evidence/mvpfix/wp32/spec_review.md),
21 rows: 18 scoped PASS, 2 QUALIFIED, 1 FAIL. Parent independently inspected
frontend consumers, capture recovery, legacy exports and visual-pack provenance.

- **F1 — P2, new defect:** `moss_transcribe_diarize/app/live_lane_decode.py:339,347`
  inherits the first successful lane's `possibly_truncated` and never combines
  the flags. System normal + microphone output cap publishes final with false
  truncation telemetry. Actual finalizer/compositor/publication probe: **2/3**
  flags correct, **3/3** proposals final. Required: OR both flags and add asymmetric
  coverage; inspect other template-only diagnostics against their declared meaning.
- **F2 — P2, pre-existing defect:** `frontend/src/capture/captureClient.ts:1110`
  marks a pre-session ended track failed but never tells ControlPanel to enter
  error. `ControlPanel.tsx:429` only offers Reset in error/terminal. Actual component
  probe: configuring, Reset absent, stale connected copy; 1/1 reproduction.
  Already recorded by WP27; blame predates base. Required: send pre-session lane
  failure through the existing cleanup/error callback and verify recovery.
- **F3 — P3, compatibility divergence:** `frontend/src/lib/transcriptKeys.ts:16`
  appends speaker identity even without `source_lane`. Saved legacy documents
  lacking segment IDs are supported (`MeetingHistory.tsx:377`). Same synthetic
  transcript: JSON **497 → 523 bytes**, speaker target keys differ; other **4/5**
  formats exactly identical. Words/timing/labels unchanged. Lead must preserve
  old keys for no-lane rows if byte compatibility is required, or explicitly
  accept the representation change. Do not claim complete legacy byte parity.

## Required review table and fresh spot-check population

Paths below are repository-relative; `app/` abbreviates `moss_transcribe_diarize/app/`,
bare frontend component names abbreviate `frontend/src/components/`, `captureClient.ts`
abbreviates `frontend/src/capture/captureClient.ts`, and `styles/` means `frontend/src/styles/`.
PASS is scoped source/test evidence,
not live host, native-model, physical-device or deployment acceptance.

| Row | Subject and evidence | Verdict | Required change / boundary |
|---|---|---|---|
| V1 | `moss_transcribe_diarize/phase2_acceptance.py:246`; `app/live_identity_album.py:45`; `app/live_provider_bundle.py:1064,1080,1376`; `ControlPanel.tsx:69`; `captureClient.ts:174`; `styles/index.css:91`; Standards S-I1–5,12 | PASS | QUALITY_BOUNDS, score/margin, admission/birth values/readers, rms>0, SILENCE_RMS and root tokens unchanged. Manifest snapshots do not prove running-service config. |
| V2 | `app/live_service_runtime.py:668,900`; `app/live_tape.py:270`; `app/live_coordinator.py:518`; `app/live_lane_contract.py:260`; `tests/phase2/test_acceptance_locator_sentinels.py:69`; Standards S-I6–11 | PASS, scoped | Queue and each tape cap preserved; mixed+two lane tapes may use 3× cap. Nine keys/two-Refresh unchanged. UI Stop remains 5 s; helper lease disarms on accepted Stop intentionally. Server drain infinity predates campaign. |
| V3 | Standards S-T1–6,8–23; `test-deletion-diff.txt`; WP10/12/17/27 retained evidence | PASS | 19 deletion-bearing files, 5 legitimate unit expectation replacements, zero Python assertions deleted. Five WP17 reference words independently restored, remaining additions still scored as errors. Source adjudication, not new listening. |
| V4 | `tests/e2e/verify_workspace.py:387,707`; `tests/test_file_resolver_performance.py:127`; WP12 mutation log `:116,136` | QUALIFIED / F4,F5 | 1 weakened E2E gate, 2 new opt-in skip cases, 0 xfails. Preserve SKIP denominator; correct mutation-efficacy claim. |
| V5 | `app/phase2.py:874,2018,2129`; `app/phase2_file.py:326,424`; `app/phase2_url.py:34,98`; `app/live_capture_guard.py:20`; Spec S01–09 | PASS, scoped | New meeting routes retain owner binding (foreign 404); failure/notice strings fixed, guard/lane telemetry finite/numeric. URL HTTP(S)/redirect policy unchanged; fixed User-Agent added; private-network URLs already allowed. No new SSRF guarantees. |
| V6 | `ops/tls/renew.py:24,61,123`; `tools/qualify/run.py:79,119,413`; `prototypes/ui-signoff-pack/live_browser.py:12,49`; `evidence/mvpfix/wp24/build-identity.json:5` | PASS with privacy boundary | TLS/config commands use argv, no shell interpolation; secret content not logged. Qualification metadata intentionally includes local paths/loopback URLs. Visual pack includes local worktree path and public-corpus transcript text. These artifacts are not universally content/path-free; no private-user transcript/credential leak demonstrated. |
| V7 | `app/live_lane_decode.py:245,312`; `app/live_identity.py:93`; `app/speaker_identity.py:602`; `app/live_service_runtime.py:1176`; Spec S10–15 | PASS, scoped | Lane jobs own separate state; results join before single publication. Interval embeddings preserve reduction order, album decisions serial; executor exceptions join workers, terminal finally releases tapes. Native hang/real ONNX parallel parity unmeasured here. |
| V8 | `app/runner_composition.py:99,184`; `tests/phase2/test_runner_composition.py:174`; `tests/test_live_lane_decode.py:564`; `tests/phase2/test_lane_consumer_store.py:13`; `frontend/src/lib/transcriptKeys.ts:16` | QUALIFIED / F3 | Legacy selector/mono producer preserved; no-lane document reopen covered. Exact-zero dispatch intentionally changed. Real ASR byte parity unmeasured; legacy JSON key parity specifically false. |
| V9 | `frontend/src/components/MeetingHistory.tsx:222`; `frontend/src/lib/fileUpload.ts:24`; `ControlPanel.tsx:75,429`; `captureClient.ts:1110` | QUALIFIED / F2 | New strings use JSX/textContent; no production dangerouslySetInnerHTML/innerHTML sink found. WP3/WP27 errors retain Reset, but pre-session ended track still lacks it. |
| V10 | `app/live_lane_decode.py:339,347`; `app/live_transcript_convergence.py:1109`; `evidence/mvpfix/wp32/spec_probe.json` | FAIL / F1 | Microphone-only truncation lost; actual native finalizer plus session publication reproduces. Aggregate the flag, then rerun asymmetric controls. |

Table totals: **10 adjudicated rows: 6 scoped PASS, 3 QUALIFIED, 1 FAIL**.
Finding totals by axis: Standards **1 gate qualification + 1 evidence limitation**;
Spec **1 new product defect + 1 pre-existing product defect + 1 compatibility divergence**.
No trivial safe fix was identified; all findings remain for lead disposition.

## Verification and measurements

Evidence root: `evidence/mvpfix/wp32/`; full commands and decisions in `NOTES.md`.
Python import resolved inside this worktree, using COMMON's interpreter and
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`. Temp/caches remained worktree-local.

| Check | Exact result |
|---|---|
| Entire Python suite | 1,941 passed; 4 skipped; 21 warnings; 37 subtests passed; 182.76 s |
| Entire frontend suite | 265 passed / 28 files; 2.95 s |
| TypeScript typecheck | exit 0 |
| Backend focused review suite | 108 passed; 2 skipped; 4 warnings; 12.29 s |
| Legacy export prototype | 4/5 formats byte-identical; JSON 497/523 bytes |
| Pre-session ended-track prototype | 1/1 defect witness; 23 unrelated cases filtered, not coverage passes |
| Asymmetric truncation prototype | 2/3 flags correct; 3/3 proposals applied/final |

The four full-suite skips are two WP28 real WAV parity cases plus existing external
identity/F-cert corpora. Their reasons were reproduced with `-rs`; they are not
passing measurements. No full-suite failures. Initial Reset probe lacked visible
console state; a retained repeat exposed it via stdout. Automated probes replace
interactive TUI for the read-mostly review and are retained as the audit bench.
No source/assets changed, so no rebuild; no GPU/shared service/physical capture.

Completed [fresh-context verification](../verify/wp32/VERIFY-RESULT.md): **10/10
audit statements accurate**, with F1–F5 unresolved; not product acceptance.
Fresh full suites also passed: Python 1941 passed/4 skipped/21 warnings/37 subtests
in 184.44 s; frontend 265 passed/28 files in 2.66 s; typecheck exit 0.
