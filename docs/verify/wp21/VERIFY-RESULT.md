# WP21 fresh-context verification result

Fresh-context rerun complete; gate-status comparison PASS (35/35 unchanged), qualification FAIL. Expected command exit 1. No retry, --long, push, merge, rebase, deployment, or shared-service change.

Branch `mvpfix/wp21-qualify-bundle`; entry `852155b511e8fa0bf805dd8d2ca7a2df0444a961`; tested clean commit `799169736bca4e25768610facffed44a4bb30eef`. Product baseline remains `c2e458676cf27b9e4da69bea20a1612152f1516a`, predating WP20 merge `5094206d`. This does not measure the final integrated candidate.

F1 — Prototype verdict retained: five interfaces inspected; partial composition supported, complete qualification unsupported with unchanged bench interfaces. No new algorithm or product policy introduced. The runner-only edit implements the explicit instruction to proceed under sibling load; own isolation, request cap, and contention recording remain unchanged.

F2 — Exact command (run once from the assigned worktree):
```sh
bash scripts/mvpfix-qualify.sh --compare evidence/qualify/5ae9566f017e-20260918T064038829598Z/summary.json > .wp21runtime/fresh-run.console 2>&1
```

Dry bundle: `evidence/qualify/5ae9566f017e-20260918T064038829598Z`. Fresh bundle: `evidence/qualify/799169736bca-20260918T065934740190Z`. Machine comparison: `evidence/mvpfix/wp21/fresh-summary.json`.

F3 — Gate table. P=PASS, F=FAIL, S=SKIP, U=UNRUNNABLE. Workspace rows are children of workspace; do not sum them twice. Durations of 0 are recorded bookkeeping/unexecuted gates, not measured execution costs.

| Gate | Dry → fresh status | Dry denominator | Fresh denominator | Dry seconds | Fresh seconds |
|---|---|---|---|---:|---:|
| tree_clean | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.000 | 0.000 |
| python_import | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.000 | 0.000 |
| asset_parity | PASS → PASS | 17/17 equal; 0 different | 17/17 equal; 0 different | 0.782 | 0.976 |
| pytest | PASS → PASS | 1877/1877 pass; 1879 collected; 2 skip; 37 subtests | 1877/1877 pass; 1879 collected; 2 skip; 37 subtests | 155.946 | 152.756 |
| frontend | PASS → PASS | 244/244 pass; 244 collected; 0 skip | 244/244 pass; 244 collected; 0 skip | 3.185 | 3.533 |
| bundle_helpers | PASS → PASS | 6/6 pass; 6 collected; 0 skip | 7/7 pass; 7 collected; 0 skip | 1.766 | 1.794 |
| typecheck | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 1.415 | 1.351 |
| verify_layout | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.080 | 0.048 |
| stack | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 5.546 | 6.555 |
| workspace | FAIL → FAIL | 10P/3F/1S/0U of 14; 13 executed | 10P/3F/1S/0U of 14; 13 executed | 295.080 | 296.107 |
| workspace_row_1 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.106 | 0.108 |
| workspace_row_2 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 3.260 | 3.264 |
| workspace_row_3 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 2.164 | 2.168 |
| workspace_row_4 | FAIL → FAIL | 0P/1F/0S/0U of 1; 1 executed | 0P/1F/0S/0U of 1; 1 executed | 132.152 | 132.060 |
| workspace_row_5 | FAIL → FAIL | 0P/1F/0S/0U of 1; 1 executed | 0P/1F/0S/0U of 1; 1 executed | 0.073 | 0.076 |
| workspace_row_6 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.463 | 0.423 |
| workspace_row_7 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.167 | 0.171 |
| workspace_row_8 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 38.504 | 38.488 |
| workspace_row_9 | SKIP → SKIP | 0P/0F/1S/0U of 1; 0 executed | 0P/0F/1S/0U of 1; 0 executed | 0.003 | 0.003 |
| workspace_row_10 | FAIL → FAIL | 0P/1F/0S/0U of 1; 1 executed | 0P/1F/0S/0U of 1; 1 executed | 5.436 | 5.475 |
| workspace_row_11 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.081 | 0.091 |
| workspace_row_12 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.180 | 0.179 |
| workspace_row_13 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 68.207 | 68.202 |
| workspace_row_14 | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 42.919 | 43.642 |
| demo_lanes | FAIL → FAIL | 0P/2F/0S/0U of 2; 2 executed | 0P/2F/0S/0U of 2; 2 executed | 104.798 | 104.659 |
| lifecycle | PASS → PASS | 7P/0F/0S/0U of 7; 7 executed | 7P/0F/0S/0U of 7; 7 executed | 12.239 | 12.093 |
| reshare | PASS → PASS | 6P/0F/0S/0U of 6; 6 executed | 6P/0F/0S/0U of 6; 6 executed | 38.196 | 37.854 |
| identity_stress | FAIL → FAIL | 1P/2F/0S/0U of 3; 3 executed | 1P/2F/0S/0U of 3; 3 executed | 82.988 | 80.415 |
| level_ladder | FAIL → FAIL | 0P/0F/0S/6U of 6; 0 executed | 0P/0F/0S/6U of 6; 0 executed | 3.103 | 3.152 |
| browser_stress_all | UNRUNNABLE → UNRUNNABLE | 0P/0F/0S/16U of 16; 0 executed | 0P/0F/0S/16U of 16; 0 executed | 0.000 | 0.000 |
| file_6min | UNRUNNABLE → UNRUNNABLE | 0P/0F/0S/1U of 1; 0 executed | 0P/0F/0S/1U of 1; 0 executed | 0.000 | 0.000 |
| file_failures | UNRUNNABLE → UNRUNNABLE | 0P/0F/0S/5U of 5; 0 executed | 0P/0F/0S/5U of 5; 0 executed | 0.000 | 0.000 |
| file_30min | SKIP → SKIP | 0P/0F/3S/0U of 3; 0 executed | 0P/0F/3S/0U of 3; 0 executed | 0.000 | 0.000 |
| capacity_4x600 | SKIP → SKIP | 0P/0F/4S/0U of 4; 0 executed | 0P/0F/4S/0U of 4; 0 executed | 0.000 | 0.000 |
| teardown | PASS → PASS | 1P/0F/0S/0U of 1; 1 executed | 1P/0F/0S/0U of 1; 1 executed | 0.000 | 0.000 |

F4 — Deltas: zero gate-status changes, added gates, or missing gates. Sole denominator change: helpers 6/6 → 7/7 from the already-added missing-reference-voice negative control. Dry SHA was `5ae9566f017e5b888d3676e9a3ccb0a007d5917d`; its identity observations were previously re-scored with all three statuses unchanged. Fresh code also records budget-at-gate metadata. This session removed the busy-decoder refusal in `tools/qualify/run.py` and corrected `tools/qualify/README.md`, committing before dispatch to preserve clean identity. This supersedes VERIFY.md’s older busy-decoder instruction. Initial load was zero, so that removed branch would not have fired in this run. Matching statuses are not strict same-code determinism.

F5 — Runtime dry 705.520 s → fresh 701.799 s (−3.721 s); per-gate durations above. Both used 300 requests, peak 1 (limit 2), zero proxy rejections, zero active at teardown. The stack enforces its own 300-call limit before further forwarding; zero proxy rejections does not mean budget remained. Fresh requests at aggregate gate completion: workspace 180, demo lanes 239, lifecycle 254, reshare 269, identity 300, ladder 300. Workspace row request metadata is sampled when rows are recorded after aggregate completion, not at individual row completion.

F6 — Contention: both 267 samples, zero errors; shared running maximum 1 → 2, waiting maximum 0 → 0. Fresh had four samples where shared running exceeded own active count (dry zero). Samples are non-atomic observations, not exact sibling attribution. No pause for sibling load. Timing causes were not isolated; the duration changes do not establish a performance improvement or contention penalty.

F7 — Unchanged observed failures: workspace row 4 and standalone demo lanes fail the word-error checks (alternating microphone pre-terminal 0.207547 > 0.166655; overlap system pre-terminal 0.226415 > 0.166655 and final/reopened 0.122642 > 0.095074). Row 5 second rename did not update row/legend, although history/export updated. Row 10 recognition 4.016300 s exceeds 4.000 s (dry 4.011200 s). Row 9 skips because configured relay models=0. No unrelated product repair attempted.

F8 — Budget limits: identity single passed; gap and alternating interrupted; ladder emitted zero of six cases. The ledger labels the identity aggregate FAIL (1/3) and ladder FAIL (0 executed, 6 UNRUNNABLE); these are incomplete measurements, not acoustic rejection. Gap retained two scored segments in dry run and zero fresh; the same budget is exhausted earlier within the sequence. The cause of the consumption shift was not isolated. No additional requests or retry were authorized or made.

F9 — Unsupported: browser_stress_all 16/16 UNRUNNABLE because case 14 restart fixes WP5 paths and decoder tunnel 18105; file_6min 1/1 UNRUNNABLE because WP16 fixes app 17876, metrics 18116 and output paths; file_failures 5/5 UNRUNNABLE for the same missing isolation arguments. File_30min 3 and capacity_4x600 4 sessions SKIP by default; --long was not supplied. No fabricated passes or relaxed thresholds.

F10 — Containment: product/frontend/tests/prototypes diff against baseline empty (exit 0); verification layout and whitespace checks exit 0; lsof on 17867/18121/18122 returned no listeners (exit 1). Python import resolves inside this checkout. Asset bytes restored 17/17, owned process groups remaining zero. WP7 inherited output restored by runner; status shows only fresh bundle before report writes. Retained bundle contains 39 JSON/JSONL/projection-log/Markdown files; checked content fields empty. Content-bearing raw output/audio/certificates remain ignored runtime scratch and are not committed. Existing SQLite version-pin bypass means local recipe evidence is not deployed runtime parity.

F11 — Changed in this session: `tools/qualify/{run.py,README.md}`, this result, `evidence/mvpfix/wp21/fresh-summary.json`, and the fresh bundle directory. Helper preflight 7/7 passed in 1.66 s; full bundle gate counts above are the authorized rerun. Final report-only commit does not change tested executable code.

Lead command from a clean checkout at the final integrated SHA (ports free, prepared dependencies):
```sh
bash scripts/mvpfix-qualify.sh --compare evidence/qualify/799169736bca-20260918T065934740190Z/summary.json
```
This compares statuses to the fresh WP21 baseline; integrated changes may legitimately change them and require explanation. Current command remains bounded at 300 requests, omits --long, and cannot claim complete qualification while required benches are unsupported or budget-limited.
