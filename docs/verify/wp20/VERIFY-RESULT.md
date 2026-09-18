# WP20 fresh-context verification — 2026-09-18

**Verification PASS; prototype REJECTED_NO_OVERLAP_WIN; product quality FAIL.**
No production fix is justified by the retained overlap experiment.

Branch: `mvpfix/wp20-lane-endpointing`.
Tested SHA: `8b46938aedc97fc50167f08ceb7838def0a159a6` (initially clean).
Production comparison base: `de35ef365724caad47c407bd41c34e21182d20c7`.
Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp20-lane-endpointing`.
Read AGENTS.md, COMMON.md, WP20 brief, execution-plan sections 1–2,
prototype skill, both WP20 NOTES files, COMMANDS.md, and the branch diff.
Import resolved to this worktree's `moss_transcribe_diarize/__init__.py`.

## V1 — fresh execution

Executed every command in VERIFY.md with its specified Python, environment,
scratch plugin, basetemp, and frontend native/no-cache flags. Commands are in
VERIFY.md; counts-only outputs are under `evidence/mvpfix/wp20/fresh-*`.

| Gate | Fresh result | Failure addressed |
| --- | --- | --- |
| `evidence/mvpfix/wp20/audit.py` | exit 0; evidence PASS, prototype rejected, quality FAIL | stale counts, altered geometry/policies, missing raw evidence |
| Full Python suite | exit 0; 1874 passed, 2 skipped, 21 warnings, 37 subtests passed; 150.98 s | backend regressions |
| Full frontend suite | exit 0; 244 tests / 27 files passed; 2.62 s | frontend regressions |
| Typecheck | exit 0 | type errors |
| Build | exit 0 | build failure |
| Asset diff | exit 0, empty | stale or changed packaged assets |
| `git diff --check` | exit 0 | whitespace errors |
| Listeners 17880/18120 | exit 1, no output | leftover measurement server/tunnel |

Python skips: operator-owned identity corpus and real F-cert speaker corpus are
not provisioned. Existing warnings retained, including frontend Node warnings.
Original log bytes copied to ignored `runs/wp20/fresh-*.raw`; only trailing
whitespace normalized in committed text logs. No assertion or product edit.

Supplemental offline check: re-scored raw immediate/final/reopened snapshots
against the accepted full references, matching all 6/6 published surface records
(12 lane scores). Re-parsed all 4/4 raw padding responses and reproduced their
error counts. Result: `fresh-surface-audit.json`. This closes the recipe audit's
use of already-scored baseline surfaces; no decoder requests were made.

## F1 — endpointing hypothesis falsified for the reported full-reference overlap

Question: does speech on the other lane move this lane's cut points and cause
its errors? Necessary distinctions: admitted audio, cut interval, decoder answer,
published surface, independent reference. Changing endpoint ownership preserves
all other production settings and the 40000-sample hard cap.

Mixed versus lane-local nonzero intervals match exactly: system 12/12, microphone
10/10. Canonical words and WER are unchanged: 18/106 and 9/53. The proposed cause
does not occur in this case; the explicit no-overlap-win falsifier blocks promotion.
This is not a claim that every possible input has identical boundaries: the
48-second microphone control does change, but lacks an exact partial reference.

## F2 — per-stage WER and the immediate-surface residual

WER = substitutions + omissions + additions, divided by reference words.
Canonical-all includes Stop-flushed spans; local is a shadow intervention, not
a candidate live surface. Values below are errors/reference words.

| Case / lane | Immediate | Canonical pre-Stop | Canonical all mixed → local | Final / reopened | Terminal alone |
| --- | ---: | ---: | ---: | ---: | ---: |
| Alternation / system | 16/106 | 18/106 | 18/106 → 18/106 | 9/106 | 11/106 |
| Alternation / microphone | 11/53 | 15/53 | 11/53 → 9/53 | 5/53 | 5/53 |
| Overlap / system | 24/106 | 26/106 | 18/106 → 18/106 | 13/106 | 13/106 |
| Overlap / microphone | 6/53 | 9/53 | 9/53 → 9/53 | 5/53 | 5/53 |

Overlap system immediate WER is 22.6415% versus alternation 15.0943%.
The eight-error gap is an unfinished tail at the pre-Stop snapshot: 28.5 s
accepted, 27.5 s committed out of 29 s speech. Completing the tail removes eight
canonical omissions (26 → 18). Alternation already committed all system speech.
Rolling replacement improves each system surface by two errors (26 → 24 and
18 → 16); it does not explain the gap. The remaining canonical recognition errors
reproduce on the same bounded lane audio alone. Overlap microphone immediate
6/53 consists of six additions. These are not evidence of mixed-boundary damage;
signal-to-noise ratio (SNR) causation was not measured.

Unchanged bars: immediate ≤16.6655%, final ≤9.5074%. Alternation fails immediate
microphone; overlap fails immediate and final system. Both complete cases FAIL.
The alternation microphone's local canonical gain (11 → 9 errors) leaves
9/53 = 16.9811%, above the immediate bar, and does not remedy overlap.

## F3 — final errors survive standalone decoding

Same-boundary independent replay matches canonical 137/137, rolling 30/30, and
terminal 11/12 windows. Alternation system terminal varies; the difference was
retained. Overlap system final 13/106 reproduces alone, without coordinator or
lane merge. Final and reopened surface scores match in both cases.

System speech is identical for 464000 samples (29 s); alternation appends 400000
zero samples (25 s). Paired standalone trials give alternation/overlap errors
9/13 and 11/13, each over 106 words. Thus decoder output depends on full-tape
silence context, with variability even on identical alternation audio. The data
do not isolate the decoder's internal cause or support a lower-SNR explanation.
These ≤54-second inputs never reach the 150-second terminal window seam.

## F4 — limits, budget, deviations

All 6/6 retained captures completed/finalized. Exact 24/48-second and per-span
WER remain UNMEASURED: no independently word-aligned partial references.
Differential word counts are not truth. Local-endpoint scheduler, queue,
readiness and Stop latency effects remain UNMEASURED: promotion stopped at the
no-win falsifier, before production integration.

Retained baseline Stop times (alternation/overlap): 24 s 5.411/11.389 s;
48 s 10.501/18.697 s; full-reference 11.466/10.851 s. Maximum sampled pending
work for the four duration controls: 1/2/2/2, not continuous queue high-water.
WP12's separate candidate is not a matched code/input/load regression control.

Fresh decoder calls: **0/60**. Historical ledger unchanged: 390/500 = 179 baseline
+ 179 standalone + 28 new nonzero local spans + 4 padding requests. Local replay
contains 191 partitions, 56 zero; 154 exact-audio/reason answers reused.

Execution deviations: frontend checks began while the Python suite was finishing;
all prescribed commands/flags were retained. Supplemental raw-surface/padding
re-scoring was offline. No new prototype, live requalification, browser acceptance,
or operator-corpus acceptance. Existing prototype deviations remain: scripted
states instead of interactive TUI; shadow endpoints plus production-decoder replay
instead of a production scheduler change. No production, policy, or test changes;
no push/merge/deploy, services/tunnels started, peer messages, or writes outside
this worktree. Only verification records and the two NOTES appendices are committed.
