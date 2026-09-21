# Context - MOSS round 4, ralph run B

## Ground

- Repo: `/Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate` — branch `round4/ralph-b` (base = `round4/integration`
  after the round-4 merges: run A + six pane branches; the lead merges this branch back afterwards).
- **D27 (user decision on the fixture correction): YES** — adopt the corrected reference/cut for the acceptance arm and
  ladder; only class-(d) edits may change; the three class-(a) decoder additions must remain visible. Candidate 4 is in
  scope. **Canonical text of D27 and D28 (verbatim question + answer):**
  `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/moss-mvp-review/grilling-decisions-20260920-addendum.md`
  — read it before acting on either; it also records that the **pre-terminal** arms stay UNMEASURED and are not closed
  by D27.
- Read before editing: `AGENTS.md`; `prototypes/batch-startup/NOTES.md` (§Minimal production seams, §Controls run B must
  carry); `prototypes/gap/NOTES.md` (§Proposed remedy — design only); `evidence/round4/overlap/attribution.md` and
  `evidence/round4/overlap-review/second-opinion.md` (if D27 = YES); `docs/adr/0002-*`, `docs/design-streaming-diarization.md`
  §7 (settled identity architecture — extend, don't re-litigate).
- Key code paths and why they matter:
  - **A3 seams** (from 3.3's prototype, all verified at base): `moss_transcribe_diarize/app/phase2_file.py:105-141,162-211,332-417`
    — `FileMeetingTasks`; the normalised local source + checkpoint must move to a Meeting-keyed durable directory after
    Meeting creation; URL acquisition retained locally; owner/source/checkpoint validated; the real checkpoint passed at
    `:417` (today `"checkpoint_dir": None`); removal only after durable terminal truth; `file-work` transient root stays
    separate (`clear_transient_work` `:139-141`). `phase2.py:1927-1941` `lifespan` — invoke the File retained-work
    claim/resume **before** `recover_active_meetings` (`:1934`), keep `clear_transient_work()` (`:1941`) after recovery.
    `phase2.py:716-749` `_recover_active_file_meetings` — stays the fallback for unclaimed/invalid/non-resumable rows
    (they finish `interrupted`); if claimed rows become terminal-owned first, no skip list is needed. `phase2.py:751-763`
    `_assert_no_active_meetings` — **unchanged**. `phase2_lifecycle.py:215-236` — apply the same File claim before the
    account-scoped recovery caller (do not call it "after login": base has no real login caller, only account revoke).
    `windowed_transcription.py:197-255` — checkpoint validation/wiring already sufficient.
  - **Gap seams** (from 3.1's diagnosis): `live_transcript_convergence.py:1015-1071` — retain the terminal-local label
    after overlap resolution instead of discarding it from the proposal; `live_lane_decode.py:236 finalize_lanes`,
    `:278-308` — replace the isolated per-segment fallback with one partition-scoped evidence decision (aggregate the
    partition's eligible intervals, one album match at 0.35/0.1, apply the canonical only within that partition), then
    project segments. Lead ruling: run B **may** edit `live_lane_decode.py` for this item only, with one violating
    control. Evidence floors: `live_identity_album.py:45-46,56-57`; `min_segment_samples` = 8,000 (0.5 s) from the manifest.
  - **Fixture seam** (D27): `tests/e2e/verify_demo_lanes.py:60-75` couples the audio cut to the coarse reference row;
    `:27 DEFAULT_MIC_GAIN = 0.03` unchanged; `tools/qualify/run.py:30 CASES`, `:452` ladder feed (24 s meetings).
    Corpus reference: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/reference.jsonl`
    is the **dev tree's** copy — read-only; the candidate carries its own copy under `evidence/live-policy-sweep-20260825/`
    if the tests read it from the repo — check which path the test actually loads before editing.

## Current state

- 2026-09-20 18:xx: base = `round4/integration` after merging run A (`round4/ralph-a` @ `3a56ce7b`: instrument custody +
  budget preflight; suites 2,123/0/5, 312/312) and the pane branches `round4/gap@fd1136d4`, `round4/jamie@992dbb17`,
  `round4/batch@b1e05026`, `round4/overlap@790d8f29+`, `round4/overlap-review@71544133`, `round4/runtime@0b60723c+`,
  `round4/surfaces@25bb06d4+` (prototypes, evidence, xfail controls only — no product change). Exact counts after the
  merges are in `progress.txt`'s header.
- Verdicts you implement: A3 **SUPPORTED** 10/10 through the real `lifespan` (deterministic runner) + real-HF smoke;
  gap **SUPPORTED** — the `S00` arises at finalization: a 4,320-sample span (< 8,000) gets a temporary `speaker-0002`
  that cannot project onto `speaker-0001`; silence does not reset identity; first post-gap score 0.8366; remedy
  controls Adam 0.909 match / Keyu 0.017 abstain; **unmeasured**: raw terminal-local labels — if `seg_0012` was isolated
  in its partition the remedy does not apply (then keep `S00` and record it).
- Verdicts you must NOT implement: Jamie aggregation **FALSIFIED** (3.2) — no code; overlap is **not** a product
  defect (3.4 + 3.1: 0 convergence/publication loss) — only the fixture (D27) may change.
- Known xfail(strict) controls in the tree that must flip when their item lands: `round4/batch` (2, File + URL valid
  retained prefix currently interrupted), `round4/gap` (1), `round4/overlap` (2, only if D27 = YES). Find them with
  `grep -rn "xfail(strict=True" tests/ | grep -i "R4-"`.
- Local HF snapshot for the real-runner smoke: `~/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8`.
- Decoder proxy: `http://127.0.0.1:18400/v1` (lead-owned, 100-request cap, counts in `…/moss-round4/status/proxy-18400-requests.jsonl`).
- **D28 (2026-09-20 18:46):** round-4 GPU total ≈3,300 requests; the 2×1800 capacity confirmation is **deferred** — do
  not run `--long`, and never let `capacity_2x1800: REQUIRED-NOT-RUN` disappear from a summary. **Lead ruling
  2026-09-21: run B is offline — 0 decoder requests, no tunnel, no proxy.** The single decoder-backed confirmation of
  the gap remedy moves to R4-10, where it must retain the raw terminal-local label stream.
- Base after the round-4 merges is `round4/integration` @ **`71f23c0c`**: backend **2,130 passed / 0 failed / 5 skipped
  / 8 xfailed / 37 subtests**, frontend **312/312**, typecheck clean, asset parity clean. **The 8 strict xfails,
  enumerated from the tree (lead-verified 2026-09-21 with `pytest -rx`; an earlier guess in this file was wrong):**
  - **batch 2** — `tests/phase2/test_batch_startup_prototype_controls.py::test_r4_5_base_lifespan_resumes_valid_retained_prefix[file]` and `[url]`
  - **gap 1** — `tests/test_r4_gap_terminal_identity.py::test_r4_3_same_terminal_partition_reuses_eligible_voice_evidence`
  - **fixture 3** — `tests/test_round4_overlap_diagnosis.py::test_r4_6_demo_reference_matches_corrected_audio_population`,
    `…::test_r4_6_ladder_reference_is_bounded_by_captured_audio`, and
    `tests/test_round4_alternation_diagnosis.py::test_r4_keyu_source_reference_matches_audited_audio_population`
  - **Jamie 2** — `tests/test_round4_jamie_violating_controls.py::test_r4_4_compatible_provisional_support_accumulates[durations0]` and `[durations1]`
  - **surfaces 0** — hidden-tab work is blocked-on-session evidence, not a strict-xfail test.
- 2026-09-21 iteration 1 completed the durable-ingress half of A3 in
  `phase2_file.py`: after Meeting creation, File and URL work move from transient `file-work` to
  `file-retained/<account>/<meeting>/`; `owner.json` carries account, Meeting, ingress, source,
  checkpoint locator, and contract version. Product File inference now receives that real checkpoint
  directory. Completed/failed/explicitly interrupted Meeting work is removed only after its terminal
  state; shutdown-retained active work stays available for the future claimant. Focused File/URL suites
  passed 29/29 and registry controls 2/2. **Still open:** no startup claimant yet consumes this retained
  work, so the current generic startup fallback still interrupts an active row; C1--C10 are not yet
  product passes.
- 2026-09-21 iteration 2 completed Candidate 1's claim primitive in `phase2_file.py`.
  `FileMeetingTasks.claim_retained_work(handle)` holds one non-blocking startup lock while the task
  runs, accepts only an exact v1 Meeting owner record plus its local source and the deployed
  `WindowedRunner` checkpoint contract, and otherwise returns `False` without decoder dispatch or
  mutation so the existing interruption fallback remains authoritative. Focused controls: a two-window
  committed prefix resumes with only the remaining calls; owner, source, contract, and non-contiguous
  prefix mutations all refuse with zero new calls and retain an active Meeting/source. `34 passed` across
  the new claim test and the owner-bound File/URL regressions. **Still open:** no `lifespan` or
  account-scoped caller invokes this primitive, so it is not yet a product restart pass and the two
  `round4/batch` xfails remain unchanged.
  This run owns **six** of them (batch 2 + gap 1 + fixture 3) and must convert exactly those to ordinary passes. The
  **two Jamie controls stay xfailed** — R4-4 is FALSIFIED and nothing in this run may make them pass.

## Validation

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
# narrowest: the flipped controls
$PY -m pytest -q -p no:cacheprovider $(grep -rl "R4-5\|R4-3" tests/ | tr '\n' ' ')
# prototype cases as product tests (A3) and the gap replay
$PY -m pytest -q -p no:cacheprovider tests/phase2 -k "retained or resume or startup or recover"
$PY prototypes/gap/reproduce.py 2>/dev/null || ls prototypes/gap/
# widest (required before completion)
$PY -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run && npm --prefix frontend run typecheck
```

## Remaining candidates

1. **A3 — startup ordering** (`phase2.py:1927-1941`, `phase2_lifecycle.py:215-236`): invoke the completed
   `FileMeetingTasks.claim_retained_work` primitive before generic File recovery; claim before `recover_active_meetings`;
   fallback `:716-749` untouched in semantics; `:751-763` byte-identical. Validate: C2/C3/C4/C7/C8/C9/C10; the two
   `round4/batch` xfails flip; `git diff --stat 89f833ac -- moss_transcribe_diarize/app/phase2.py` shows no change in `:751-763`.
2. **Gap remedy — partition-scoped terminal decision** (`live_transcript_convergence.py:1015-1071`,
   `live_lane_decode.py:278-308`): retain terminal-local label; one aggregated match per unmapped partition; project
   only inside it. Validate **both branches**: shared-partition control resolves to the established identity while the
   Keyu control abstains (`round4/gap` xfail flips); isolated-partition control **stays `S00`** and says so. No decoder
   run in this loop — the historical S17 row stays UNMEASURED and belongs to R4-10.
3. **Fixture correction (D27 = YES only)** (`tests/e2e/verify_demo_lanes.py:60-75`, corpus reference): per prd; falsifier
   test = exactly the three class-(a) additions remain.
4. **Full suites + `docs/verify/round4-run-b/VERIFY.md`.**

## Non-candidates

- Jamie / lone-participant aggregation — FALSIFIED; user decision D1 vs D15 pending; no code.
- Any change to `tools/qualify/` (run A's territory) beyond consuming its preflight.
- Any threshold/floor/constant; Stop cap; separator; hidden-tab (needs an Aqua session — measurement, not product);
  runtime packaging (4.1's receipt + `MOSS_TEST_REAL_SQLITE` conftest guard are merged as-is; no pin change).
- `docs/known-limitations-20260918.md` — lead-owned; the lead rewrites L1/L9 rows after the round.
