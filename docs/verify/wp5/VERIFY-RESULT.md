# WP9 fresh-context verification — PASS for WP9; full suite NOT GREEN

Fresh-context session, 2026-09-18: executed the user-provided `/new` verification
handoff without implementation-session context. The literal tmux `/new` invocation
and pane identity were not independently observed or asserted.
Verified clean starting branch `mvpfix/wp9-rename-identity` at
`97f09c3a82801910531b43536472c8dd7ba7cf65`.
Base: `a92bb4aa88f9581b46cefcafae98c80e911a1d3b`.
No production implementation changed in this verification session.

**F1 — Durable rename passes.** An owner names a stable speaker ID in an owned
meeting; ending capture does not end the right to edit its saved display name.
The production diff preserves owner authority, active naming, pending clearing,
identity/enrollment thresholds and the two-Refresh sentinel. Existing linked
voiceprints remain renameable; terminal meetings without retained eligible voice
evidence return `unavailable`, with no fabricated voiceprint or pending enrollment.
Exact-ID/duplicate-label, foreign-owner, restart and enrollment checks pass.

| Path | Fresh base before | Fresh WP9 after |
|---|---:|---:|
| (a) during capture | HTTP 200 | HTTP 200 |
| (b) after Stop, before reload | HTTP 404 | HTTP 200 |
| (c) after reload / same-owner observer | HTTP 404 | HTTP 200 |
| (d) older meeting from History / recreated app | HTTP 404 | HTTP 200 |
| (e) completed file meeting | HTTP 404 | HTTP 200 |

Fresh replay: 1/5 before, 5/5 after; GET/history agree 5/5 after. Naming replay
explicitly disables enrollment: bank remains empty in 5/5 cases. Separate affected
Python tests exercise default enrollment and linked profiles. Full frontend rerun
with fresh route documents verifies 25/25 exports and 4/4 completed summary inputs.
See `evidence/mvpfix/wp9/fresh-rename-matrix.json`, `fresh-base-prototype.json`,
`fresh-prototype.json`, and `fresh-frontend-route-docs.log`.

**F2 — History-card decision: leave unchanged.** LiveTranscribe's
`frontend/src/components/historyPanelSurface.tsx:133–174` renders meeting title,
metadata, duration and source, with no speaker field. Read that reference and
`tools/uifidelity/reference_oracle.py`; saved names belong in the opened transcript
and returned history documents. No card redesign is justified by this contract.

**F3 — Integrated silence span passes.** WP7 Adam Frank fixture, 49–109 s excerpt,
25–35 s replaced by digital zeros; exact original birth span 25.25–27.75 s:
0 nonzero bytes, 0 decoder requests, 0 identity preparations, 0 extra births.
Existing speaker `speaker-0001` unchanged. Production adapter/coordinator are
unchanged against base. This is the exact-span check, not a full 60 s acoustic rerun.
See `evidence/mvpfix/wp9/fresh-silence.json`.

**F4 — Exact fresh test counts.**

| Run | Passed | Failed | Errors | Skipped | Denominator / time |
|---|---:|---:|---:|---:|---|
| Entire Python `tests` tree | 1,753 | 19 | 22 | 2 | 1,796 test items; 137.99 s |
| Affected Python, literal VERIFY script | 20 | 0 | 0 | 0 | 20; 3.48 s |
| Known integration nodes, literal script | 0 | 2 | 22 | 0 | 24; 3.67 s |
| Full frontend, literal script | 239 | 0 | 0 | 0 | 239 in 27 files; 2.66 s |
| Full frontend, fresh route documents | 239 | 0 | 0 | 0 | 239 in 27 files; 2.43 s |

The full Python run also reports **37 passed subtests**, separately from 1,796
items (JUnit includes them, hence 1,833 records). 21 warnings. The two skips concern
unprovisioned operator-owned identity and F-cert corpora. Typecheck/build and
`git diff --check` pass; rebuilt frontend assets are byte-identical to starting HEAD.
The historical 805/2/22 result was phase2-only, not the entire Python suite.

**F5 — Every product failure is pre-existing on base; 0 introduced by WP9.**
A scratch `git archive a92bb4aa` lives inside `.wp9runtime/base-a92bb4aa`.
Ran each failing **whole file** from that archive's own cwd, using its production
code, the same interpreter, `PYTHONPATH=.` and the same temporary-path relocation.
All 41 failing/error node IDs, outcome types and normalized tracebacks match.
These six test files are unchanged by WP9. Per-node evidence:
`evidence/mvpfix/wp9/fresh-failure-classification.json` and accompanying base XML/logs.

| Whole file on scratch base | Passed | Failed | Errors | Reason |
|---|---:|---:|---:|---|
| `tests/phase2/test_draft_lane.py` | 14 | 1 | 0 | Zero-PCM replacement returns 0 expected 2 rows |
| `tests/phase2/test_runner_composition.py` | 12 | 1 | 0 | Zero PCM produces 0 expected 1 request |
| `tests/phase2/test_export_oracle.py` | 0 | 0 | 22 | Node cannot resolve extensionless transcriptOrder |
| `tests/test_live_pipeline_seams.py` | 52 | 15 | 0 | Guard bypasses fixture decoder results/errors/metadata |
| `tests/test_live_rolling_wiring.py` | 27 | 1 | 0 | Empty zero-PCM result bypasses salvage fixture |
| `tests/test_live_service_replay.py` | 23 | 1 | 0 | Terminal fixture reports failed instead of final |

Base total for these six files: 128 passed, 19 failed, 22 errors, 169 items,
plus 9 passed subtests. First five: 7.08 s; service replay: 0.49 s.
The 19 failures match the known WP3 adapter zero-guard seam failures assigned to
WP10. The 22 export errors match the import corrected later in `79467f08` (inspected,
not applied). No unrelated repair, merge, push or deployment was performed.

**F6 — Execution boundaries and deviations.**
- Ran `bash prototypes/rename-after-stop/verify.sh` literally, successfully. Its
  full-suite prohibition is superseded by the user's explicit full-suite request.
- Full command remains `python -m pytest -q -p no:cacheprovider tests`; the supplied
  interpreter resolves this worktree. `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=.`,
  own-tree TMPDIR/npm cache, and PYTEST_ADDOPTS for basetemp/JUnit/short tracebacks.
  `evidence/mvpfix/wp9/contained-run.py` temporarily relocates hardcoded `/tmp`
  sockets/directories to `.wp9runtime/t`, then restores all seven affected source/
  test files and three regenerated WP2 screenshots byte-for-byte. Exact temporary
  patch is retained losslessly inside containment JSON; trailing whitespace in
  logs/XML is trimmed for diff-check. No test assertions or product policies were changed.
- Initial relocation returned absolute tempfile paths exceeding macOS's Unix-socket
  limit: three admin-status failures reproduced on scratch base twice. Correcting
  only relative socket spelling gives 3/3 on base and 3/3 in the completed full run.
  These are containment-harness failures also present on base, not WP9 defects.
  The first full attempt was stopped (SIGINT did not finish; SIGTERM, exit -15)
  and its partial log retained; it has no completed-suite count. A wrapper-edit
  command initially used the archive-relative wrong path (FileNotFoundError);
  it made no change. The corrected full run above completed normally, exit 1.
- Extra base VAD file check: 15/15, no failures; it did not supply a missing failure.
- Retained batch prototype instead of interactive TUI; semantic SQLite 3.50.4
  override follows existing fixtures (production requires 3.53.4). Production
  runtime, deployment, attended browser acceptance and full 60 s acoustic result
  remain unmeasured. Prior-session `/tmp` writes are historical deviations;
  this session's scratch/temp destinations stay inside the authorized worktree.
- No shared decoder calls, tunnels, shared-service changes, pushes, merges or deploys.

Implementation files are enumerated in `evidence/mvpfix/wp9/implementation-files.txt`.
Core behavior: `phase2.py`, `phase2_speaker_identity.py`, `TranscriptPane.tsx`,
`speakers.ts`; rebuilt JS/map; naming/silence tests, CONTEXT and replay documentation.
This commit changes only VERIFY-RESULT, the prior phase2-count label/verification
appendix in NOTES, and fresh WP9 evidence plus its reproduction helper.
