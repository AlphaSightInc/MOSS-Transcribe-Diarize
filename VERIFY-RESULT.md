# WP1 fresh-context verification result

**Architecture/evidence checks PASS within retained coverage; full Python suite FAIL.**
Two staging failures are **pre-existing, fixture-location-dependent**, not introduced by WP1.
Frontend full suite PASS. Matched mono live timing comparison and a named reusable zero/silent predicate remain absent.

## F1 — Provenance and scope

- Fresh independent conversation supplied by the user, with no earlier implementation conversation inherited; not a compact/fork/subagent substitute. Initial cwd changed to the requested worktree before verification.
- Branch `mvpfix/wp1-lane-decode`; tested HEAD `da3d1818116e516b2a542e4f21ec32a59cf8816a`; initial `git status --short` empty. The verification commit contains documentation/logs only; its parent is this tested SHA.
- Read VERIFY.md, COMMON.md, WP1-lane-decode.md, execution-plan sections 1–2, prototype skill instructions, design-lane-decode.md, and NOTES.md. No new prototype/design or production repair undertaken.
- `.wp1/new-dispatch.json` records a prior `/new` dispatch to pane %20; `.wp1/new-pane.txt` shows the command queued and old context still displayed. These files do not independently prove that prior pane completed its reset. This report claims this fresh conversation, not a witnessed prior pane reset.
- Imports of package, app.live_lane_decode, and live_service_replay resolve inside this worktree (fresh-imports.txt). Base import resolves inside `/private/tmp/claude-501/wp1base` (fresh-base-imports.txt).
- VERIFY.md requires offline checks, so no live stack/tunnel and **0 new decoder requests**. User's optional <=120-request live allowance unused. Historical cumulative usage remains 646/650, peak 1 in flight.
- Only worktree outputs plus the user's explicitly requested scratch-base area modified. No push, merge, deployment, shared service changes, or pane messages. All started test processes exited; ports 17871/18101 have no listeners.

## F2 — Checks and exact results

Each check has a specific falsifier: imports detect wrong checkout; full suites detect regressions; base reproductions distinguish source change from fixture placement; evidence audits detect saved/final, identity, scoring, and accounting mismatches; source review detects policy/wire/recording drift; listener checks detect leftover owned runtime. Any unexpected failure is reported rather than hidden or repaired in this verification-only session.

| Check | Result |
|---|---|
| Full Python suite, exact VERIFY.md adapter | **FAIL: 1718 passed, 3 failed, 2 skipped; 37 subtests passed; 21 warnings; 155.36 s** |
| Prior full-tests-final.txt comparison | Same counts and same three failure names; prior duration 167.17 s |
| Full frontend suite | **PASS: 24/24 files, 206/206 tests, 2.76 s** |
| Base storage file, temp inside protected base checkout | **17 passed, 2 failed, 0.52 s** |
| Base storage file, temp outside protected base checkout | **19 passed, 0.45 s** |
| WP1 storage file, temp outside protected WP1 checkout | **19 passed, 0.49 s** |
| Offline evidence audit | **PASS: 646 unique IDs 1..646; peak concurrency 1; 26/26 saved/final matches; 17/17 resumed/fixed falsifier runs; 6 fixed cases; 3 retained E2E scripts** |
| Additional raw saved/pre scoring audit | **PASS: 52/52 saved lane edit metrics, 52/52 pre-terminal lane edit metrics, 52/52 saved vocabulary metrics; 26/26 disjoint cross-lane speaker sets** |
| Lane/replay checks in full suite | **PASS: no failures in tests/test_live_lane_decode.py or tests/test_live_service_replay.py** |
| Retained failure-state check | **PASS: original system 8–12 s crossing segment/identity preserved; microphone revised 2/2 windows; decoder calls system, mic, mic** |
| Source contract review / git diff --check / listener cleanup | **PASS**, details fresh-source-scope.txt and fresh-cleanup.txt |

Exact full-suite failures:
1. `tests/phase2/test_candidate_storage.py::test_staging_dry_run_deletes_nothing[True]`
2. `tests/phase2/test_candidate_storage.py::test_staging_dry_run_deletes_nothing[False]`
3. `tests/phase2/test_voiceprint_latency_measurement.py::test_name_latency_is_independent_of_observer_polling_delay`

The two staging tests expect `would_remove`; the staging script passes `--protect PROJECT_DIR`, excluding fixtures nested in that checkout. Both fail identically on untouched base when fixtures are nested there; both pass outside it, on both base and WP1. Storage code, staging script, and test file are byte-identical to base. Thus **pre-existing test/environment interaction, not a WP1 source regression**; do not claim base fails with ordinary external pytest temp placement. Base source was extracted via `git archive 37979e53 | tar -x -C /private/tmp/claude-501/wp1base` without edits.

The third failure is the expected 30-second Playwright timeout waiting for Meeting history → Voiceprints in the unchanged HTML fixture. The cold decode-failure Stop test's previously observed HTTP 202/2-second deadline failure **did not recur** in this full run; no deadline changed.

## F3 — Saved-transcript falsifier results

Question: can serial per-lane decoding preserve each source's words and separate speaker namespace through Stop and saving, and what does it cost?
Verdict: **named architectural falsifiers pass in retained runs**. These checks rule out whole-lane erasure and cross-lane identity collapse; they do not assert every pre-terminal word is unchanged or establish a numerical accuracy acceptance bar.

System/mic columns are ordered. Vocabulary = retained unique words / historical unity-gain lane-alone control vocabulary. Edits = substitutions/omissions/additions on the **saved** transcript against the full reference (system 188 words, mic 145; same-voice both 188). Zero/noise mic reference empty. These omissions include unplayed audio; they are not exact-cut word-error rates. Lane attribution derives from exact saved/final positional text-and-speaker correspondence; saved objects do not natively carry source_lane.

| Case | Evidence / verdict | Saved words S/M | Vocabulary S ; M | Saved edits S ; M | Stop→final s |
|---|---|---:|---|---|---:|
| parity | fixed PASS | 86/56 | 50/50 ; 45/45 | 2/106/4 ; 0/95/6 | 11.395471 |
| mic −10 dB | fixed PASS | 86/56 | 50/50 ; 45/45 | 2/106/4 ; 0/95/6 | 11.572018 |
| mic −15 dB | fixed PASS | 86/60 | 50/50 ; 45/45 | 2/106/4 ; 0/95/10 | 11.639741 |
| system −10 dB | fixed PASS | 84/56 | 49/50 ; 45/45 | 2/106/2 ; 0/95/6 | 11.763544 |
| alternation 48 s | prototype PASS | 86/69 | 50/50 ; 13/45 | 2/106/4 ; 2/76/0 | 10.315231 |
| zero mic lane | fixed PASS | 86/0 | 50/50 ; 0/45 | 2/106/4 ; 0/0/0 | 4.999514 |
| quiet noise −45 dBFS | prototype PASS | 86/0 | 50/50 ; 0/45 | 2/106/4 ; 0/0/0 | 6.107974 |
| same voice both lanes | fixed PASS | 86/86 | 50/50 ; 50/50 | 2/106/4 ; 2/106/4 | 11.640392 |
| Stop mid-speech 12 s | prototype PASS | 38/31 | 32/50 ; 26/45 | 1/150/0 ; 0/122/8 | 8.729192 |
| reshare | prototype PASS | 86/56 | 50/50 ; 45/45 | 2/106/4 ; 0/95/6 | 11.849155 |
| system −15 dB | prototype PASS | 86/56 | 50/50 ; 45/45 | 2/106/4 ; 0/95/6 | 11.268787 |

All listed saved cases have zero unattributed words. Same voice has two disjoint IDs (`speaker-0001`, `speaker-0002`). Zero/noise produce no mic words or mic identities. Alternation has one system identity and **two mic identities**: lane separation passes, single-speaker continuity is not established. Its mic capture is the later half of the source, so 13/45 vocabulary against the first-24-second control is not a matched-extent loss estimate; the 12-second Stop case also has unequal extent. Full per-lane pre-terminal metrics and exact run IDs remain in fresh-saved-measurements.json.

## F4 — Cost, queue, and baseline limits

99 fixed-build individual 2.5-second lane decoder calls: median **0.14452375000109896 s**, max **1.133293874998344 s**. These exclude identity and queue waiting; not a complete two-lane span latency.

| Fixed case | Calls at 2.5 s | Median / max decode s | Sampled canonical queue max | Pending signals max | Stop→final s | Total requests / capture minute |
|---|---:|---|---:|---:|---:|---|
| parity | 18 | 0.144910 / 0.838978 | 2 | 1 | 11.395471 | 26 / 65 |
| mic-10 | 18 | 0.143045 / 1.093738 | 1 | 1 | 11.572018 | 26 / 65 |
| mic-15 | 18 | 0.129633 / 0.782870 | 1 | 1 | 11.639741 | 26 / 65 |
| system-10 | 18 | 0.151284 / 1.009487 | 1 | 1 | 11.763544 | 26 / 65 |
| zero | 9 | 0.256471 / 1.133294 | 1 | 1 | 4.999514 | 13 / 32.5 |
| same | 18 | 0.152197 / 0.841097 | 1 | 1 | 11.640392 | 26 / 65 |

Across retained instrumented runs, canonical queue max **3**, pending signals max **1** (point samples, not a bound on unseen peaks). Fixed cases max queue **2**; each other fixed case max **1**. Resumed prototype system −10 had Stop→final **33.139640 s**, retained rather than excluded. Fixed Stop range **4.999514–11.763544 s**.

**Matched mono per-span latency, queue, Stop→final, and requests/minute baseline: UNMEASURED.** No live rerun authorized by VERIFY.md. Prior assessment's 24-second whole-clip median-of-three baseline was mono **1.420 s** versus independent serial **1.432 s** (+0.8%); it cannot supply those missing live deltas. Source: `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/moss-mvp-review/evidence/parallel-lanes-assessment/opus-diagnosis.md` §6.3. The 32.5/min single-active-lane control is not a mono two-voice baseline.

Historical requests: 196 initial + 271 resumed prototype + 143 fixed + 36 E2E = **646**. Retained E2Es: lifecycle **6/6** (9 requests), reshare **6/6** (15), demo **PASS**, 20 seconds (12). Lifecycle concurrent case excluded for single-meeting limit. These are audited retained live results, not newly executed E2Es.

## F5 — What changed and what is preserved

Production commits `2cb9d014`, `644833ee`; later commits bench/evidence. Nine production files changed:
- `app/live_mixer.py`, `app/live_coordinator.py`: aligned lane PCM/silent facts, bounded per-lane retention beside mixed tape, immutable work capture, ownership recorded only after accepted commit.
- `app/live_lane_decode.py`, `app/live_identity.py`, `app/live_provider_bundle.py`: serial decoding; each lane forks its own album/sweeper while sharing encoder; matching restricted to that lane's born speakers via allowed_speakers; births use existing global monotonic speaker-NNNN allocator. Voice evidence uses producing lane PCM.
- `app/live_service_runtime.py`, `app/live_transcript_convergence.py`, `app/live_session.py`: draft/rolling/terminal per lane, successful rolling lanes advance independently, failed lane crossing segment retained; terminal failure preserves prior lane surface. Cross-lane overlap legal, same-lane overlap refused; order start/system-first/end. Uncertain identity preserves unattributed words.
- `live_service_replay.py`: reads additive segment source_lane and commit source_lanes; legacy defaults retained.

All `app/` paths above are under `moss_transcribe_diarize/`. Tests changed: `tests/test_live_lane_decode.py`, `tests/test_live_service_replay.py`, `tests/phase2/test_owner_bound_live_meeting.py`, `tests/phase2/workspace_reachability_fixtures.py`; lifecycle fixture audio now nonzero, existing assertions unchanged. Design/bench/evidence: `docs/design-lane-decode.md`, `prototypes/lane-decode-proto/`, `evidence/mvpfix/wp1/`, VERIFY.md, .gitignore.

**Reusable zero/silent predicate status:** behavior exists, but **no shared named helper was added**. `live_coordinator.py:511–513` converts all-declared-silent lane PCM to zeros; `live_lane_decode.py:37,211,251` and `live_service_runtime.py:1420` repeat `not any(pcm/audio)`. Unit coverage exercises zero/declared-silent canonical, rolling, draft, terminal. This verification reports the missing reusable API; it does not silently refactor production.

No numeric QUALITY_BOUNDS/identity/readiness policy changes, no two-Refresh sentinel change, unchanged nine-key wire and mixed recording authority. Mixed and two source tapes each bounded by B: <=3B (80,000-byte capacity test gives 240,000 total); four canonical PCM buffers <=8R bytes before copy overhead; rolling/encoder allocations additional, process peak memory unmeasured.

## F6 — Limits and deviations

- Fixed build covered six cases before final preview/replay cleanup; final-code E2Es passed. Complete final-SHA 11-case ladder not rerun under prior 650 cap. Noise, 48-second alternation, mid-speech Stop, two-voice reshare, system −15 remain prototype evidence.
- Saved lane provenance native persistence/reopen/export belongs to WP2; exact positional correspondence is derived attribution. Full-reference WER and historical control/gain/extent mismatches limit accuracy claims. No numeric acceptance recommendation.
- Existing benchmark falsifiers only detect complete lane words/speakers disappearing; they do not demonstrate verbatim pre-terminal preservation. Alternation mic identity split noted above.
- Initial prior-suite runs used hardcoded external /tmp sockets; mandated fresh full run used existing local redirect adapter without assertion changes.
- Frontend runner-loader attempt failed before collection (`__dirname is not defined`), retained as fresh-frontend-runner-attempt.txt. Successful full run used standard loader, disabled result cache, temporary local node_modules directory linking existing dependencies while keeping .vite/.vite-temp local; original node_modules symlink restored. No npm install/build or shared dependency writes.
- Base first run intentionally retained protected-tree placement, then rerun outside base protection to isolate cause. Both outcomes retained. Explicit user base-scratch exception is the only additional write area.
- Prior pane `/new` completion unverified; this conversation itself is fresh. No fresh provider results claimed.

## Reproduction commands and artifacts

Run from WP1 unless stated. Python = `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`; each Python invocation sets PYTHONDONTWRITEBYTECODE=1.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:prototypes/lane-decode-proto TMPDIR="$PWD/.wp1/test-tmp" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider -p pytest_local tests --basetemp=.wp1/pytest-fresh > evidence/mvpfix/wp1/fresh-full-tests.txt 2>&1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/lane-decode-proto/audit_evidence.py > evidence/mvpfix/wp1/fresh-evidence-audit.txt 2>&1
npm --prefix frontend test -- --run --no-cache > evidence/mvpfix/wp1/fresh-frontend-tests.txt 2>&1
git archive 37979e53 | tar -x -C /private/tmp/claude-501/wp1base
```

Base cwd `/private/tmp/claude-501/wp1base`, PYTHONPATH=., same Python, `-m pytest -q -p no:cacheprovider tests/phase2/test_candidate_storage.py`, first `--basetemp=/private/tmp/claude-501/wp1base/.pytest-tmp`, then `--basetemp=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp1-lane-decode/.wp1/pytest-base-storage`. WP1 control uses same file command from WP1 with `--basetemp=/private/tmp/claude-501/wp1base/.pytest-wp1-storage`.

Additional raw scoring verification reused only the existing pure words()/edits() definitions via AST extraction (no score.py output rewrites), recomputed from scratch saved/pre surfaces + public references, and checked disjoint speaker sets. Output: fresh-saved-measurements.json. All fresh logs and this report are the only files committed by this session.

Log trailing whitespace/extra terminal blank lines normalized after the staged diff check flagged pytest/console formatting; contents/counts unchanged. Final staged whitespace check passes.
