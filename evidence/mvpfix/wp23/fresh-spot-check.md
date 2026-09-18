# WP23 fresh-context source spot-check — 2026-09-18

**Documentation PASS: 10/10 pinned rows and 5/5 selected numerical claims match.**
This verifies reporting accuracy, not product acceptance or new runtime performance.
Tested documentation: `ff8bcb797ab2f371805de4634ffe02c0f12f634f`, initially clean,
branch `mvpfix/wp23-closure-docs`. Integration remains pinned to
`c609d7f3e03091becda8aa8588655447a51ea434`.

## Method and falsifiers

Independently opened each named source worktree from `source-index.json` using:

```sh
git -C <source-worktree> rev-parse <named-branch>
git -C <source-worktree> log --reverse --format='%h %s' <base>..<tip>
git -C <source-worktree> show <tip>:<verify-result-path>
git -C <source-worktree> diff --name-only <base> <tip>
```

Read each complete result, comparing question, scoped verdict, counts and key
measurements against the ledger. Read WP12 NOTES for earlier serial/concurrent
timings, WP15 REAL-DECODER and primary samples, WP19 resolver JSON and WP20 overlap
JSON where the shorter result did not independently establish a claim. No source
worktree writes or inference calls. Checks detect incorrect revisions, inventories,
counts, numerical scope or acceptance claims; a mismatch would require a document
correction with the original mismatch retained here.

All ten current source branch tips matched their pins when read. Each ledger base,
tip, branch, commit list and changed-file list matches Git; grouped directory and
generated-asset entries cover every changed leaf, with no nonexistent listed path.
Full SHAs/worktree paths remain in `source-index.json`; table paths are relative to
that row's source worktree and were read at its pinned revision.

## Ten primary rows

Counts below are retained source results, not suites executed by WP23 this session.
Subtests remain separate from test-item counts; failed runs remain failures.

| WP | Source tip; commits/files in range | Result path | Exact suite counts | Key measurement / boundary | Documentation verdict |
|---|---|---|---|---|---|
| WP1 | `2ffd80e7`; 6/102 | `VERIFY-RESULT.md` | Python 1718 passed, 3 failed, 2 skipped; 37 subtests. Frontend 206/24 files. | 26/26 saved/final matches and disjoint lane speaker sets; six fixed cases; parity Stop 11.395471 s; 646 historical requests. Two fixture-location failures and old latency fixture retained. | MATCH; scoped lane repair, full Python FAIL. |
| WP3 | `2e7206c7`; 4/57 | `VERIFY-RESULT.md` | Final literal selected Python 455 passed, 2 failed; 19 subtests. Frontend 215/25 files. | Near-speech false suppression 80/12960; echo false pass 3651/4320. Opt-in correlation only; no suppression promoted. | MATCH; guards fixed, suppression falsified, literal verification FAIL. |
| WP6 | `06a6737a`; 5/75 | `VERIFY-RESULT.md` | Final Python 1701 passed, 1 failed, 2 skipped; 37 subtests. Initial 1698 passed/4 failed/2 skipped. Retention 42 passed/19 subtests; frontend 206/24 files. | Five attempts, 13 sessions: 9 complete/4 interrupted. 4x600: 2/4 final; 12/32 foreign-load samples; 3 pauses/269.986569 s; 2887 calls. | MATCH; measured, capacity NOT ACCEPTED. |
| WP8 | `fcb247c2`; 2/30 | `VERIFY-RESULT.md` | 31 ticket, 25 assertion, 12 audit rows; 7 pins/39 paths. Integrated focused Python 22 passed; no full suites. | Actual serializers: legacy 5/5, lane overlap 0/5; label, ordering/end and expected-failure defects retained at this old pin. | MATCH; review findings confirmed, no repair/acceptance at this pin. |
| WP9 | `8f8847fc`; 3/80 | `VERIFY-RESULT.md` | Python 1753 passed, 19 failed, 22 errors, 2 skipped; 1796 items plus 37 subtests. Affected 20/20; frontend 239/27 files. | Six base files reproduce 128 passed/19 failed/22 errors. Saved naming 1/5 before, 5/5 after. | MATCH; rename fixed, inherited full-suite failures retained. |
| WP12 | `a2ee97eb`; 6/89 | `VERIFY-RESULT.md` | Current-context Python 1805 passed, 2 skipped; 37 subtests. Frontend 230/26 files. | 24 s serial 11.327668 -> concurrent acoustic 6.839325 -> mapping candidate 3.788534 s, separate runs. Candidate 60/180 s: 7.490138/16.964282 s; mono180 12.717313 s. 135/135 same-input segments; 54 restored assignments source-backed; 2 turns/16 words unassigned. | MATCH; stopped acceptance, not a new fresh acceptance, not merged. |
| WP15 | `e721fc7d`; 3/80 | `VERIFY-RESULT.md` | Python 1860 passed, 2 skipped; 37 subtests. Frontend 242/27 files; prototype 8/8. | Unpaused 600 s complete, 2589 words, 600 s MP3; Stop 179.408107 s; RSS 631.406/1201.047/1200.516 MiB; 460 calls. Each of three tapes 19.2 MB -> zero; contention 8/27 samples. | MATCH; lifecycle fixed, 1800 s/plateau unmeasured. |
| WP17 | `371af1be`; 4/62 | `docs/verify/wp17/VERIFY-RESULT.md` | Initial Python 1868 passed/1 layout failure/2 skipped; corrected 1869 passed/2 skipped, 37 subtests. Frontend 242/27 files. | Recognition 4/4 API routes, 3.526378542–3.528290542 s; mic 10/48 -> 5/53 additions after source-reference correction; 400000/400000 samples equal; 8/8 saved lane comparisons/628 words; quality 0/2. | MATCH; observation/reference repairs verified, quality FAIL. |
| WP19 | `16460396`; 4/44 | `docs/verify/wp19/VERIFY-RESULT.md` | Python 1889 passed, 2 skipped; 37 subtests. Frontend 249/28 files; lease 20/20 independent runs. | 6/30 min IDs 7->3 / 31->3; correct segments 84/92 / 420/464; overlap seconds 322.11/338.04 / 1592.97/1684.98; zero abstentions. Resolver 62.894428/332.007926 s for 3/15 windows; fresh six-minute replay 62.804387 s. | MATCH; scoped File album acceptance, merged; broader accuracy unmeasured. |
| WP20 | `717daaa8`; 2/36 | `docs/verify/wp20/VERIFY-RESULT.md` | Python 1874 passed, 2 skipped; 37 subtests. Frontend 244/27 files. | Boundaries identical 12/12 system, 10/10 mic; overlap immediate 24/106 and 6/53, final 13/106 and 5/53. 179 replay windows: 137/137 canonical, 30/30 rolling, 11/12 terminal exact; quality 0/2. | MATCH; endpointing remedy rejected, quality FAIL. |

## Five selected numerical claims

| Code | Document / claim | Independently opened evidence and arithmetic | Result / scope |
|---|---|---|---|
| N1 | Attended plan A6: six echo conditions | `2e7206c7:docs/handoffs/attended-echo-protocol.md`, A2: AEC on/off x playback-only/operator-only/double-talk = 2 x 3 = 6. | MATCH; prescribed future conditions, no attended pass. |
| N2 | Attended plan A7: 7/8 phrase words, ordered | `cf8147f5:docs/handoffs/g7-preadmission-runbook.md`, final phrase section: at least 7 of 8, in-order under one speaker distinct from all tab-only speakers; 6/8 fails. | MATCH; existing criterion, not new measured attendance. |
| N3 | Limitations L1: WP20 overlap system immediate 24/106 = 22.64151% | `717daaa8:evidence/mvpfix/wp20/baseline-overlap.json`, `surfaces.pre_terminal.lanes.system`: substitutions 2 + omissions 14 + additions 8 = 24; reference_words 106; WER .22641509433962265. | MATCH; immediate surface only, quality failure preserved. |
| N4 | Limitations L5: resolver 332.007926 s / 15 windows | `16460396:evidence/mvpfix/wp19/accept-real-30.json`: resolver_seconds 332.00792645898764, window_count 15; result A5 states embedding included and retained measurement not rerun. | MATCH; rounded to six decimals; original 30-minute File corpus, not final-head throughput. |
| N5 | Limitations L6: RSS first/peak/final 631.406/1201.047/1200.516 MiB | `e721fc7d:evidence/mvpfix/wp15/real-1789711765822268000/result.json`, 27 primary `resources` records; bytes / 1048576, rounded to three decimals. Checked against `actions.jsonl` and REAL-DECODER.md. | MATCH; primary process samples. Separate independent sampler has different sample instants; neither is a memory ceiling or proof of leak. |

## Additional bounded checks

- **C1 — Missing results and drift:** WP21 `33112b07` has no WP21 VERIFY-RESULT.
  The copied partial summary equals its named source file: 1877 Python passed,
  2 skipped/37 subtests, frontend 244, KeyboardInterrupt, 0 decoder calls.
  Current WP21 branch was `5ae9566f017e5b888d3676e9a3ccb0a007d5917d` when read;
  this later state was not substituted for the ledger pin or qualified here.
  WP22 remains `8938cb2c`, zero commits since its identical base, no WP22 result.
- **C2 — Integration:** actual first-parent log at `c609d7f3` matches all 17
  listed merges. WP4 is an ancestor of WP7; WP19 tip is merged, WP12 tip is not.
  `a92bb4aa` records frontend 230/230; `79467f08` focused export 22/22.
  No final full-Python count appears in those first-parent messages. Current
  integration ref was still `c609d7f3` when read.
- **C3 — Documents:** 22/22 WP headings; 31/31 ticket number/state pairs exactly
  match supplied `github-issues.json` (16 OPEN/15 CLOSED). All six deliverables
  read; 34/34 local Markdown links exist. PR draft retains source pin and release
  exclusions. Attended estimates sum 10+30+30+20+20+10=120 minutes, explicitly an
  estimate; two routes x both source scenarios = four captures. Trusted target
  TLS, physical MacBook/Chrome, viewports, real key, voiceprint cases and open
  decisions retained. No prose grants host authority.
- **C4 — Command/contract scope:** lane CLI supports `--base`, `--case both`,
  `--output`; browser bench supports `all` and enumerates 1..16, with 25/35 s lease
  cases. WP21 command remains conditional on landing. WP19 MP3 exception is only
  explicit File enrollment, not transcription or automatic enrollment; saved
  naming is no longer active-only. WP12 timing/acceptance caveats, WP17/WP20
  failures, quiet additions and WP22 pending state remain intact.
- **C5 — Preparation evidence:** retained full logs confirm Python 1901 passed,
  2 skipped, 37 subtests, 21 warnings, 153.74 s; frontend 249/28 files, 2.59 s.
  These are PREPARATION results, not newly executed tests or release acceptance.
- **C6 — Packaging:** layout gate and whitespace checks passed. Changes since
  `c609d7f3` confined to `docs/` and `evidence/mvpfix/wp23/`. New records contain
  only source pointers, counts and scope; no audio, private transcripts or secrets.

No factual corrections to the six deliverables were needed. Updated only the
pending WP23 verification status and recorded the observed WP21 branch drift.
