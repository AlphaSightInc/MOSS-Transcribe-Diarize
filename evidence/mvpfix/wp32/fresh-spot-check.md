# WP32 fresh ten-row spot-check

Date: 2026-09-18. Actual `CODEX_THREAD_ID`:
`01a0b3b4-01b2-7e93-8055-ea384b226f27`; drafting thread:
`01a0b3a8-76ee-79d1-8136-01518e7c6e10`. Different threads; this session started
with the user's verification assignment, not drafting context. No dispatch log
was present or relied on.

Initial worktree clean; branch `mvpfix/wp32-final-crossreview`; initial HEAD and
audit commit `2df225bb1b2c2e9a64c4080557b427e73f89c3bd`. Reviewed source:
`37979e539f04d4ea740a1a94d021cd3bb894a0e2` →
`d8fa767f3ccbb577584643d7e23f80f55d92b2f5`.

Question: does each of the ten audit statements survive direct source, Git-object,
retained-evidence and production-seam checks? Primitives: lane evidence, session
publication, owner access, terminal state and persisted representation. These
separate who owns data, when it becomes authoritative, and what survives capture.
Invariants: protected values/protocol, isolation, cleanup and truthful accounting.
Unknown: live service configuration, physical devices, real-model parallel parity,
native hangs and all-input byte compatibility. Falsifier: a cited statement
contradicted by its actual source or a reachable probe. Diff/blame resolves changed
contracts; retained logs resolve historical claims; witnesses resolve reported
defects; suites detect integration failures. Contradictions require audit correction
or a lead finding, not an unrequested production redesign.

**10/10 PASS for audit accuracy; 0/10 FAIL.** This preserves the audit's product
verdicts (6 scoped PASS, 3 QUALIFIED, 1 FAIL); it does not convert defects into
product passes. Exactly V1–V10 were adjudicated; no new whole review performed.
Paths below are repository-relative; `app/` means `moss_transcribe_diarize/app/`.

| Row | Fresh verdict | Independent evidence and implication |
|---|---|---|
| V1 | PASS | Ran exact `git diff 37979e53..d8fa767f --` the six cited source files and current-revision `git blame` on protected ranges. `phase2_acceptance.py:246–255` retains all eight bounds; `app/live_identity_album.py:45–57` retains 2.0/1.0/0.35/0.1; `app/live_provider_bundle.py:1064–1085,1376–1377` retains override readers. `ControlPanel.tsx:69`, `captureClient.ts:174`, CSS `:root` at `styles/index.css:93–153` predate base. CSS changes use existing tokens; readiness error guard is additional. No protected-value change. |
| V2 | PASS | Opened runtime `:668,714–749,900–939`, tape `:270–310`, coordinator `:518–523`, frame parser `:260–281`, sentinel test `:69`, UI Stop `:249`, capture request `:601`. Queue limit remains admission-bound; each of mixed/system/microphone tapes gets the same capacity and refusal semantics, allowing 3× aggregate storage. Counted nine required frame keys plus pre-existing optional end timestamp. Parser, helper-failure module and original two-Refresh test have empty base/source diffs. `git show 37979e53:.../live_service_runtime.py` already has `end_time = float("inf")` at :925. Accepted-Stop lease release at transport :251 is intentional and documented. |
| V3 | PASS | Read both frontend test diffs: two exact lease-copy replacements, two saved/observer naming enablement replacements, one missing-meeting message replacement; retained terminal/Reset and provisional prohibitions. Naming contract in `CONTEXT.md:27` and owner tests supports changes. Independently enumerated 19 deletion-bearing test files and zero deleted Python assert/unittest assertions; retained inventory matches exact Git hunks after removal of extra blank separators between files. WP10 draft fixture preserves 1/2/0/0 assertions and matches real poller `mossPoller.ts:660`; zero-guard prototype NOTES records original failure. WP12 baseline log lists 19 failures; sampled rolling/launcher/replay diffs change PCM, retaining assertions. WP17 fixture restores five words: retained whole-file decode `file.jsonl:30` at 114.81–116.04 and original long reference :4 corroborate; five remaining additions remain errors. WP27 commit `379eac08` adds required preflight descriptor and positive graph/context checks without deleting assertions. |
| V4 | PASS | Opened `tests/e2e/verify_workspace.py:387–389,707,747–750`: no models returns skip; PASS/SKIP-only results exit 0, even all SKIP; summary preserves denominator. `tests/test_file_resolver_performance.py:127–142` adds two optional real-WAV skips, but explicit missing fixture paths fail. Changed-test scan finds only this new pytest.skip and no xfail. WP12 mutation log :116–120 directly shows missing `gaps` TypeError; :136–144 shows final/failed assertion after runtime catches that TypeError. Three valid assertion controls, two invalid terminal controls; not 5/5 valid kills. |
| V5 | PASS | Read admission `app/phase2.py:2018–2037`, saved rename :2129–2147 and speaker identity :184–261,305–321. Authentication precedes admission; meeting ownership precedes rename; fallback updates retain account/generation/status conditions and naming lock. Outcome joins :874–893 remain account-bound. Read file error producers :326–359,424–455 and URL producer/diff :34–121; fixed messages and fixed User-Agent, unchanged HTTP(S)/bounded redirects, no new private-network rejection claim. Capture guard uses finite labels and numeric/boolean fields. Fresh focused suite executes foreign rename 404 (`test_saved_speaker_naming.py:57`) and nine synthetic outcome cases with secret-bearing errors checked against persisted reasons/logs (`test_file_failure_reasons.py:15–57`). No leak or owner bypass found within checked scope. |
| V6 | PASS | Read TLS renewal :24–37,43–47,61–83,123–126: literal contact parser, argv subprocesses, token-file environment, type-only failure logging. Read qualification argv handling :119–156 and metadata :79–84,159–164,413–418: local import path, loopback URLs and comparison path are intentional. `wp24/build-identity.json:5` contains a worktree path. `prototypes/ui-signoff-pack/live_browser.py:12–29,49` loads public reference WAVs into fake devices and writes meeting data, including public-corpus text. No universal content/path-free claim is justified; audit correctly states this boundary. No credential/private-user transcript leak demonstrated. |
| V7 | PASS | Read terminal `app/live_lane_decode.py:245–320`: lane-local lists/tapes, ordered pool.map and executor join before assembly. `app/live_identity.py:93–109` forks lane state/revision readers; provider :633–647,1016–1023 creates independent mutable evidence. `speaker_identity.py:602–630` chooses session before interval fanout, preserves input reduction order; `file_identity_album.py:80–153` keeps album/sweep updates serial. Runtime :1176–1214 converts exceptions into failed finalization and finally releases all tapes via coordinator :1144–1149. Fresh tests cover two concurrent terminal jobs with no early publication and embedding failure/worker closure/reduction order. Base already has infinite server drain; native hangs and real ONNX concurrency parity remain unmeasured. No additional race/lifecycle defect found in this scope. |
| V8 | PASS | Opened `runner_composition.py:99–109,184–198` and its :174 test: legacy file selector preserved, terminal copies runner and retains old resolver over same decoder. No-lane test `test_live_lane_decode.py:564` uses mixed PCM only; persistence test `test_lane_consumer_store.py:13–36` commits, closes, reopens and compares actual legacy document. Fresh export probe runs base/current TypeScript: md 72/72, txt 69/69, srt 91/91, vtt 99/99 identical; JSON 497/523 differs in two target-key speaker suffixes. `transcriptKeys.ts:16–18` explains change; `MeetingHistory.tsx:377–387` supports missing segment IDs. Exactly 4/5 formats byte-identical, not all-input/real-ASR parity. |
| V9 | PASS | Production frontend search (excluding tests) found no dangerouslySetInnerHTML, innerHTML, outerHTML, insertAdjacentHTML or document.write sinks. Read JSX notice/error at `MeetingHistory.tsx:222`, textContent in `fileUpload.ts:24`, ControlPanel error/Reset :75,429 and client markLaneFailed :1110–1118. Blame dates missing callback before base; WP27 VERIFY-RESULT :86 already records it. Fresh actual-component witness: phase configuring, Reset false, stale connected copy, Switch mic/Reshare present; 1 passed, 23 filtered (Vitest labels those skipped). Simulated devices/HTTP; no physical recovery claim. |
| V10 | PASS | Read native terminal accounting `app/live_transcript_convergence.py:1109`, compositor `live_lane_decode.py:339–371` and runtime publication :1216–1256. Template selection retains first successful result's flag without OR. Executed retained probe with actual TerminalTranscriptFinalizer, compositor and session.apply_text_revision; none/system/microphone flags false/true/false; 2/3 correct; all 3 applied and session final. Running pre-publication state was not mislabeled final. Synthetic PCM/stub runner, not a real-model measurement. |

## Execution evidence and deviations

Executed literally `sh evidence/mvpfix/wp32/fresh-probes.sh` once, exit 0.
Its five checks are import custody, legacy export, truncation, frontend Reset and
seven-file focused Python suite. Outputs: `fresh-import.txt`, `fresh-legacy.jsonl`,
`fresh-truncation.json`, `fresh-reset.txt`, `fresh-focused.txt`, status file.
Focused result: **108 passed, 2 skipped, 4 warnings; 11.68 s**.
Reset: **1 passed, 23 filtered; 551 ms**. Other probe results are above.

Opened prior `python.txt`, `frontend.txt`, `typecheck.txt`/status and `skips.txt`:
1941 passed/4 skipped/21 warnings/37 subtests, 182.76 s; 265 frontend tests/28 files,
2.95 s; typecheck exit 0. User explicitly also requested full suites this session,
so that overrides VERIFY step 4's no-rerun direction. Fresh full results are in
VERIFY-RESULT.md and `fresh-python.txt`, `fresh-frontend.txt`, `fresh-typecheck.txt`.
Three extra gate commands; eight executable checks total. Source inspection
commands are evidence reads, not test denominators.

Read-only inspection corrections: optional dispatch log absent; some guessed reader
paths absent, corrected through actual canonical_preview_reader.cjs to mossPoller.ts.
Long WP17 original reference is absent in this clean worktree; read the existing
main-tree public reference read-only and cross-checked the retained decode here.
No audio copied or new listening claimed. Initial raw inventory comparison differed
only because retained file adds blank separators; normalized complete hunks match.
No audit claim required correction. No test/probe execution failed or was retried.
No production fix, policy, threshold or source rebuild; automated retained logic
witnesses fulfill this verification's explicit prototype instructions.
