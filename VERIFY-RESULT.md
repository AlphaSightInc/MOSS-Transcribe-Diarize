# WP11 fresh-context verification — 2026-09-18

**WP11 verification: PASS within its stated scope. Full Python suite: FAIL.**
No introduced test failures observed; all 19 failures match retained base evidence.

- Branch: `mvpfix/wp11-export-labels`.
- Tested SHA: `e0bb7104e734800d60b5ebf3dae012b8f66dcfa9`.
- Base: `b31683a6`; initial worktree clean. Import resolved inside this worktree.
- Fresh session: read VERIFY.md, AGENTS.md, NOTES.md, COMMANDS.md, WP11 brief,
  COMMON.md, execution plan sections 1–2 and required prototype skill. No prior
  implementation conversation used. No new design or production edits.

## F1 — Label contract and prototype: PASS

Speaker display name / existing ID fallback is the label in md/txt/json/srt/vtt.
Lane identifies input origin, not a person: JSON keeps optional `source_lane`
separately; UI lane badges remain. Text/subtitle formats omit lane metadata.
WP2 documented decoration to match its UI choice, no separate user requirement.
Overlapping cues retain their original times and separate speakers.

Retained prototype asks whether overlapping, two-speakers-per-lane documents
round-trip through all five formats while corrupt labels fail. Baseline tagged
0/5 accepted; candidate tagged 5/5 accepted, corrupt 5/5 rejected. Legacy 5/5
accepted and corrupt 5/5 rejected in both. Tagged corpus: 9 segments / 4 IDs;
legacy: 5 segments / 2 IDs. Verdict SUPPORTED. Projection prototype found 0/2
saved lanes, repaired to 2/2. Fresh oracle suite: 50/50 PASS, including tagged and
legacy exports, words/label/time corruptions, JSON lane corruptions, saved projection.

## F2 — Fresh gates and inherited failure classification

Executed VERIFY.md's command block literally, without `set -e`, using its Python,
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/runs/wp11"`, confined-fixture
plugin and `--basetemp=runs/wp11/pytest-fresh`; native config loader/cache disabled
for frontend tests. Logs below are under `evidence/mvpfix/wp11/`.

| Gate | Result | Exact evidence |
| --- | --- | --- |
| Full Python `tests` | FAIL, exit 1 | 1809 passed, 19 failed, 2 skipped, 37 subtests passed; 21 warnings; 140.49s; `fresh-python.log` |
| Full frontend | PASS, exit 0 | 233 passed / 26 files; 2.55s; `fresh-frontend.log` |
| Typecheck | PASS, exit 0 | `fresh-typecheck.log` |
| Production build | PASS, exit 0 | 34 modules; 105ms; `fresh-build.log` |
| Export oracle | PASS, exit 0 | 50 passed; 0.83s; `fresh-oracle.log` |
| Failure classification | PASS | Fresh 19/19 FAILED lines exactly equal both `expected-failures.txt` and `base-failures.log`; additional 0, missing 0; assertion locations/types also identical |
| Shipped assets | PASS | `git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets` exit 0 after build |
| Owned ports | PASS | `lsof -nP -iTCP:17871 -iTCP:18111 -sTCP:LISTEN`: no listeners, exit 1 |

Base reproduction was read, not rerun: 128 passed, 19 failed, 9 subtests passed,
6.83s, from the retained b31683a6 snapshot run documented in NOTES.md. All five
failing test files are unchanged from base. File-by-file classification:

- `tests/phase2/test_draft_lane.py`: 1 pre-existing; fixture changes legacy text
  while keeping authoritative empty `effective_transcript`; expects 2 rows, gets 0.
- `tests/phase2/test_runner_composition.py`: 1 pre-existing; zero PCM prevents
  the transport request that the fixture expects.
- `tests/test_live_pipeline_seams.py`: 15 pre-existing; zero PCM preempts decoder
  transport, salvage, token-cap and response/timing assertions.
- `tests/test_live_rolling_wiring.py`: 1 pre-existing; zero PCM preempts salvage.
- `tests/test_live_service_replay.py`: 1 pre-existing; terminal zero-audio refusal
  yields failed instead of expected final.

Thus the 19 comprise 18 zero-audio seam fixtures plus 1 transcript-authority
fixture. WP10 repair is outside this verification. Full-suite FAIL remains open.

## F3 — Integrated WP5 evidence: PASS (retained reruns, not fresh decoder runs)

Per VERIFY.md, checked `integrated-complete/campaign-results.json`, screenshots,
prototype counts and decoder-accounting.json; viewed `case-12.png`. Programmatic
checks confirm every case's PASS/ok fields and the exact counts below.

- Case 8: 5/5 variants; four completed uploads, two rejected files with visible
  reasons; 15.785s.
- Case 10: live 5/5 + file 5/5 exports, 10/10 total; both live lanes retained,
  four live turns / one file turn. Audio retries 2/2 decode, 54,693 / 72,837 bytes
  equal expected sizes after cancellation at 1,500 bytes; 1.759s.
- Case 11: renamed exports 5/5, two renamed turns, one enrolled voiceprint after
  reload; 15.751s.
- Case 12: 60/60 fixture history rows, two visible Refresh controls in Voiceprints,
  viewport/scroll width 400/400px; 0.193s. Screenshot is the subsequent Sessions
  view; the recorded Voiceprints count is not inferred from that screenshot.
- Decoder accounting: 10 + 18 + 14 = 42/60 calls, maximum 2 in flight. Fresh
  verification adds 0 calls; no tunnel or live stack started.

## F4 — Scope, changed files and limitations

Diff from base reviewed: label serializer, JSON lane oracle, saved-lane projection,
upload failure reason, matching tests, design document, browser bench, evidence,
verification instructions and shipped assets only. No QUALITY_BOUNDS, identity
policy, readiness thresholds, frame keys, lifecycle assertions or two-Refresh
sentinel changes. Existing fake-segment test only adds `source_lane=None` twice.

Product files: `frontend/src/lib/{transcriptExport,fileUpload}.ts`,
`moss_transcribe_diarize/app/phase2_live.py`, shipped `app.js` / `app.js.map`.
Tests: frontend `transcriptExport.test.ts`, `laneConsumers.test.ts`,
`fileUpload.test.ts`; `tests/e2e/export_oracle.py`;
`tests/phase2/{test_export_oracle,test_owner_bound_live_meeting}.py`.
Supporting files: `docs/design-lane-consumers.md`, browser-stress `run.py` /
`README.md`, `evidence/mvpfix/wp11/*`, `VERIFY.md`.
This verification commit adds only this report and the five `fresh-*.log` files.

Restored the three generated WP2 geometry snapshots as instructed. No push,
merge, deployment, service restart or other-worktree source modification.
No fidelity, echo, transcription accuracy, external subtitle-player, deployed
runtime or human visual acceptance claim. History scale uses synthetic rows.
Retained earlier campaign failures remain recorded; browser burst-limit causality
remains a hypothesis, despite passing after duplicate download removal.

Deviations retained from implementation: scripted prototype instead of interactive
TUI; earlier explicit /tmp fixtures before confinement (documented self-cleaned).
Fresh verification used the prescribed fixture redirection from the outset.
Integrated browser cases and baseline failures were verified from retained evidence,
as VERIFY.md explicitly directs; neither was rerun in this fresh session.

Staged whitespace check: raw pytest/npm output contains trailing whitespace / blank
EOF lines (`git diff --cached --check` exit 2); retained verbatim as evidence.
The authored report passes its whitespace check; no source change is involved.
