# WP7 fresh-context verification — PASS (offline); prototype MIXED

Verified 2026-09-18 in a fresh conversation, from the supplied worktree documents,
without the implementation conversation. This replaces the inherited placeholder.
Branch: `mvpfix/wp7-identity-stress`.
Source SHA: `5509a757eaecab8df190f449c7a03d1d3fa729a5` (initial worktree clean).
Comparison base: `a7bb4201`.
Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp7-identity-stress`.

## F1 — Fresh checks and their meaning

Executed VERIFY.md's command literally from this worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/mvpfix/wp7/verify_offline.py
```

- Overall exit **0**; **25/25** booleans true in `evidence/mvpfix/wp7/fresh/checks.json`.
- Import resolves to this worktree's `moss_transcribe_diarize/__init__.py`.
- Phase-2: **811/811 passed**, **0 failures**, **21 warnings**, **114.37 s**.
- Frontend: **5/5 passed**, **2/2 test files**, **0 failures**, **1.06 s**.
- Protected policy diff: exit 0, empty; **7/7** specified files unchanged.
- No production, test, policy, lifecycle, or verification-script changes this session.
- Fresh logs: `evidence/mvpfix/wp7/fresh/{import,phase2,frontend,policy-diff}.txt`.

These checks detect wrong-tree imports, regressions, policy drift and inconsistent
retained counts. A failure would require recording it and repairing only an actual
in-scope defect. No such failure occurred. Green evidence checks include preservation
of known failing observations; they do not mean all acoustic cases passed.
Warnings are dependency deprecations (21 Python warnings), Vite's future native-config
compatibility warning, and Node's missing localstorage path warning; suites exited 0.

## F2 — Part 0 source inspection and outcomes

Read `NOTES.md`, `PART0.md`, `verify_offline.py`, COMMON.md and plan sections 1–2;
inspected the production/test/runbook diff against `a7bb4201`, including the base
quality constants and base oracle rejection conditions, independently of test success.

- `phase2_g7_canary.py`: ordered subsequence matching within one speaker replaces
  exact contiguous matching. The fixed eight-word phrase accepts 7/8 or 8/8 matches;
  one omission/substitution and inserted words are tolerated. 6/8 and reversed order
  fail. Operator and tab speakers must remain disjoint. Retained prototype: **5/5**
  intended outcomes; fresh parameterized tests and existing separation control pass.
- `lane_word_oracle.py`: adds attribution segment diagnostics and separately counts
  errors only for legacy segments strictly straddling a supplied switch. Explicit
  lane ownership and segments starting at/after the switch remain strict failures.
  No invented numeric time-radius exemption. This is a new instrument rule, not a
  new WER (word error rate) bar. Boundary/interior/explicit controls pass freshly.
- `tests/e2e/verify_demo_lanes.py`: supplies the alternation switch and reports the
  separate file/URL **0.15** bar without changing live acceptance.
- Tests changed: `tests/phase2/test_attended_g7_canary.py` and
  `tests/phase2/test_lane_word_oracle.py`; documentation changed:
  `docs/handoffs/g7-preadmission-runbook.md`. Its phrase sentence has a cosmetic
  inherited-diff wording defect, "the at least"; no semantic ambiguity or fix needed.
- Retained Part-0 regression run: **64 passed**; it is not an additional fresh run.

Original WP4 alternation predicates (`evidence/mvpfix/wp4/live-lane-results.json`):

| Surface | System WER | Microphone WER | Attribution | Duplication | Failed predicates |
| --- | --- | --- | --- | --- | --- |
| Pre-terminal | 16/106 = 0.150943, pass | 16/48 = 0.333333, fail | 2, fail | 0, pass | Microphone WER; attribution |
| Final | 11/106 = 0.103774, fail | 6/48 = 0.125000, fail | 2, fail | 2, fail | Both WERs; attribution; duplication |
| Reopened | 11/106 = 0.103774, fail | 6/48 = 0.125000, fail | 2, fail | 2, fail | Both WERs; attribution; duplication |

The live bars **0.166655 immediate / 0.095074 final** and zero attribution/duplication
requirements already existed at `a7bb4201`; WP7 did not invent them. Under the separate
0.15 file/URL WER bar, both final/reopened lanes pass and both pre-terminal lanes fail.
That does not erase attribution failures or replace the live contract. Original WP4
counts lack segment timestamps: boundary versus interior remains **UNKNOWN**.

Part-0 live retry consumed **20/20** calls and ended with heartbeat/Stop HTTP 409 at
the harness cap. **Interrupted, not passed or confirmed**. The 54 s fixture requires
at least **22** canonical 2.5 s spans before finalization; 20 calls cannot finish it.
Completing it needs separately authorized additional decoder budget; no retry here.

## F3 — Per-case identity verdicts (retained observations)

**13/13** identity meetings completed with final output. The following are retained
measurements checked against records, not newly run acoustic qualification.

| Case | Concrete verdict |
| --- | --- |
| `single` | PASS: 1 birth, 1 final-used ID; Adam 0 switches across 16 scored segments. |
| `gap` | FAIL extra birth: 2 born, only 1 finally used; Adam 0 switches across 15 segments. Extra birth at 25.25–27.75 s inside inserted 25–35 s digital silence. WP3 silent-span admission finding, not final transcript over-splitting. |
| `alternating` | Identity PASS within scoring scope: 2 born/used IDs; Bill 0 switches/11 segments, Keyu 0/6. One switch-straddling segment excluded. Word attribution/duplication FAIL separately below. |
| `enroll` | PASS: active naming initially pending; eligible evidence later yields one profile/sample; saved label retained. |
| `recognition` | PASS: known voice gets correct API name at 3.52034775 s, below existing 4 s reference bound. Browser first-name timing unmeasured. |
| `unknown` | PASS abstention: unknown Keyu retains anonymous S01, no known name assigned. |
| `after_delete` | PASS abstention/hygiene: same voice receives no deleted name; bank empty. |
| `three_seconds` | No naming test occurred: Stop preceded first decode; no action, empty bank. |
| `three_seconds_waited` | PASS pending behavior: active naming HTTP 200/pending, saved display label, empty bank at Stop; provisional evidence only. Recording duration is not eligible speech duration. |
| `lanes` | WP1 baseline FAIL against future lane separation: same voice simultaneously on both lanes produces 1 birth/used ID, not 2. Current unscoped behavior retained. |
| `replacement` | PASS new-profile creation after deletion: early actions pending; final new profile has 1 sample and replacement label. |
| `eligible_replacement` | 8 s attempt still pending; same replacement profile renamed, sample count remains 1. Not evidence of completed new-sample enrollment. |
| `confirmed_replacement` | PASS: 12 s follow-up with eligible evidence uses same profile, count 1→2; immediate repeated enrollment stays 2; renamed label persists. |

Rename propagation: selected saved History transcript and reload retain the name;
**5/5** browser downloads (md/txt/json/srt/vtt) match names, words, timing and identity.
History cards have no speaker-name field. Post-Stop/reload naming HTTP 404 follows the
unchanged active-only mutation contract; it is not a regression.

Retained production CPU probe: **2/2** known matches correct, **2/2** unknown abstentions;
**3/3** eligibility outcomes: 1.99 s rejected, 2 s and 3 s accepted. Five embeddings
were computed in that earlier run; neither it nor the older 470-probe bench was rerun.

## F4 — Concrete mixed verdict and limits

Stable final IDs, recognition/abstention, rename persistence and bank sample hygiene
coexist with an extra silent-span birth, missing per-lane identity separation, and
wrong/duplicated words. Therefore the universal "every stress case passes" claim is
falsified; no identity-policy change is justified by these observations.

The separate mono alternating case has **2 attribution errors + 2 duplicate words**
at **29.02–30.05 s**, after the exact **29.00 s** switch: **0** boundary-exempt words,
oracle **false**. Both voices actually entered SYSTEM; inferred voice grouping is not
physical lane evidence. For the first **154** reference words, Bill WER **10/106**,
Keyu **6/48**. Scoring selects output ending <=54 s and may omit boundary words; the
repeated final 6 s lacks word timestamps and was not given a guessed reference.
This does not localize the original WP4 failure or qualify a repaired dual-lane path.

Budget: **149/150** identity decoder calls (**130 initial + 19 follow-up**), plus
**20/20** Part-0 calls = **169 retained decoder calls**. **0 new provider/decoder calls**
this session. Album dispositions count observations, not people; unpublished
abstention counts remain **UNKNOWN**. No attended capture or browser latency claim.

## F5 — Deviations and session scope

- No substantive discrepancy from NOTES.md's measured verdict found. Its statement
  that fresh verification awaits this result is now superseded by F1.
- Prior measurement deviations remain disclosed: batch traces instead of an
  interactive TUI; initial observer class-name error corrected before requests;
  initial stacks inherited system TMPDIR and created/removed provider WAVs there,
  corrected for follow-ups. Retained artifacts remained in WP7.
- VERIFY.md names MOSS:3.4; the user identifies Fable/MOSS:2.1. Verification ran in
  this fresh conversation; no pane switch or peer message was required or sent.
- Literal verifier sets TMPDIR/npm cache inside WP7 and reuses existing dependency
  symlink. No install, new prototype/live measurement, push, merge, deployment or
  shared-service restart. No server/tunnel started; prior cleanup records ports
  17867/18107 stopped (not represented as a new live port measurement).
- Additional work was read-only source/retained-evidence inspection. One optional
  config glob and one legacy PRD-path lookup found no file; neither is a verification
  failure or affects the completed command. No relevant prior memory hit was used.
- Only this result and fresh verification logs are committed by this session.
