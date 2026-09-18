# WP32 fresh-context verification result — 2026-09-18

**PASS: 10/10 audit statements accurate; 0 discrepancies. Not product acceptance.**
The audit retains 6 scoped PASS, 3 QUALIFIED and 1 FAIL product rows. F1–F5 remain
for lead disposition; no production or test fixes made.

## Session and source custody

- Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp32-final-crossreview`.
- Branch: `mvpfix/wp32-final-crossreview`; initially clean.
- Actual `CODEX_THREAD_ID`: `01a0b3b4-01b2-7e93-8055-ea384b226f27`.
- Drafting thread from retained file: `01a0b3a8-76ee-79d1-8136-01518e7c6e10`.
- Initial HEAD/audit commit: `2df225bb1b2c2e9a64c4080557b427e73f89c3bd`.
- Review base: `37979e539f04d4ea740a1a94d021cd3bb894a0e2`.
- Integrated source: `d8fa767f3ccbb577584643d7e23f80f55d92b2f5`.

This fresh session began from the user's verification assignment and read COMMON,
WP32 brief, AGENTS, VERIFY, audit and NOTES before adjudicating. The identities
differ; no dispatch log existed or was used as proof. Source at verification is
unchanged from the integrated source SHA. This result is committed with the audit
link and fresh evidence; the enclosing commit identifies the completed record.

## Ten-row result

Exactly V1–V10 checked independently: **V1 PASS; V2 PASS; V3 PASS; V4 PASS;
V5 PASS; V6 PASS; V7 PASS; V8 PASS; V9 PASS; V10 PASS** for accuracy.
Detailed sources, base-object comparisons, falsifiers and outcomes:
[fresh-spot-check.md](../../../evidence/mvpfix/wp32/fresh-spot-check.md).

| Category | Confirmed result |
|---|---|
| Protected invariants | 12 audit invariant entries checked through V1/V2; 0 protected numeric/token/parser changes. Aggregate tapes can use 3× one-tape cap; accepted Stop intentionally releases helper lease. Server drain infinity predates base. |
| Weakened tests/evidence | 19 deletion-bearing files; 5 justified frontend unit assertion replacements; 0 removed Python assertions; 1 weakened E2E gate (F4); 2 new optional real-WAV skips; 0 new xfails. F5: 3 valid mutation controls, 2 invalid terminal controls. |
| Privacy/security | 0 new actionable findings in inspected paths. Owner-bound rename and fixed failure messages pass fresh controls. Engineering artifacts intentionally contain local paths, loopback URLs and public-corpus text; not universally content-free. |
| Concurrency/lifecycle | 0 additional race/early-publication/cleanup defects found at checked seams. 1 terminal aggregation defect F1 remains; native hangs and real-encoder parallel parity unmeasured. |
| Legacy compatibility | 1 representation divergence F3; 4/5 export formats byte-identical on the synthetic legacy witness. JSON 497→523 bytes. No-lane persistence and legacy resolver selection covered; all-input/real-ASR parity unmeasured. |
| Frontend | 1 pre-existing recovery defect F2; 0 unsafe production HTML sinks found. Fresh ended-track witness confirms configuring with Reset absent. |

## Executed commands and exact counts

Ran `sh evidence/mvpfix/wp32/fresh-probes.sh` literally once, exit 0; its five
executable checks plus three fresh full gates total **8**. Source/log inspection
commands are not counted as passing tests. No test/probe command failed or retried.

| Check | Result | Evidence under `evidence/mvpfix/wp32/` |
|---|---|---|
| Python import | Resolves inside assigned worktree | `fresh-import.txt` |
| Legacy export probe | 4/5 identical; md 72/72, txt 69/69, srt 91/91, vtt 99/99 bytes; JSON 497/523 | `fresh-legacy.jsonl` |
| Native finalizer/compositor/publication probe | none/system/microphone flags false/true/false; 2/3 correct; 3/3 applied/final | `fresh-truncation.json` |
| Actual ControlPanel ended-track witness | 1 passed, 23 filtered; configuring, Reset false; 551 ms | `fresh-reset.txt` |
| Focused Python, seven files | 108 passed, 2 skipped, 4 warnings; 11.68 s | `fresh-focused.txt` |
| Entire Python suite | 1941 passed, 4 skipped, 21 warnings, 37 subtests passed; 184.44 s; exit 0 | `fresh-python.txt`, `fresh-python-status.txt` |
| Entire frontend suite | 265 passed / 28 files; 2.66 s; exit 0 | `fresh-frontend.txt`, `fresh-frontend-status.txt` |
| TypeScript typecheck | exit 0 | `fresh-typecheck.txt`, `fresh-typecheck-status.txt` |

Full Python command, from this worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp32/full" \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run --configLoader runner
npm --prefix frontend run typecheck
```

Prior full logs independently opened: Python 1941 passed/4 skipped/21 warnings/
37 subtests, 182.76 s; frontend 265/28 files, 2.95 s; typecheck exit 0.
Retained `skips.txt` identifies two new optional WP28 real-WAV cases and two
existing external identity/F-cert corpus cases. Fresh focused log again identifies
the WP28 skips. These are unmeasured cases, never coverage passes.

## Remaining findings and required action

- **F1 — P2, new:** `moss_transcribe_diarize/app/live_lane_decode.py:339,347` loses
  microphone-only truncation by inheriting the system template flag. Combine lane
  flags with OR, add asymmetric coverage, adjudicate other template diagnostics.
- **F2 — P2, pre-existing:** `frontend/src/capture/captureClient.ts:1110` does not
  notify pre-session failure; `frontend/src/components/ControlPanel.tsx:429` offers
  Reset only in error/terminal. Route failure through existing cleanup/error callback
  and verify recovery. Blame and WP27 evidence predate this change.
- **F3 — P3:** `frontend/src/lib/transcriptKeys.ts:16–18` changes legacy no-ID,
  no-lane JSON target keys. Preserve old keys if byte compatibility is required,
  or explicitly accept the representation change. Words/timing/labels unchanged.
- **F4 — gate qualification:** `tests/e2e/verify_workspace.py:387,707` lets missing
  models SKIP and exit 0. Acceptance must inspect SKIP counts; if CLI success is
  the required-summary gate, restore non-success for the unmeasured required row.
- **F5 — evidence limitation:** `evidence/mvpfix/wp12/fixture-mutations.txt:116,136`
  records two invalid terminal controls (missing `gaps` TypeError). Qualify the
  historical efficacy as 3 valid/2 invalid; repair/rerun those two controls only
  if valid five-control efficacy is required.

**Trivial fixes: none.** Only verification documentation/evidence and audit's final
link changed. No audit discrepancy found; the three prototype universal claims
(all-lane truncation, universal Reset recovery, legacy byte parity) remain falsified.

## Limits, deviations and cleanup

User explicitly requested full suites, overriding VERIFY step 4's instruction to
reuse prior full-suite logs. Otherwise the ten-row contract was followed. Automated
retained probes replace interactive TUI as explicitly prescribed. No source rebuild:
no production/assets changes. Browser devices and decoder results were simulated;
no GPU, model dispatch, physical capture, shared-service, deployment, push or merge.

Some guessed read-only paths were absent and corrected; the original public WP17
long reference was read from the main tree without writing there, corroborated by
the retained decode in this worktree. Details in fresh-spot-check.md. No secrets,
audio or database files added to evidence; retained text contains only synthetic
probe data, source paths, test diagnostics and counts. Own `.wp32/fresh` and
`.wp32/full` scratch and temporary WP32 test source removed after completion.
No owned test/server/process roots remain. Source/docs whitespace check passes;
raw native logs retain their original formatting. Production/test diff versus
`d8fa767f` is empty.
