# Gemini live runtime stress and fault result

**Result: all 19 named stress scenarios passed their stated transport and fault expectations.** This table binds each expectation to the product commit and immutable run receipt. A stress PASS means the named session accepted its audio, reached the expected terminal state, retained its recording, and exposed runtime counters; fault rows also require an observed proxy injection. Speech quality is scored separately on the frozen H1 reference set. An empty or incomplete reference cannot turn a transport result into a diarization result.

All receipts below are under `/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/`. `c58595da`, `a3fbf081`, and `56513e30` are clean earlier runtime archives. The final runtime code SHA is `0b9deed5`; the D6 scorecard's H1 and E1 quality receipts use this final SHA. The lead's Stop bound is `60 s + 5% × accepted audio duration`. Other scenario receipts stand on their listed SHA.

| Scenario | Expectation | Verdict | Runtime SHA | Receipt |
| --- | --- | --- | --- | --- |
| long60, 43m06 | Bounded queue; 2,586 s tape; terminal within 189.3 s; resource and lag trace | PASS | `56513e30` | `runtime-s12-long60-full1/summary.json` |
| concurrent2 + third create | Two 300 s sessions finish; third receives 409 `live_capacity_full` | PASS | `0b9deed5` | `runtime-final-concurrent2-full1/summary.json` |
| stop-early | Accepted prefix retained; Stop reaches terminal | PASS | `0b9deed5` | `runtime-final-stop-early-full1/summary.json` |
| abort-mid | 150 s accepted; abort terminal, tape retained | PASS | `c58595da` | `runtime-c585-abort-mid-full1/summary.json` |
| silence10 | 600 s empty transcript and exact tape; zero Gemini Live/batch calls and cost | PASS | `0b9deed5` | `runtime-final-silence10-full1/summary.json` |
| music5 | 300 s tone retained; terminal state; text behavior reported | PASS | `c58595da` | `runtime-c585-music5-full1/summary.json` |
| overlap | Both simultaneous 300 s streams finish with bounded queue | PASS | `c58595da` | `runtime-c585-overlap-full1/summary.json` |
| manyspk K6 | 604 s tape; terminal within 90.2 s; counters exposed | PASS | `56513e30` | `runtime-s12-manyspk-full1/summary.json` |
| REST 429 burst ×5 | Five injected failures; eventual terminal and tape | PASS | `c58595da` | `runtime-c585-faults-429-burst5-1/summary.json` |
| REST 503 burst ×5 | Five injected failures; counted retries; recovery and tape | PASS | `0b9deed5` | `runtime-final-faults-http-503-full1/summary.json` |
| REST 30 s stall | Injected delay; eventual terminal and tape | PASS | `c58595da` | `runtime-c585-faults-stall-full1/summary.json` |
| REST connection reset burst ×5 | Injected resets; eventual terminal and tape | PASS | `c58595da` | `runtime-c585-faults-connection-reset-full1/summary.json` |
| REST malformed JSON burst ×5 | Five invalid bodies; bounded failure and recovery | PASS | `a3fbf081` | `runtime-a3-faults-malformed-json-full1/summary.json` |
| Google down 60 s mid-meeting | Real proxy outage then recovery; live session and tape survive | PASS | `a3fbf081` | `runtime-a3-faults-google-down-mid-full1/summary.json` |
| Google down at Stop | Finalization fails visibly, never hangs; live rows and tape retained | PASS | `a3fbf081` | `runtime-a3-faults-google-down-stop-full1/summary.json` |
| WS close 1011 | Injected close; rolling rows and tape survive | PASS | `0b9deed5` | `runtime-final-faults-ws-close-1011-full1/summary.json` |
| WS GoAway | Injected GoAway; preview recovers, session finishes | PASS | `a3fbf081` | `runtime-a3-faults-ws-goaway-full1/summary.json` |
| WS stall 30 s | Injected stall; session finishes, rows from windows survive | PASS | `a3fbf081` | `runtime-a3-faults-ws-stall-full1/summary.json` |
| WS refused connect | Refusal visible; reconnect/degrade; final tape retained | PASS | `a3fbf081` | `runtime-a3-faults-ws-refused-connect-full1/summary.json` |

The following rates are **words clamped or dropped divided by recorded Gemini calls** in the corresponding table receipt. A zero-call run has no per-call rate; `UNMEASURED` is intentional. Dollar amounts are recorded engine estimates, not billed invoices. Earlier `c58595da` SDK retry counters undercount physical attempts; its fault recovery receipts remain valid for their stated lifecycle expectation.

| Scenario | Calls | Clamped/call | Dropped/call | Engine cost, USD |
| --- | ---: | ---: | ---: | ---: |
| long60 | 157 | 0.031847 | 0 | 1.633487 |
| concurrent2 | 44 | 0.022727 | 0 | 0.341417 |
| stop-early | 3 | 0 | 0 | 0.001087 |
| abort-mid | 15 | 0 | 0 | 0.032028 |
| silence10 | 0 | UNMEASURED | UNMEASURED | 0 |
| music5 | 32 | 0 | 0 | 0.083729 |
| overlap | 64 | 0.140625 | 0.203125 | 0.167457 |
| manyspk K6 | 29 | 0.034483 | 0 | 0.259121 |
| REST 429 burst ×5 | 33 | 0.030303 | 0 | 0.083729 |
| REST 503 burst ×5 | 26 | 0 | 0 | 0.169957 |
| REST 30 s stall | 30 | 0.033333 | 0 | 0.081225 |
| REST connection reset burst ×5 | 32 | 0.031250 | 0 | 0.077719 |
| REST malformed JSON burst ×5 | 22 | 0 | 0 | 0.159449 |
| Google down 60 s mid-meeting | 25 | 0 | 0 | 0.118032 |
| Google down at Stop | 21 | 0 | 0 | 0.146538 |
| WS close 1011 | 23 | 0 | 0 | 0.170709 |
| WS GoAway | 23 | 0 | 0 | 0.170709 |
| WS stall 30 s | 22 | 0 | 0 | 0.170709 |
| WS refused connect | 25 | 0 | 0 | 0.144790 |

## Evidence limits and defects

- **F1.** The old `c58595da` long60 and silence10 runner verdicts used a provisional 35 s Stop cutoff and stopped observing before product finalization. The lead replaced that bound with `60 s + 5% × duration`. They are not current failures. The 56513e30 long60 rerun is the definitive stress receipt for that SHA.
- **F2.** `56513e30` fixed hidden REST retries: the five proxied 503 attempts appear as five runtime errors and four retries. Its silence10 skipped every rolling/final batch call and finalized in 2.621 s, but sent two eager system Live preview calls costing $0.050583. On final SHA `0b9deed5`, full silence10 retained the exact 600 s MP3, had no text rows, finalized in 0.472 s, and made zero Gemini calls at zero cost. Per-call anomaly rates are `UNMEASURED` because the denominator is zero.
- **F3.** The original `a3fbf081` WS close1011 summary has a harness-only FAIL: it demanded a literal `rolling` counter key, while the product correctly emitted `system_rolling`; its adjudicated receipt changes only that check. The final-SHA rerun passed directly: one injected close, one counted error/retry, 20 rolling calls, exact 300 s MP3, final in 41.238 s after Stop, and no timing anomalies across 23 calls.
- **F4.** `music5` produced a lone `2` token on a pure tone. Audio retention and terminal behavior passed; text on non-speech is a documented product limitation.
- **F5.** `c58595da` 429/recovery and other early receipts prove recovery and tape retention on that commit; its SDK retries were hidden from the runtime counters. Count reconciliation is evidenced separately by the 56513e30 503 receipt and must be rechecked on the final SHA.
- **F6.** Complete `56513e30` long60 stress passed: Stop-to-final 122.094 s versus 189.3 s bound; exact 2,586 s retained MP3; queue max 1/16. Across 157 calls, four natural Live GoAway recovered, five words clamped (0.031847/call), none dropped; engine cost $1.633487. Rolling lag p50 23 s/max 48 s; UI label delay p50 33.315 s/p90 63.718 s. Snapshot poll p50 8.01 ms/p90 151.866 ms; maximum snapshot 136,176 bytes, RSS 2,835,104 KiB, CPU 116.6%, descriptors 238. These are 56513e30 measurements; L-1 changes on final code SHA require their own latency evidence.
- **F7.** The final-SHA REST 503 burst injected five failures and recorded exactly five `503` errors and four retries across 26 runtime calls, with no timing anomalies. It retained the exact 300 s tape and finalized in 39.695 s after Stop. This independently confirms the S-1 counter fix on the final code SHA.
- **F8.** Final-SHA concurrent2 retained two exact 300 s MP3s and finalized in 38.182/32.179 s after Stop; the third create returned HTTP 409 `live_capacity_full`. One word was clamped across 44 calls (0.022727/call), none dropped; total engine cost $0.341417.
- **F9.** Final-SHA stop-early retained the exact 5 s accepted prefix and finalized in 6.979 s; three calls, zero timing anomalies, cost $0.001087.

The test's `long60` audio is the registered 2,586 s complete-reference Lex concatenation with five true speakers. This report checks lifecycle and resources, not its diarization score. Sparse acquired 5 m and 30 m references are diagnostic only. The final D6 scorecard uses accept6 H1 #3 truth and names its own qualification SHA.

## Qualification and budget

The source-tagged [final D6 scorecard](/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/scorecard-stress-final-1/scorecard.md) includes all 19 stress receipts and the **final code SHA `0b9deed5`** H1 12-case-pass and E1 quality receipts from pane 6.2. Its four hard bars pass: Stop-settled diarization error rate 0.099369 (`<0.145`), final diarization error rate 0.104860 (`<=0.110`), four labels at Stop (`<=5`), and zero dropped reference seconds in 1,216 checked seconds. H1 engine diagnostics: 108 calls, two clamped words (0.018519/call), zero dropped words, $0.465024 recorded cost. The E1 word-visible p50 is 0 s and label p50 is 18.257 s; both pass their soft bars.

The scorecard's meeting-hour cost cell is **$2.273996 per audio hour from the complete `56513e30` long60 stress receipt**, with its SHA identified here. The final-SHA H1/E1 quality verdict and that older-SHA cost/long60 stress verdict are separate measurements. Pane 6.2's final-SHA long60 qualification is a separate run; this stress table does not claim its quality or latency outcome. The P64 campaign's observed provider-cost accounting is about **$5.732107**, including earlier exploratory receipts and subsequent terminal-cost corrections, under its $6 cap; these are engine estimates, not invoices.
