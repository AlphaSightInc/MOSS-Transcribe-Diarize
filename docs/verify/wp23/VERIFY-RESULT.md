# WP23 fresh-context verification — 2026-09-18

**PASS: 10/10 pinned ledger rows and 5/5 selected numerical claims match their
source evidence. No factual corrections required. Product acceptance remains
incomplete.** Detailed rows, source paths, exact counts and additional checks:
[fresh-spot-check.md](../../../evidence/mvpfix/wp23/fresh-spot-check.md).

## Provenance and question

This conversation received the user's fresh-context assignment without the prior
WP23 drafting conversation. Started in the requested worktree on
`mvpfix/wp23-closure-docs` at `ff8bcb797ab2f371805de4634ffe02c0f12f634f`, clean.
That is the tested documentation SHA; this verification commit only adds records
and updates NOTES. No literal prior `/new` execution or tmux pane identity was
independently observed; neither is inferred from a queued command file.

Read local AGENTS.md, COMMON.md then WP23 brief, execution plan sections 1–2,
VERIFY.md, NOTES and all six deliverables. Read COMMON's prototype instructions;
the prepared census is sufficient for this documentation-only verification,
without a new algorithm or prototype. Memory supplied evidence/qualification
boundary guidance only; current Git objects and reports supply every result.

Question: does the closure ledger agree with independently opened source revisions?
Necessary distinctions: revision, scoped result, measured population and remaining
acceptance boundary. Invariants: preserve pins, denominators, failures and missing
evidence; documentation only. Unknowns remain below. Falsifier: wrong SHA/range,
changed-file inventory, count or verdict, or branch evidence promoted to release
acceptance. Each executed check addresses one of these; no runtime test required.

## Freshly executed checks

- **F1 — Ten source rows PASS:** WP1, WP3, WP6, WP8, WP9, WP12, WP15, WP17,
  WP19, WP20. Ran pinned `git -C <source> log --reverse --format='%h %s'
  <base>..<tip>`, `show <tip>:<VERIFY-RESULT path>` and `diff --name-only`.
  Read each complete result; matched question/verdict, every reported suite count,
  key numbers, commits and all changed files. No missing/extra ledger file entries.
  All ten branch tips matched their pins when read. Source failures remain visible.
- **F2 — Five numerical claims PASS:** six echo conditions; ordered 7/8 G7 phrase;
  WP20 overlap immediate system 24/106 = 22.64151%; WP19 resolver 332.007926 s /
  15 windows; WP15 primary RSS 631.406/1201.047/1200.516 MiB. Sources and arithmetic
  retained in N1–N5 of the spot-check. Measurements were not rerun.
- **F3 — History/missing-result checks PASS:** WP21 has no fresh result at
  `33112b07`; copied partial dry run remains failed before decoder use. WP21's
  branch has advanced to `5ae9566f`; no repin or claim about later acceptance.
  WP22 has zero commits/result since base `8938cb2c`; inherited ancestry is not a
  WP22 merge. Actual first-parent history at `c609d7f3` confirms all 17 merges,
  WP4 via WP7, WP19 merged, WP12 not merged, frontend 230/230 and focused export
  22/22 messages, and absence of a final full-Python count in those messages.
- **F4 — Six deliverables consistent:** 22 ledger rows; 31 original ticket states
  preserved (16 OPEN/15 CLOSED); 34 local links, zero missing. Attended plan keeps
  120 minutes as estimate, physical/trusted prerequisites, both scenarios on each
  route, visual/provider/voiceprint checks and explicit decision boundaries. Smoke
  CLI arguments/16-case enumeration match source; WP21 remains conditional.
  File MP3 enrollment exception and saved naming scope are correctly limited.
- **F5 — Packaging PASS:** `bash scripts/check_verify_layout.sh`, `git diff --check`
  and staged whitespace check pass. Inspected changes since `c609d7f3`: only
  `docs/` and `evidence/mvpfix/wp23/`. New text contains no secrets/private content.

## Preparation counts, not fresh execution

Read retained full-suite logs: **1901 Python passed, 2 skipped, 37 subtests,
21 warnings, 153.74 s; 249 frontend passed / 28 files, 2.59 s.** These were run
before VERIFY.md by preparation on the integrated base. No Python/frontend suite,
benchmark, decoder/provider request or attended run was executed this session.
This result must not be used as same-head speech, capacity or host qualification.

## Files, corrections and open boundaries

Added this result and `evidence/mvpfix/wp23/fresh-spot-check.md`; updated
`evidence/mvpfix/wp23/NOTES.md` from pending to completed documentation verification.
The six deliverables remain unchanged: campaign ledger, production contract, PR
draft, attended plan, operator smoke handoff and known limitations. Zero factual
corrections; WP21 drift recorded explicitly instead of silently updating pins.

- **D2 / P3:** retention/error bar and exact input/reference population.
- **P4:** permitted speakers-route fallback if physical AEC remains inadequate.
- **D3:** shared/open workspace internal convenience versus supported product mode.
- **D5:** safe file/URL failure explanation as a release gate.
- **P2:** attended echo/G7 scheduling; headphones and speakers both required.
- **P5:** same-lane simultaneous-speech exclusion/limits.
- **S1:** numerical summary reliability population/tolerance and semantic review.

WP17/WP20 quality remains 0/2; quiet-mic additions remain. WP12 acceptance stopped
and unmerged; WP19 resolver cost/attribution errors remain corpus-scoped. WP15
600 s completion is not 1800 s durability or memory plateau; WP22 pending at pin.
Final-candidate capacity, real summaries, attended/visual and host acceptance remain
unestablished. No acceptance threshold or product policy changed.

Deviation: no new deviation from VERIFY.md; prior preparation's scripted census
and non-root verification layout remain documented. No second reset, other-tree
writes, product/test changes, GPU/network requests, processes/tunnels/services,
peer messages, push, merge, rebase, deployment or GitHub writes. Local commit only.
