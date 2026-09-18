WP25 · `mvpfix/wp25-qualify-run` · final SHA: see pane report · qualification **FAIL**; fresh verification **FAIL**.
Candidate `625dbaa97b55`; long harness `ab4744511b41`; fresh measured `1dd59f66e4a9` (same code, different SHA). F=failed, S=skipped, U=unrunnable; Python includes 37 subtests.

| Gate | Long: pass/denominator; seconds | Fresh: pass/denominator; seconds |
|---|---|---|
| tree_clean | PASS 1/1; 0.000 | FAIL 0/1 F1; 0.000 |
| python_import | PASS 1/1; 0.000 | PASS 1/1; 0.000 |
| asset_parity | PASS 17/17; 0.789 | PASS 17/17; 0.817 |
| pytest | PASS 1910/1912 S2; 160.574 | PASS 1910/1912 S2; 154.926 |
| frontend | PASS 249/249; 3.187 | PASS 249/249; 3.542 |
| bundle_helpers | PASS 9/9; 1.280 | PASS 9/9; 1.740 |
| typecheck | PASS 1/1; 1.253 | PASS 1/1; 1.381 |
| verify_layout | PASS 1/1; 0.048 | PASS 1/1; 0.044 |
| stack | PASS 1/1; 5.481 | PASS 1/1; 5.496 |
| workspace | FAIL 12/14 F1 S1; 255.414 | FAIL 11/14 F2 S1; 255.908 |
| workspace_row_1 | PASS 1/1; 0.178 | PASS 1/1; 0.110 |
| workspace_row_2 | PASS 1/1; 3.242 | PASS 1/1; 3.248 |
| workspace_row_3 | PASS 1/1; 2.169 | PASS 1/1; 2.170 |
| workspace_row_4 | FAIL 0/1 F1; 108.518 | FAIL 0/1 F1; 108.554 |
| workspace_row_5 | PASS 1/1; 0.061 | FAIL 0/1 F1; 0.060 |
| workspace_row_6 | PASS 1/1; 0.408 | PASS 1/1; 0.404 |
| workspace_row_7 | PASS 1/1; 0.163 | PASS 1/1; 0.165 |
| workspace_row_8 | PASS 1/1; 38.826 | PASS 1/1; 38.529 |
| workspace_row_9 | SKIP 0/1 S1; 0.003 | SKIP 0/1 S1; 0.003 |
| workspace_row_10 | PASS 1/1; 5.110 | PASS 1/1; 5.344 |
| workspace_row_11 | PASS 1/1; 0.087 | PASS 1/1; 0.081 |
| workspace_row_12 | PASS 1/1; 0.194 | PASS 1/1; 0.196 |
| workspace_row_13 | PASS 1/1; 57.092 | PASS 1/1; 57.221 |
| workspace_row_14 | PASS 1/1; 37.795 | PASS 1/1; 38.071 |
| demo_lanes | FAIL 0/2 F2; 87.286 | FAIL 0/2 F2; 87.323 |
| lifecycle | PASS 7/7; 11.253 | PASS 7/7; 11.225 |
| reshare | PASS 6/6; 34.958 | PASS 6/6; 35.008 |
| identity_stress | PASS 3/3; 194.452 | PASS 3/3; 194.906 |
| level_ladder | PASS 6/6; 170.859 | PASS 6/6; 161.787 |
| browser_stress_all | FAIL 13/16 F1 U2; 694.833 | FAIL 13/16 F1 U2; 757.265 |
| file_6min | PASS 1/1; 80.936 | PASS 1/1; 78.524 |
| file_failures | PASS 5/5; 44.093 | PASS 5/5; 43.430 |
| file_30min | PASS 3/3; 1223.493 | SKIP 0/3 S3; 0.000 |
| capacity_4x600 | FAIL 0/4 F4; 699.552 | SKIP 0/4 S4; 0.000 |
| teardown | PASS 1/1; 0.000 | PASS 1/1; 0.000 |

- **F1:** Status deltas: `tree_clean` PASS→FAIL (38 retained interrupted-evidence files); row5 PASS→FAIL (second rename visible-label check false; HTTP 2/2=200, history 2/2 correct, export correct). Cause unmeasured. All other comparable gate statuses match; long-only gates intentionally SKIP.
- **F2:** WER bars immediate ≤0.166655; final/reopen ≤0.095074; reference system106/mic53; gain0.03. Fresh workspace alternation immediate .141509/.207547, final .084906/.094340; demo alternation .150943/.207547→.084906/.094340. Both overlap invocations .216981/.113208→.122642/.094340; reopen=final.
- **F2:** Long differs only workspace alternation: .150943/.207547→.103774/.094340. Mic alternation immediate and system overlap immediate/final fail; long workspace alternation system final also failed. First text long/fresh 3.328802/3.330545s≤4s; attribution/duplication/unresolved=0.
- **F3:** Browser9 predicate accepts1/3: truthful “URL media could not be acquired.” and “The URL returned a web page instead of direct media.” miss old keywords; 404 passes. Cases3/15 UNRUNNABLE: native visibility never hidden. Row9 SKIP: configured relay models0; no provider dispatch.
- **F4:** Long capacity stays FAIL4/4: each accepted/accounted9,600,000 samples,2400 lane frames; campaign clock >90s from before Stop POST (30s caller deadline), then abort. Stop→final sessions1/2/3/4: all unmeasured, no final by >90s; exact timeout timestamps absent. Terminal starts0/4; terminal requests0 inferred from event-before-dispatch contract.
- **F4:** Serial canonical/rolling drain—not terminal decoding—remained pending; admitted/completed rolling30/29,31/30,5/4,22/21.64 post-Stop calls;1107 capacity total,peak1. Terminal design: per-session threads/concurrent lanes,proxy≤2; never reached. Mic all-zero, skipped by canonical/rolling; terminal zero-skip unexercised. Final WER/lag/complete pre-stop real-time factor unmeasured.
- **F5:** Long1879/2000 calls,3724.259s; fresh724/900,1807.553s; peaks2, rejects0, teardown active0. Contention long1753/1753 valid,shared>own68,max running/waiting2/1; fresh812/812 valid,excess1,max2/0;errors0. Non-atomic excess ≠ proven sibling attribution. No load pause; all7 owned ports closed.
- **F6:** Ladder6/6 final,all4 overlaps37/37 system+32/32 mic; alone37/37+0/32 and0/37+32/32,matching long/lead; vocabulary≠WER. File fresh76.398788s,WER.106878307 (101 errors/945 reference;998 observed),3 speakers,exports5/5; typed failures5/5.
- **P1:** Prototype isolation supported:4/4 dependencies,2/2 real inputs,HTTP200/200/429; absorbed. Changes only `docs/verify/wp25/VERIFY-RESULT.md`, `evidence/mvpfix/wp25/fresh/**`, this report. Budget400 attempt interrupted at22.929s/0 calls on user raise to900; retained, restart dirty; no code/predicate changes or live retry.
- **A1:** Lead command: `cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp25-qualify-run && bash scripts/mvpfix-qualify.sh --long --budget 2000`. Local measurement only; no deployment/attended acceptance.
