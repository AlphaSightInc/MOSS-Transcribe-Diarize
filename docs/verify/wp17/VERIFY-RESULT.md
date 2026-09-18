# WP17 fresh-context verification — 2026-09-18

Initial literal verification at `12b9e16337a2130584f94d68064ec07d847c7689`: **FAIL**, one document-layout test. Evidence consistency and frontend gates PASS; retained product quality acceptance FAIL. **Final offline verification PASS after document relocation; product quality acceptance remains FAIL.**

Branch: `mvpfix/wp17-lane-quality-voiceprint`. Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp17-lane-quality-voiceprint`. Initial status clean. Production fix `7870eb2c01a63ab4daa2dca2c00d77817dd6d96c`; fixture correction `685319f4632916736315aab1f6ad956942669777`. No source/test/assertion/policy changes during verification.

Read the worktree AGENTS.md, COMMON.md, WP17 brief, execution-plan sections 1–2, VERIFY.md, prototype NOTES.md, evidence NOTES.md/COMMANDS.md/reference-adjudication.md, and both fix commits. Applied the required prototype skill to the retained experiment; used diagnose for the deterministic document-layout failure. No new prototype or algorithm was needed.

## V1 — Fresh execution and failure adjudication

Executed VERIFY.md's command sequence from this worktree, with mandated venv, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=.`, local TMPDIR, local scratch plugin and native/cache-disabled frontend invocation. Import resolved to this worktree. Each check targets the failures named in VERIFY.md; failures are retained rather than assertions relaxed.

- Offline `audit.py`: exit 0, evidence consistency PASS; product acceptance FAIL; 4 recognition routes, 12 duration cases, 8 lane comparisons, historical decoder count 431.
- Initial complete Python suite: **1 failed, 1868 passed, 2 skipped, 37 subtests passed, 21 warnings, 143.76 s**. Full failed output: `evidence/mvpfix/wp17/fresh-python.txt`.
- Failure: `tests/phase2/test_tls_preparation.py:146` invokes `scripts/check_verify_layout.sh:6`, which rejects tracked or untracked root `VERIFY.md`/`VERIFY-RESULT.md`. Commit `12b9e163` introduced root VERIFY.md after the previously recorded passing suite. This is a real repository-layout failure, not a recognition regression or acceptable test waiver.
- Resolution: moved VERIFY.md unchanged to `docs/verify/wp17/VERIFY.md`; result recorded alongside it. No check or assertion changed. The script directly identifies the rejected file, so speculative hypotheses/stress loops were unnecessary. Full Python rerun uses the same flags and `--basetemp=runs/wp17/pytest-fresh-layout`; output `fresh-python-after-layout.txt`.
- Frontend: **242 passed / 27 files**, 2.45 s, exit 0 (`fresh-frontend.txt`). Typecheck and build exit 0 (`fresh-typecheck.txt`, `fresh-build.txt`). Assets identical; historical screenshot restore executed as instructed. `git diff --check` passed. Listener check for 17877/18117: no output, expected exit 1.
- Both Python skips: unprovisioned operator-owned real identity corpus and real F-cert speaker-accuracy corpus. Warnings retained in logs.

Final rerun result: **1869 passed, 2 skipped, 21 warnings, 37 subtests passed in 140.20s (0:02:20)**, exit 0. Tested implementation remains `12b9e163`; only verification-document placement and new records differ. This corrects the layout failure without waiving it.

## F2 — Recognition: causal evidence survived enrollment, but disappeared before matching

Structural question: does a lane commit preserve the original acoustic observation until workspace recognition reads it? Necessary distinct primitives: acoustic observation, committed lane speaker assignment, enrollment album, publication observation. Enrollment and recognition use different evidence-duration requirements, so an album entry cannot substitute for the original observation. Invariants: unchanged thresholds, lane namespaces, shared workspace bank, album timing and encoder calls. Falsifier: original observations survive unmodified lane commit. Retained fake-encoder prototype disproved that: **2 prepared -> 0 committed observations**, album 2, embeddings 2; both lane-parameterized regression cases failed before the fix.

Root cause: lane commit calls reconciliation (`live_coordinator.py:711`), which consumes `_pending_vectors` (`live_provider_bundle.py:878`); later matching reads that pending map (`live_provider_bundle.py:784`). Fix: freeze original observations before reconciliation at `moss_transcribe_diarize/app/live_coordinator.py:703`, then return them only for the matching identity snapshot version at `:819`. Regression: `tests/test_live_lane_decode.py:415`; repeat reads require no extra embeddings. Previously recorded focused suite: 70 passed; fresh full suite exercises it again.

Retained real baseline: no live label during the 12-second capture; a name appeared during terminal album publication. The workspace bank was not lost. Retained after-fix API snapshot measurements, enrollment lane -> recognition lane:

| Route | Seconds | Bar |
|---|---:|---:|
| system -> system | 3.526464500 | <=4.0 |
| system -> microphone | 3.527691750 | <=4.0 |
| microphone -> system | 3.528290542 | <=4.0 |
| microphone -> microphone | 3.526378542 | <=4.0 |

All four completed and saved the expected name. Times run from capture start to first API snapshot observation, not speech onset or browser rendering. Later deletion of the first enrolled profile removes its historical links; current DB link counts are not counts at recognition time.

## F1 — Microphone additions: reference correction, not a lane merge repair

Independently re-read before/after JSON, standalone diffs, fixed-output reference-only rescore, scoring predicates and bounds. Freshly compared source PCM: **400000/400000 samples exactly equal**, short clip seconds 0–25 versus longer recording seconds 115–140 (16 kHz mono 16-bit). Longer source was read from the shared tree; no writes. Freshly confirmed the fixture changes only the five leading tokens; original remaining reference tokens are unchanged. Quantitative recount/PCM output retained in `fresh-assessment.json`.

At actual mic gain **0.03 (-30.4576 dB)**, same-PCM lane-alone decode yields the same ten additions as paired saved/reopened outputs. Five are omitted source words: **“Kind of the same thing.”** Longer source reference and historical independent decode support the sentence tail. Remaining additions are **uh, um, deference, uh, uh**: four fillers plus repetition, still counted as decoder additions; no new human acoustic adjudication establishes whether all five are truly absent in speech. Gain-1 control still has the missing five words plus repeated “deference”; no gain change made.

Fixture change: `tests/e2e/fixtures/lane-microphone-reference.json:3`; selected by `tests/e2e/verify_demo_lanes.py:65`. Original mic reference/observed counts **48/58, 10 additions** -> corrected **53/58, 5 additions**. The lane-merging explanation is falsified for these ten additions, not universally for all intermediate behavior. System standalone also yields 13/106 edits; overlap final error does not require a lane merge.

## F3 — Numerical quality verdict under unchanged live bars

Word error rate = (substitutions + omissions + additions) / reference words. The harness requires every lane on every scored surface to pass; no cross-lane average or rounding into pass. Existing bounds: immediate **<=16.6655%**, final/reopened **<=9.5074%** (`moss_transcribe_diarize/phase2_acceptance.py:247,254`; harness `tests/e2e/verify_demo_lanes.py:130–139`). The separate 15% file/URL bar does not override live bounds.

| Case / surface | System before -> after | Microphone before -> after |
|---|---|---|
| Alternation immediate | 15/106=14.15094% -> same | 16/48=33.33333% -> 11/53=20.75472% |
| Alternation final and reopened | 9/106=8.49057% -> same | 10/48=20.83333% -> 5/53=9.43396% |
| Overlap immediate | 23/106=21.69811% -> 33/106=31.13208% | 11/48=22.91667% -> 6/53=11.32075% |
| Overlap final and reopened | 13/106=12.26415% -> same | 10/48=20.83333% -> 5/53=9.43396% |

Final/reopened system substitutions/omissions/additions: alternation **1/5/3** before and after; overlap **2/6/5** before and after. Mic **0/0/10 -> 0/0/5**. Immediate system **2/6/7 -> same** alternating, **2/14/7 -> 2/24/7** overlap; mic **1/4/11 -> 1/4/6** alternating, **0/0/11 -> 0/0/6** overlap.

After-correction attribution **2 -> 0** both cases; duplication **2 -> 0** alternating and **1 -> 0** overlap; speaker-lane conflicts **0 -> 0**. Removing false system-exclusive words from the microphone reference explains the attribution/duplication change; it is not evidence of a decoder repair.

**Acceptance remains 0/2 cases passed**: alternation fails immediate mic by **4.08922 percentage points**; overlap fails immediate system by **14.46658 points** and final/reopened system by **2.75675 points**. Alternation final/reopened pass. Both saved mic lanes pass by only **0.07344 points**. Immediate snapshots depend on publication timing; the before/after decoder reruns are not a controlled claim that reference editing changed system decoding. `reference-only-after.json` separately scores fixed retained output.

## F4 — Duration isolation and limits

12/12 captures: 24/48 seconds x alternation/overlap x paired/system-alone/mic-alone. Fresh recount: **8/8 saved lane comparisons identical, 628 words**; **8/8 terminal windows identical**. Of 120 paired producer windows, 92 have matching control geometry: 64 canonical, 20 rolling, 8 terminal. **89/92 match text**. Other **28 canonical windows unmatched**, not assigned invented ground truth.

Three rolling differences: 24-second overlap system 10–20 s, “you're” -> “you know” (2 edits/33 control words); 48-second overlap same window, reverse (2/34); 48-second alternation mic 20–30 s, “that” -> “the” (1/20). These are differential errors against controls, not independent quality scores. Six of eight pre-terminal surface comparisons differ; all saved outputs converge. Source of each intermediate variation is not causally isolated.

Real recognition latency and decoder outputs are retained prior measurements, independently assessed offline here; no live replay, browser DOM latency, physical-mic acceptance, deployment or whole-product qualification claimed. No fresh human acoustic adjudication of the remaining five mic additions. No new general accuracy/capacity claim from 12 duration controls or one speaker across four recognition routes.

## V2 — Scope and deviations

Fresh decoder calls **0/100 allowed**; no tunnel or service started. Historical budget **431/600 = 427 stack-ledger rows + 4 standalone calls**; request indices restart per process and are not the total. No push/merge/deploy/GitHub/peer messages, other-checkout source writes, shared-service changes, or ports 7861/7862 touched.

Only verification records and unchanged VERIFY.md relocation are modified in this session. Layout relocation is the necessary deviation from root file placement; literal first-run failure remains committed. Existing prototype deviation retained: scripted state output rather than interactive TUI, prototype absorbed into regression tests. Brief's -10 dB/half-active description is stale: actual full-window harness uses gain .03 and exact-zero idle frames. Read-only exploratory lookups encountered absent worktree-local long corpus paths; used the documented shared corpus for the PCM comparison. No live requalification required by VERIFY.md.

Staged whitespace check exposed trailing whitespace/blank EOF lines emitted by pytest/npm. Committed logs normalize whitespace only; failed assertions/counts/output are retained, with byte-original copies in ignored `runs/wp17/*.raw`. Final committed-range whitespace check passed.
