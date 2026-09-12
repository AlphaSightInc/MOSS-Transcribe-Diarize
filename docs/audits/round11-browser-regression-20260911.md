# Round 11 browser regression and optional voiceprint saving — 2026-09-11

**13/13 E2E rows PASS** on a fresh isolated stack with both relay models configured and draft lane 1.0 s. Product commit `6b292c40`; initial complete-pass head `ad6e252e` adds only the harness fixture correction. A final full run on rebased head `46aa1ff3` also covers concurrent `463b1d66` (identity-count fields). No identity threshold or first-decode scheduling changes are included.

## F1 — optional voiceprint saving

The speaker-name dialog now has **Save voiceprint**, checked on every opening. Checked sends the unchanged JSON `{ "label": "…" }`; the server defaults an absent flag to enrolment. Explicit `save_voiceprint: true` does the same. Unchecked sends `save_voiceprint: false`, persists the meeting name, returns `enrollment: "not_requested"`, and does not create/update a voiceprint sample or queue future enrolment. It cancels a prior pending enrolment for that speaker.

For an already linked speaker, rename-only detaches this meeting speaker from the saved profile; the bank profile and its samples remain unchanged. The existing manual-label protection prevents automatic recognition from replacing this meeting-local name. Checked retains the previous bank-linked rename behavior. Dialog and button accessible names are unchanged; no acceptance selectors changed.

Validation: checked/unchecked UI requests and displayed names; explicit true/false and absent API flag; invalid flag rejection; rename-only with no prior intent, pending intent, and an enrolled profile; later observation cannot fulfil cancelled intent. The exact required `voiceprint-lifecycle` command passes **61 tests, zero skips**. Full suite: **1,421 Python passed, 2 skipped, 37 subtests passed; 201 frontend passed**. Focused frontend: 25 passed; typecheck and production asset build passed. Full-suite skips concern optional local corpus fixtures; no browser or required voiceprint tests skipped.

## F2 — all 13 checklist rows

Baseline is the retained original `evidence/e2e-feature-verification-20260911/results.json` (10/12). Row 13 was added later, so its comparison is with the accepted network-resilience evidence. Each linked row JSON names its screenshot and checked artefacts; the complete network trace is retained alongside it.

| Row | Check | Original → current | Evidence |
|---:|---|---|---|
| 1 | Fresh workspace | PASS → **PASS** | [Fresh signed-in workspace; boot ready](../../evidence/round11-browser-regression-20260911/rebased-head/row-01.json) |
| 2 | File transcription | PASS → **PASS** | [50 s corpus; completed; WER 8.70%](../../evidence/round11-browser-regression-20260911/rebased-head/row-02.json) |
| 3 | URL transcription | PASS → **PASS** | [URL corpus; completed; WER 8.70%](../../evidence/round11-browser-regression-20260911/rebased-head/row-03.json) |
| 4 | Live dual-lane capture | PASS → **PASS** | [First visible text 2.339 s; Stop → completed 2.069 s](../../evidence/round11-browser-regression-20260911/rebased-head/row-04.json) |
| 5 | Speaker naming / default enrolment | PASS → **PASS** | [Both rename entry points; history and export updated](../../evidence/round11-browser-regression-20260911/rebased-head/row-05.json) |
| 6 | Five transcript exports | PASS → **PASS** | [MD, TXT, JSON, SRT, VTT checked](../../evidence/round11-browser-regression-20260911/rebased-head/row-06.json) |
| 7 | Completed audio download | PASS → **PASS** | [50.0 s MP3; decoded successfully](../../evidence/round11-browser-regression-20260911/rebased-head/row-07.json) |
| 8 | Interrupted capture / partial audio | PASS → **PASS** | [Interrupted status; decodable 11.412 s partial MP3](../../evidence/round11-browser-regression-20260911/rebased-head/row-08.json) |
| 9 | Both relay summaries | FAIL → **PASS** | [MacStudio and RTX4090: current, validated, rendered summaries](../../evidence/round11-browser-regression-20260911/rebased-head/row-09.json) |
| 10 | Enrolled speaker recognition | FAIL → **PASS** | [Bank present; visible enrolled name 3.700 s ≤ 4.0 s](../../evidence/round11-browser-regression-20260911/rebased-head/row-10.json) |
| 11 | History / selected header | PASS → **PASS** | [Selected title/mode and header visible](../../evidence/round11-browser-regression-20260911/rebased-head/row-11.json) |
| 12 | Phone layout | PASS → **PASS** | [400 px viewport; scroll width 400 px; anchors visible](../../evidence/round11-browser-regression-20260911/rebased-head/row-12.json) |
| 13 | 3 s and 20 s origin outages | Later PASS → **PASS** | [Both outages survived; frame sequences continuous; completed/final](../../evidence/round11-browser-regression-20260911/rebased-head/row-13.json) |

Row 10 retains the 4.0 s criterion for this measurement. Its first canonical span remains 40,000 samples / 2.5 s: queue wait **0.1980 ms**, canonical processing **538.876 ms**, decoder **150.547 ms**. The visible enrolled name appeared **3.6999 s** after Start click. Raw `row-10-decoder-events.json` retains the runner timing and draft publications.

Row 13 blocked the entire application origin, including frame uploads, heartbeat, snapshots and events. After 3 s, the first microphone/system frame recovered in **0.272/0.356 s**; after 20 s, **0.286/0.361 s**. Both preserved sequence continuity, showed restored-connection feedback, retained playable audio, and reached `completed` / `final` with no failure reason.

## F3 — first-pass failures retained, not erased

The first uninterrupted all-row attempt at `6b292c40` passed 10/13. Row 10 reused the capture document after Stop/reload and reached **Invalid state** when sharing tab audio, before a second live session existed. Row 8 then raised a missing `enrollment_live` KeyError because its prerequisite had not created a session. The first row-13 variant reused that failed capture document and also failed setup; the independent new-page 20 s variant passed. Screenshots, row JSON, network trace and full first-pass result are retained under `first-pass/`.

This repeat-capture Invalid state was already documented in the original E2E, first-match and outage audits. It is an **unresolved repeat-capture limitation**, not evidence that the new checkbox caused a regression. Reproduction: complete a capture, Stop, reload the same capture page, enable microphone and Share audio; the screenshot shows disconnected lanes and Invalid state instead of Start capture. The browser rejection is known; the underlying lifecycle cause remains unisolated here. No product fix is claimed.

The harness correction makes the previously measured independent-fixture protocol executable in one invocation: a new capture page for row 10 and for each outage, same authenticated browser workspace; bring the capture page to the foreground; report row 8 as blocked if row 10 did not admit a session. It does **not** reload or replace any session during an outage. A second full 13-row run used a newly started stack and entirely separate database/workspace; all rows passed. No row was silently retried or overwritten. This qualifies the independent scenarios, not repeat capture in one document.

## Reproduction and scope

```sh
.venv/bin/python tests/e2e/verify_workspace.py \
  --base https://127.0.0.1:17863 \
  --corpus /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s \
  --output /tmp/moss-round11-e2e-20260911/attempt3/artifacts
```

The final rebase brought in `463b1d66`, so the completed `ad6e252e` pass remains under `final/`, and a third full run with a fresh stack/database at `46aa1ff3` is retained under `rebased-head/`. All 13 rows passed again. The late integration’s focused regression passed **177 tests and 9 subtests**.

The output directory above is the retained completed run; use a new directory for another full attempt. Current launcher, relay configuration, measured commits and isolated state paths are retained in `evidence/round11-browser-regression-20260911/environment.json` and `local_launcher.py`. Launcher copies the existing local-stack pattern, changes only port/state/control paths, points `sys.path` at this worktree, sets both MOSS_LLM_UPSTREAMS entries, and adds `--live-draft-lane-seconds 1.0`. The pre-existing local SQLite-runtime override is retained and explicitly limits this to local verification. The existing self-signed certificate and decoder tunnel at `127.0.0.1:18000` were reused.

No host operations, vLLM changes, port-17861 service changes or database access. Cookies/browser storage and databases are excluded from committed evidence. Full Python/frontend suites ran during the first pass; the second and third full passes ran after they finished. The isolated port-17863 instances were stopped after measurement; their separate databases remain retained.

## Scheduling permission received during the run

The operator now permits earlier first-decode scheduling while preserving identity thresholds. This completed candidate remains on the previously accepted decode geometry so its measurements stay attributable. Timing implementation scope was queried separately; no earlier-decode prototype has been shipped as part of the checkbox or regression task.
