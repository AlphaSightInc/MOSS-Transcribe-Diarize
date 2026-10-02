# P74-L1 contract (throwaway measurement bench, retained as regression seam)
1. Structural question: can one response-release choke point stop page-wide Chrome request exhaustion, including stale bundles?
2. Minimum primitives: request (real serialization/delivery), response (status/body ownership), server admission (real frame/heartbeat routes), page (Chrome loader lifetime). Removing any hides either the leak or an accounting change.
3. Invariants: every obtained capture response is released; original status/error payload remains available; sequence/replay/admission/terminal behavior stays unchanged; old bundles remain usable against the proposed server.
4. Unknowns: real-path throughput, native renderer memory, empty-response/no-store interaction, stale bundle behavior are unmeasured until recorded. Tiny synthetic frames test request lifetime, not hours of physical capture or provider throughput.
5. Falsifier: baseline does not die near 16,384; any candidate networking failure within 100,000; increasing retained renderer memory; altered outcome table.
6. Tool decision: Vite bundles the actual module into a test-only page; Playwright runs installed real Chrome; actual Phase2 app uses ScriptedGeminiEngine. Accelerated synthetic inputs bypass physical audio timing only. CDP/OS measurements separate JavaScript heap from renderer resident memory. Unit guards attack unread bodies across all response outcomes; existing suites attack accounting/route compatibility.

Hypothesis: C1 drains bytes before returning a reconstructed Response, preserving JSON for failures without cloning a live network stream. C2 empty success replies may release stale clients; C3 excludes only frame/heartbeat POST responses from no-store while retaining bodies/statuses. Each measured alone before production edits. C4 combines C1 with the smallest stale-client fix that passes.

## Measurement custody
Initial Playwright observer runs retain Network-domain bookkeeping: C1 100,002/100,002, heap 1.28→1.31 MB, renderer RSS sum 464.5→860.8 MB. This is NOT the native-memory gate. All receipts retained. A prototype transform initially ran after TypeScript conversion and matched nothing: `C1-transform-missed` is invalid candidate evidence, retained. The corrected transform runs before conversion and its emitted bundle was checked for the added arrayBuffer call.

For native memory, Playwright acquires/navigates the real Chrome page, then disconnects; Chrome remains externally owned. Raw Chrome DevTools Runtime/Performance calls continue the identical compiled loop with Network observation disabled. Baseline still dies at capture request ordinal 16,382 (16,381 successful capture replies), 19.24s, GET/POST both dead. C1 completes 100,002 in 102.73s with heap ~1.26MB; native renderer memory roughly stable after startup. Compare warm windows, not total initial RSS while Chrome's transient startup renderers exit. Instrumented and native-memory runs remain separately labeled.

One command (each invocation stops its Chrome and server):
`../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/L1/run.py --mode baseline --total 21000 --raw --label baseline-check`
Modes C1, C2, C3, C4 default to 100,002 requests. `product` uses checked-out product unchanged. Run baseline at 54fb5573; run product at candidate commit. For historical mode comparisons the runner will pin the capture source through git show rather than borrow candidate code.

## Verdict and numbers
**Recommend C1+C3 for the capture leak**, local candidate only. C1 releases every capture network body, preserving status/error JSON; C3 preserves acknowledgement bodies and protects old cached bundles. C2 passes Chrome but breaks ack-reading callers and leaves old heartbeat error bodies no-store. The header exception includes error replies.

| Arm | Complete loop requests | Failed requests | Seconds | Warm renderer RSS MB (30k -> end) | JS heap MB (30k -> end) |
|---|---:|---:|---:|---:|---:|
| Baseline native, old bundle | 16,380 + 1 partial success | 3 | 19.24 | 136.47 at start -> 691.34 | 1.084 at start -> 1.629 |
| C1 only, old server policy | 100,002 | 0 | 102.73 | 186.02 -> 194.83 | 1.260 -> 1.265 |
| C2 only, old bundle | 100,002 | 0 | 126.41 | 176.92 -> 187.28 | 1.263 -> 1.262 |
| C3 only, old bundle | 100,002 | 0 | 121.46 | 181.88 -> 192.78 | 1.258 -> 1.263 |
| C4 prototype, C1+C3 | 100,002 | 0 | 118.62 | 185.95 -> 194.77 | 1.352 -> 1.357 |
| Candidate PRODUCT code | 100,002 | 0 | 108.88 | 186.14 -> 193.70 | 1.359 -> 1.364 |

Every successful arm also delivered one startup heartbeat: 100,003 capture HTTP replies, all 200 except C2 all 204. 66,668 frame replies / 33,335 heartbeats. Candidate actual runtime accepted 66,668 mixed samples; both lanes advanced to sequence 33,334. Raw baseline first failing capture request index 16,382; 16,381 successful capture replies preceded it. The original fully Playwright-observed baseline had 16,382 successful replies and died in 21.18s. Small count differences reflect other page requests and partial concurrent batches, all retained.

Renderer memory is approximately flat after warmup: single-digit/low-double-digit MB drift, not literally zero. C1/C2/C3 use the largest warm renderer as the capture-tab approximation; C4/product identify its exact PID by one startup timestamp trace (tracing stopped before workload). Chrome startup renderers exit during the first ~30s; raw total initial renderer RSS is therefore not a meaningful before/after comparator. Full initial/warm/final samples are printed and preserved. No memory result from Network-observed runs is substituted for native runs.

Gates: frontend 578 pass, typecheck/build green; backend 2,918 pass, 9 skip, 2 expected failures, 37 subtests, 432.80s. Unit baseline: 19 new guards fail; 64 original capture tests and 2 empty-body controls pass. All 85 capture tests pass on candidate, original outcome assertions untouched. Backend cache guard fails baseline on no-store and passes candidate, including error replies and preserved ack/helper JSON. Thus G1-G4 pass for the stated capture-request seam; physical-duration and provider qualification remain unmeasured.

UI receipt `baseline-ui.json`: actual App/ControlPanel with its last active state and real poller on the exhausted page shows `Recording 45:32`, `Reconnecting — keep this tab open.` (observer phase viewing). The loop itself shows first TypeError and stalled sequence counts. The UI cannot learn of server lease expiry while all networking is dead. Propose copy only: `This page lost its connection — retrying. If it stays disconnected, reload and start a new recording; check History for the recorded part.` No detector/timeout added.

Residual from audit: inactive SummaryPane repeatedly ignores non-OK summaryApi bodies at 0.2/s; 22h45m20s to a fresh 16,384 budget. Healthy replies consumed. This is separately reported, not covered by capture G1 or fixed here. The exported but unmounted FinalSummary component has a similar 0.5/s error path (9h6m8s if mounted). C1+C3 closes the measured 45-minute failure, not every frontend error-body ownership issue. Header risk: no-cache requires revalidation but permits storage; scope only frame/heartbeat POSTs, no explicit POST freshness, all other APIs remain no-store. A page already exhausted needs reload.

Regression commands (unique evidence directory by default; raw native-memory mode is default):
- Baseline, pinned old module and restored old server header: `../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/L1/run.py --mode baseline --total 21000 --ui`
- Candidate: `../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/L1/run.py --mode product`
- Each isolated prototype: same command, `--mode C1` / `C2` / `C3` / `C4`.
The command exits nonzero if baseline fails to reproduce near the limit, if it exceeds 180s, if GET/POST still work, or if any candidate does not reach its target with zero failures and expected statuses. Backend binds 127.0.0.1:18976; Chrome debugger 127.0.0.1:18978. Choose another allowed --port for server if occupied; do not disturb other owners. Fake 2-sample frames remove audio-time/storage scaling only, leaving real serialization, queues, heartbeats, authorization, route admission and publication intact. ~$0, no provider path/keys; unsupported physical capture and provider behavior are unmeasured.

The prototype is absorbed as a retained regression bench. It remains test-only; no shipped test route, feature flag, provider, network interceptor, or audio timing override is added to production.
