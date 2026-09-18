# WP29 fresh-context verification — PASS

Fresh session, 2026-09-18: no implementation conversation inherited. Read and executed
`VERIFY.md`, COMMON.md, WP29 brief, execution-plan §§1–2, repository instructions,
prototype skill and retained NOTES.md. No production changes or new experiments.

## F1 — Scope and source

- Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp29-tape-exhaustion`.
- Branch: `mvpfix/wp29-tape-exhaustion`.
- Tested starting SHA: `9ac68d11610e2c80ab830c87c4a81f62f3609597`; starting tree clean.
- Python import resolved to this worktree's `moss_transcribe_diarize/__init__.py`.
- Python executable: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`.
- Every Python command used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` and
  `TMPDIR="$PWD/.wp29/t"`, with this worktree as cwd. Existing shared dependencies
  were consumed; frontend cache and generated output remained checkout-local.

## F2 — Commands and fresh results

Below, `$PY` denotes the exact executable above. Logs are under `evidence/mvpfix/wp29/`.
Exit statuses are also retained in `fresh-*-status.txt` / `fresh-exit-status.txt`.

| Command | Exit | Result / log |
|---|---:|---|
| `$PY -c 'import moss_transcribe_diarize as m; print(m.__file__)'` | 0 | Correct worktree import |
| `$PY -m pytest -q -p no:cacheprovider tests` | 0 | 1,932 passed, 2 skipped, 21 warnings, 37 subtests passed; 182.68 s; `fresh-python.txt` |
| `npm --prefix frontend test -- --run` | 0 | 265 passed / 28 files; 2.77 s; `fresh-frontend.txt` |
| `npm --prefix frontend run typecheck` | 0 | `fresh-typecheck.txt` |
| `npm --prefix frontend run build` | 0 | `fresh-build.txt` |
| `$PY prototypes/streaming-diarization/tape-exhaustion/audit.py` | 0 | 9/9 exhaustion sessions, 2/2 RSS sessions finalized; `fresh-audit.json` |
| `git diff --check f5fff0b2..HEAD -- moss_transcribe_diarize tests frontend/src docs prototypes` | 0 | WP29 source/test/doc whitespace clean |
| `git diff --check` | 0 | Worktree whitespace clean |
| `git diff --exit-code HEAD -- moss_transcribe_diarize/app/frontend_assets` | 0 | Generated frontend assets unchanged |

Zero fresh failures; no reruns needed. Python warnings concern Starlette/httpx,
tar extraction defaults, and deprecated aifc/audioop/sunau modules. The documented
unsynchronized scheduler failure did not recur. Earlier implementation failures
(4 red unit cases, 2 notice failures, 1 scheduler failure) remain in their original
logs and NOTES.md; this fresh pass does not erase them.

Commit preparation's unrestricted `git diff --cached --check` exited 2 solely for
native trailing blank lines in `fresh-frontend.txt:60` and `fresh-typecheck.txt:4`.
Raw command output retained unchanged. The required source/tests/docs scoped check
passes; these log-format diagnostics are not test failures.

The full Python suite includes 8 HTTP scenarios / 9 meetings and 5 lower-level
all/one/no-gap and all-zero cases. Frontend suite includes the notice/partial-download
case. HTTP regressions use synthetic PCM and stub decoding; retained standalone
before/after evidence uses public speech. No real decoder or GPU service used.

## F3 — Prototype question, verdict and exhaustion outcomes

Question: can bounded retained audio end truthfully while preserving committed words?
Verdict: yes for the measured cases. Committed text, retained audio, refinement,
durable publication and lifecycle ownership have separate lifetimes. Running out
of retained audio must not become a generic refinement defect or erase committed text.

Before values below come from retained `prototype.json`; after values from retained
`fixed.json`, audited afresh and exercised by the fresh HTTP regressions.

| Cases | Meetings | Refinement before → after | Saved result / after lane gaps |
|---|---:|---|---|
| Normal Stop; accepted Stop then departure; silent mic; two concurrent sessions | 5 | `failed` → `unavailable` | `completed` before and after; 2 gaps each |
| System-only exhaustion; microphone-only exhaustion | 2 | `final` → `final` | `completed`; incorrect 0 gaps → correct 1 each |
| Mixed-only exhaustion | 1 | `final` → `final` | `completed`; 0 lane gaps; both lanes refine |
| Departure/lease expiry before Stop | 1 | `not_started` → `not_started` | `interrupted` preserved; intentional `aborted` terminal failure |

All 9: saved/live text agrees, saved/reopened documents agree, committed exhausted-lane
segments preserved, audio flagged `partial`, metadata 60,000 ms and MP3 duration exactly
60.000000 s for 90 s capture, lease disarmed, publication queue empty, three tapes released.
This preserves already committed words; it does not claim transcription beyond available audio.

The 5 generic failures previously omitted required `_refused(..., gaps=...)` input.
The fix supplies `gaps` and `tape_samples`; all 8 completed terminal payloads expose
`outcome`, `tape_gaps`, `tape_samples`, `reason`, `applied`, `finalization_status`.
Gap counts count lanes, so the same missing interval on both lanes counts twice.
All-zero input returns named `all_lanes_zero` refusal, with no proposal and 0 gaps.

Seven affected completed meetings save and reopen the exact notice:
“Final transcript refinement was unavailable for some audio. Previously committed words were kept.”
The existing UI shows this notice and “Download partial audio”. Mixed-only exhaustion
needs no refinement notice because both transcript lanes remain available.

## F4 — Fix locations and changed files

- `moss_transcribe_diarize/app/live_lane_decode.py:321`: aggregate real lane gaps and
  retained samples; supply refusal arguments and propagate accounting for partial results.
- `moss_transcribe_diarize/app/phase2_live.py:794`: derive the safe notice from settled
  runtime accounting; `:840` forwards it through terminal publication.
- `moss_transcribe_diarize/app/phase2.py:1156`: persist notice with final transcript;
  `:1411` forwards it through the meeting handle.
- Coverage: `tests/test_live_lane_decode.py:765`, `tests/phase2/test_tape_exhaustion.py:14`,
  `frontend/src/components/MeetingHistory.test.tsx:71`; ADR-0003 and retained prototype/evidence.
- This verification changes only this result and `evidence/mvpfix/wp29/fresh-*` logs.
  No production source, policy, cap, protocol, threshold or generated-asset changes.

## F5 — Retained repeated-session RSS: growth, owner UNKNOWN

Fresh audit of retained measurements, not a repeat model run. Current process resident
memory (RSS), not historical peak; same runtime and ONNX encoder across two 600 s sessions.

| Point | Bytes | MiB |
|---|---:|---:|
| Before first frame | 147,259,392 | 140.4375 |
| After first final | 624,230,400 | 595.3125 |
| After second final | 651,165,696 | 621.0000 |
| Second minus first | 26,935,296 | 25.6875 |

Both finalize: 9,600,000 accepted and committed samples each; 602 stub runner calls each;
zero GPU requests. After each, all tapes/pending PCM hold zero samples. Measured Python
owner counts and estimated bytes are identical; runtime session count grows 1 → 2.
Native allocation ownership is unmeasured. Additional 25.6875 MiB is real measured growth,
not proof of a plateau or bounded memory. No obvious owner identified; no memory fix.

## F6 — Limits, deviations and cleanup

HTTP/SQLite/MP3 are excluded from the RSS bench: this cannot certify WP22's full-service
616 → 1,149 MiB footprint. Longer repeated-session memory behavior and real ASR accuracy
remain unknown. No deployment, attended-browser fidelity or throughput qualification.
Headless browser tests included by the full suite do not establish attended acceptance.

Inherited prototype deviations: automated state dumps instead of interactive TUI;
isolated lane-capacity overrides because silent PCM occupies bytes and does not keep a
tape small. Production caps unchanged. No deviation from the requested fresh verification;
independent frontend commands ran alongside Python, with separate logs and exit statuses.

Python/frontend command sessions exited zero. Post-suite process check found 0 remaining
test roots or worktree-tagged processes (`fresh-process-check.txt`). No tunnel/server left
running; no push, merge, deploy, shared-service operation or other-worktree modification.
Result and fresh logs committed locally; final commit SHA and clean status reported in pane.
