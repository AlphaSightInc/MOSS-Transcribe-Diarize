# Fetch body audit (baseline 54fb5573)
A body parse that throws still disturbs/releases the stream. A fetch that throws before returning a Response has no response for the caller to release. Rates are upper bounds excluding request latency; user actions have no fixed hourly rate. All direct fetch and injected fetcher sites in frontend/src inspected; tests excluded.

| Site | Success body | Non-OK body | Throw / parse failure | Requests per hour |
|---|---|---|---|---|
| F1 captureClient postFrame -> fetchRequest | **Unread**; ack unused | Always json, including 400/409/429/5xx | fetch failure has no response; JSON failure disturbed | 14,400 (2 lanes × 2/s) |
| F2 captureClient flushHeartbeat -> fetchRequest | **Unread** | **Unread**; throws by status | fetch failure no response | 7,200 (2/s) |
| F3 captureClient prepareContext descriptor | json | **Unread** on throw | JSON parse failure disturbed | 1 per Start/preparation |
| F4 captureClient createSession | json | json only for 400/409; others **unread** | validation occurs after json | 1 per new meeting |
| F5 stopCaptureSession | json only 202; 200 **unread** | **Unread** | 202 parse failure disturbed | 1 per Stop |
| F6 api/mossPoller fetchJson (snapshot/events) | json | json BEFORE status | parsed/invalid JSON released; timeout abort | <=72,000 during active meeting (2 routes/100ms); <=3,600 idle |
| F7 api/meetings requestJson (list/open/title) | json | json | parse catch after disturbance | history/open/title user actions; refinement open <=720/h per item (5s); file follow <=2,400/h per item (1.5s) |
| F8 api/speakers listVoiceprints | json | json | parse failure released | dialog actions |
| F9 api/speakers changeVoiceprint | json | json | parse catch released | user actions |
| F10 api/speakers nameMeetingSpeaker | json | json | parse catch released | user actions |
| F11 api/speakers reassignMeetingPassages | json | json | parse catch released | user actions |
| F12 lib/summaryRequests postJson | json | failure(response) json | parse failure released | live rolling <=180/h at default 20s wait; manual final summary actions |
| F13 lib/finalSummary fetchRelayModels | json | **Unread** return [] | parse failure released | setup + one per relay summary job |
| F14 lib/finalSummary summaryApi | json | **Unread** status throw | parse failure released | writes/user actions; worker monitor <=1,800/h while generating (2s), stops on first failure; inactive SummaryPane <=720/h (5s), repeats after errors; exported FinalSummary component <=1,800/h (2s), currently unmounted |
| F15 lib/finalSummary queue provider fetch | json | json only relay 502; other errors **unread** | timeout abort; parse failure released | <=2 relay / <=4 external deliveries per job (provider requests NOT exercised here) |
| F16 lib/fileUpload admission POST | **Unread**, if upload follows | json through selected response | network error has no Response | 1 per file |
| F17 lib/fileUpload upload/URL POST | json | json | parse catch released | 1 per file/URL |
| F18 SettingsDialog descriptor effect | json | **Unread** return null | parse failure released | once per dialog open |
| F19 SettingsDialog testProvider | json | json | parse catch released | explicit Test click (NOT exercised here) |
| F20 SettingsDialog testBrowserProvider | json | **Unread** 401/403; other errors detailOf json | abort deadline; parse failure released | explicit Test click (NOT exercised here) |

Recurring leaks: **F1 + F2 = 6/s = 21,600/h**, 16,384/6 = **45m31s**. F6, the faster live poller, always consumes bodies on all HTTP outcomes: correct. F7 also consumes bodies: correct. F14 can leave one error body unread but aborts its monitor at the first error; it cannot accumulate 1,800 leaks/hour. **F14 inactive SummaryPane is another recurring error-path leak**: 0.2/s, 720 unread bodies/h if every HTTP reply is non-OK, fresh-page budget at 16,384/0.2 = **22h45m20s**. Its error catch retries indefinitely, even with the pane hidden. Healthy responses are consumed. The exported FinalSummary component would leak 0.5/s on repeated HTTP errors (**9h6m8s**), but has no production mount in frontend/src; reported as dormant source, not a reachable current-product rate. These rates assume empty initial budget and continuously fast HTTP error replies; transport failures without a Response do not leak bodies. A user could accumulate low-rate unread responses by repeating actions; those are reported, not bundled into unrelated production edits.

C1 routes all CaptureClient raw fetches plus standalone Stop through one response-draining helper. C3 only changes frame/heartbeat POST response cache policy; other API no-store behavior remains.
