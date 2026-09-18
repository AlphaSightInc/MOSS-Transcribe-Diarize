# WP2 fresh-context verification: PASS after lead-requested correction

Fresh session: user supplied worktree/SHA and VERIFY.md; no prior session or memory
results used as verification evidence. Started clean on mvpfix/wp2-lane-consumers at
`e820644f7afa2574abdf40cdb1b10cc1e1e832cc`. All commands ran with cwd
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp2-lane-consumers`.
Python import resolved to this worktree's moss_transcribe_diarize/__init__.py.
Verified corrected implementation: `2d2dc7e218e74464ea16a023c70af4b66af63c8c`.
Initial prescribed suite passed, but that was insufficient product-contract evidence:
lead identified weakened provisional-tail expectations; corrected before acceptance.

## Commands and exact results

Python below = `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`;
every Python invocation used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`.
Logs/timing files are under `evidence/mvpfix/wp2/`. Each command ran separately.
Timed reruns used `/usr/bin/time -p sh -c '<command with log redirection>'`.

| Command | Evidence prefix | Exit/result | Time |
|---|---|---|---|
| `npm --prefix frontend test -- --run --configLoader native --cache=false` | fresh-frontend | 0; 218/218 tests, 25/25 files | Vitest 2.63 s; shell wall not captured |
| `npm --prefix frontend run typecheck` | fresh-typecheck | 0 | wall 1.30 s |
| `npm --prefix frontend run build -- --configLoader native` | fresh-build | 0; 34 modules | wall 0.60 s; build 81 ms |
| `<python> evidence/mvpfix/wp2/run_python_checks.py` | fresh-python | 0; 48/48, no skips | pytest 17.68 s; wall 18.39 s |
| `<python> evidence/mvpfix/wp2/consumer_probe.py` | fresh-consumer | 0; tagged 9 rows/9 lanes/4 IDs, legacy 5/0/2 | wall 0.70 s |
| frontend test command, original tests restored before fix | correction-red-frontend | 1; 216/218 pass, exactly 2 original tests fail; 23/25 files pass | Vitest 2.69 s; wall 3.35 s |
| frontend test command, corrected comparator | correction-frontend | 0; 218/218, 25/25 files | Vitest 2.33 s; wall 2.77 s |
| typecheck command | correction-typecheck | 0 | wall 1.30 s |
| native build command, first | correction-build-1 | 0 | wall 0.53 s |
| native build command, second | correction-build-2 | 0 | wall 0.44 s |
| consumer probe command, corrected implementation | correction-consumer | 0; tagged 9/9/4, legacy 5/0/2 | wall 0.55 s |
| `git diff --check` | initial and final | 0 | not timed |

## Contract correction and field-level evidence

Restored both original test files verbatim from 37979e53 (zero diff against base):
mergeTranscript.test.ts and transcriptModel.test.ts. New lane tests remain intact.
compareTranscriptOrder, used by compareSegments, now orders committed before
provisional FIRST, then start, system before microphone, then end. Draft text cannot
jump ahead of committed text. docs/design-lane-consumers.md and VERIFY.md corrected.
The two restored tests fail on the old comparator and pass on the corrected one.
Python suites predate this frontend-only correction; frontend and consumer probe rerun.

Both fresh and corrected probe logs were checked beyond counts: entire stored/GET
transcripts equal inputs; ordered start/end/text/lane/canonical speaker IDs and
segment IDs match at normalization; candidate ID order agrees. Results retained in
fresh-state-comparison.log. Tagged turns 9/9; legacy turns 5/5. Frontend tests cover
all five exports, exact overlapping SRT/VTT intervals, history/search, shared-name
independent IDs, rename/enrollment and summary-body construction without providers.

## Rendering and build

Inspected production-390.png and production-1280.png with view_image. Lane labels
System/Microphone distinguish independent speakers; readable wrapped text, no visible
horizontal overflow. Automated geometry checks cover 390/400/1280 px. Screenshots
are partial scroll views, not proof of all content or human visual acceptance.
Chosen variant A: chronological interleave with lane badge (committed before draft).
NOTES.md records 9/9 layout combinations without horizontal overflow; at 390 px,
A has 324 px text-row width, B 162, C 312. B splits reading order/crowds text;
C adds redundant overlap labels. These variant measurements are prior recorded
prototype evidence, not rerun in this fresh session.

vite.config.ts changed to import.meta.dirname for native ESM config loading and an
explicit checkout-local cacheDir: shared node_modules must not receive Vite cache
or bundled-config scratch writes. Initial fresh rebuild produced no tracked asset
diff. Correcting the comparator intentionally changed app.js/app.js.map.
Two subsequent native builds from unchanged corrected source produced identical
SHA-256 values for 17/17 asset files, including JS, source map, CSS, fonts/worklet:
`find moss_transcribe_diarize/app/frontend_assets -type f -exec shasum -a 256 {} + | sort`
written to correction-build-{1,2}.sha256, then `cmp` exited 0. With checkout-local
cacheDir, repeated builds do not alter bundle bytes for unchanged source. This is
repeat-build evidence, not a separate comparison with cacheDir removed.

## Scope, deviations and remaining limits

Reviewed `git diff --name-only 37979e53`: no protected upstream producer, identity,
QUALITY_BOUNDS, readiness constants, frame protocol, lifecycle tests, or two-Refresh
sentinel modified. Existing two ordering tests are restored, not weakened.
Only this worktree modified. No push/merge/deploy/GitHub, shared-service changes,
providers, decoders, extra agents, or tunnels. Process listing found no remaining
verification test/probe/browser processes (only the inspection command itself).
Fresh geometry regenerated screenshots; consumer probe regenerated meeting IDs/times.
Both are retained as fresh evidence. No fixture-content change.

Earlier deviations retained from NOTES.md: initial standard Vite commands wrote
cache/config artifacts through shared node_modules; lifecycle tests briefly used
self-cleaning /tmp sockets. Later commands use isolated cache/native config and
worktree-relative socket paths. Prior SQLite refusal, test typing errors, overlong
socket address and geometry setup failure are recorded there. No recurrence here.
The earlier assertion that the two provisional-last tests were incompatible with
lane order was WRONG; corrected by the lead finding and restored-test falsifier.

Fresh-run deviations: initial frontend duration is Vitest-reported, not full shell
wall time. Initial hash glob hit fonts/worklets directories (exit 1), corrected to
file-only enumeration; both builds passed. An additional log reader initially
rejected trailing interleaved subprocess output; JSON raw_decode read the complete
first object and all four field comparisons passed. No product fix from these.
Warnings: Node localstorage-file path; Starlette TestClient/httpx deprecation.

SQLite semantic tests use existing test override: host 3.50.4 versus required
production 3.53.4. No production-runtime qualification. No WP1 live integration,
real voiceprint recognition, external subtitle-player rendering, deployment or
human visual sign-off. These remain unmeasured; no blocker to scoped WP2 verification.
