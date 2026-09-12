# Content-boundary audit — 2026-09-12

**Confirmed violations fixed.** Removed 402 newly committed evidence files and 16
speaker-embedding caches. Retained 223 content-free evidence files. Fixed writers
that could recreate the leaks; no transcription, identity, scoring or acceptance
pass/fail criteria changed. Numeric quality/identity policy is untouched.

## Scope and boundary

Pinned comparison: `git diff c93395fe..e03d6a31`, 917 changed paths. Inspected all
625 changed `evidence/` files, changed audit documents, 59 prototype JSON/JSONL
schemas and their producers, plus diagnostic logs/events/journals, browser evidence
and bundle construction. The code-review standards and spec checks independently
traced writers and inspected artifacts; this report consolidates their violations.

Allowed retention is opaque identifiers, fixed statuses/operations, numeric counts,
timing and measurements. Product transcripts/audio and private measurement inputs
remain necessary working data; they must not enter diagnostic output or bundles.
Reference corpus case ids identify the benchmark; human-readable speaker labels,
voice embeddings and transcript/summary content are not diagnostic identifiers.

Locations below refer to **audited e03d6a31**, so deleted files remain locatable with
`git show e03d6a31:<path>`. The [complete per-file inventory](content-boundary-files-20260912.json)
accounts for all 625 evidence files, including every removal and retained-file verdict.
Artifact categories overlap; totals must not be added together.

## Findings

| Code | Location at audited head | Violation | Fixed |
|---|---|---|---|
| F1 | `evidence/e2e-feature-verification-20260911/export.json:12`; complete inventory | Transcript exports and meeting/snapshot text: 80 JSON text artifacts and 25 export files across the affected E2E directories | Yes; removed affected files |
| F2 | `evidence/e2e-feature-verification-20260911/download.mp3` (binary); inventory | 24 retained audio files | Yes; removed |
| F3 | `evidence/round11-browser-regression-20260911/final/row-04.png` (binary); `tests/e2e/verify_workspace.py:103` | 169 screenshots from unmasked writers; representative image visibly contained transcript, labels and history. Not every blank image is claimed to contain text | Yes; removed raw-image category; E2E screenshot writer disabled |
| F4 | `evidence/relay-thinking-models-20260911/browser-aborted/macstudio-browser-request.json:7`; inventory | 47 raw relay request/response artifacts, including messages/content/reasoning | Yes; removed; E2E and thinking-probe body writers removed |
| F5 | `evidence/relay-thinking-models-20260911/browser/macstudio-summary.json:4`; inventory | 14 generated-summary artifacts | Yes; removed; writers retain status/boolean/count projections only |
| F6 | `evidence/e2e-feature-verification-20260911/diagnoses.json:24`; inventory | 61 artifacts with human-readable speaker/display-name fields | Yes; removed; new E2E metadata excludes label strings |
| F7 | `evidence/browser-timeout-evidence-20260911/python-suite.txt:24`; inventory | 17 files exposing local user home paths | Yes; removed; remaining docs/prototype metadata normalized or reduced to asset ids |
| F8 | `tests/e2e/verify_workspace.py:78-81,103,124-125,144,315,345,373,445,608,647-655` | Raw bodies, screenshots, browser credential storage, meeting documents, exports/audio and events written into evidence output. No committed credential value established | Yes; no browser-state/body/image retention; private temporary downloads/media cleaned up; retained writer projects metadata |
| F9 | `moss_transcribe_diarize/phase2_browser_evidence.py:43-44,178-179` | Full page URL and selector/JavaScript source can contain credentials or transcript text | Yes; operation identifier and URL scheme only; sync/async paths |
| F10 | `moss_transcribe_diarize/phase2_acceptance_measure.py:219-221`; `phase2_acceptance_replay.py:342-347` | Arbitrary exception first line includes replay-promoted HTTP detail, OS paths or upstream content. Pre-existing boundary reused by today's diagnostics | Yes; exception type/operation plus numeric HTTP/errno/exit status, no freeform message |
| F11 | `moss_transcribe_diarize/app/live_coordinator.py:727`; `app/live_service_runtime.py:1192,1598,1603` | Pre-existing `exc_info=True` leaks provider/finalizer/rolling exceptions into service journal | Yes; type-only logging; failure behavior preserved |
| F12 | `moss_transcribe_diarize/phase2_acceptance.py:2558` | Pre-existing outer error JSON/stderr retains arbitrary exception text | Yes; type only, still failed/unqualified |
| F13 | `ops/stage-account-provider-manifest.py:71,80` | Full operator path and arbitrary staging exception printed | Yes; staged status + candidate SHA, exception type on refusal |
| F14 | `prototypes/streaming-diarization/identity-floor-a2/results/*.npz` (16 binary files); `run.py:50,170-184`; `results/results.json:1` | Voice embeddings retained in git; reference names in speaker/source-plan fields | Yes; caches removed and moved outside evidence to private cache; per-case reference ids replace names |
| F15 | `prototypes/terminal-direct-diagnosis/probe.py:17-31`; `results.jsonl:1-5` | Prompt/request fields and full tracebacks retained | Yes; writer and committed rows reduced to types/numeric measurements |
| F16 | `prototypes/client-configured-llm/thinking_browser_probe.py:72-81`; `thinking_request_probe.py:37-56` | Explicit raw request/response/summary/image writers; response summary/error printed | Yes; removed raw sinks; boolean/status/numeric metrics only; explicit private transcript input |
| F17 | `prototypes/streaming-diarization/account-path-differential/{measure,controls,repeat}.py`; `mixer-repair-feasibility/{measure_account,attribution_measure}.py`; `text-path-differential/measure.py`; `speechless-windows/measure.py:42` | Freeform exception messages or user paths in published measurement rows/logs | Yes; exception classes, manifest basename, fixture identifier; scoring unchanged |
| F18 | `docs/audits/browser-latency-budget-20260911.md:78-81`; `e2e-feature-verification-20260911.md:44,49,84`; `voiceprint-first-match-20260911.md:22-23`; reproduction commands in six audits | Literal model refusal/spoken prefix, display-name values and local username paths quoted in documents | Yes; content removed, labels pseudonymized, home paths generalized |
| F19 | `prototypes/streaming-diarization/mixer-repair-feasibility/tail.json:10,24`; `tail.py:28` | Two 12-sample PCM arrays. These were a synthetic ramp, not captured voice | Yes; arrays removed from artifact and writer; sample/change counts retained |

F17 exact writer locations:
`account-path-differential/measure.py:47,59,69`, `controls.py:44,49`, `repeat.py:41,46`;
`mixer-repair-feasibility/measure_account.py:54,64`, `attribution_measure.py:62,72`;
`text-path-differential/measure.py:23,35,55`; `speechless-windows/measure.py:42`.
All are beneath `prototypes/streaming-diarization/`. Removed paths are in the inventory; these are diagnostic-only edits. Fixture literals in tests and product input/
output code are not themselves retained observations and were not erased.

## Verified correct

- **C1 — Relay error paths:** `app/phase2_llm.py:108-133` returns fixed error codes.
  No upstream messages, request/response bodies, refusal text or exception bodies
  are logged there. The leaks were in probe/E2E writers, not this production handler.
- **C2 — Timeout screenshots:** `CONTENT_FREE_STYLE` masks text, forms and media in
  sync/async timeout PNGs. The existing real-browser test changes transcript/form
  secrets and proves identical masked PNG bytes. Registered masked PNGs remain.
- **C3 — Bundle exclusion:** campaign lives in a separate temporary directory
  (`phase2_acceptance.py:2373-2406`). Only registered artifacts pass the collector
  copy (`phase2_acceptance_measure.py:243-278`) and bundle copy (`phase2_acceptance.py:941-1003`).
  Raw quality captures/traces/audio and ordinary fidelity PNGs are unregistered;
  the campaign directory is deleted at `:2566-2567`. No direct tar bypass found.
- **C4 — Identity counts:** `phase2_acceptance_external.py:3244-3274` retains numeric
  emitted/reference counts, births, admitted/provisional-only counts and abstentions.
  No embeddings, display labels, transcript or audio fields. Draft/preview events
  likewise retain sample/span ids and counters; product transcript state is separate.
- **C5 — Journal observation:** the new verified-systemd source clause expands
  provenance, but retained observation contains unit/status/counts, not journal bodies.

No credential/API-key/email value was established in the inspected committed data.
This is a bounded source/artifact audit, not a claim that pattern scanning proves
all secrets absent. The follow-up commit removes files from the branch tip; it does
not rewrite earlier Git history. No host operations or provider requests performed.

## Verification

Targeted writer regressions cover transcript/query credential exceptions, upstream
HTTP details, provider exceptions, staging paths, raw E2E bodies and screenshot
exclusion. Failure outcomes remain failures. Full combined Python: **1,542 passed + 37 subtests, 25 expected skips** (23 optional
browser cases, two unprovisioned corpus cases). All 24 required files and all required
named cases pass the acceptance denominator check, no missing/failed/skipped required
case. Frontend: **202 passed**. The real-browser masked-PNG and writer tests also
passed during the focused run (196 tests); the E2E metadata/sequence tests passed
without browsers. No frontend behavior or bundle rebuild.

Full logs stay outside the repository: `/tmp/moss-content-boundary-python.log`,
`/tmp/moss-content-boundary-python.xml`, `/tmp/moss-content-boundary-frontend.log`.
