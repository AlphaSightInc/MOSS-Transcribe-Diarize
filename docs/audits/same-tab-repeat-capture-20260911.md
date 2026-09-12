# Same-tab repeat capture — 2026-09-11

**Root cause confirmed: Chromium moved native focus to the shared tab. On the next Share audio request, macOS capture rejected the capture page as backgrounded: `CAPTURE_FROM_BACKGROUND_PAGE_ON_MAC`, surfaced as `InvalidStateError: Invalid state`.** The fix keeps focus on the capturing application using a fresh `CaptureController` for each chooser. AudioContext teardown, tracks and server sessions were not reused incorrectly.

## F1 — exact reproduction and origin

Baseline `4d6d487e`, own HTTPS port 17863, separate database, existing decoder tunnel, relay configured, draft lane 1.0 s. Real Chromium, genuine corpus audio as microphone input and a separate real browser tab as system-audio source. No host operations or access to the operator's 17861 database.

Sequence: Start, capture eight seconds, Stop, wait for meeting `completed` / finalization `final` and UI `terminal`, export, Reset capture, enable microphone, Share audio again. Same Page and JavaScript document throughout; no Playwright foregrounding between cycles. The second chooser failed in three baseline runs. The native diagnostic is retained in `evidence/same-tab-repeat-capture-20260911/native-rejection.txt`.

The JS trace establishes the boundary:

- Old AudioContext successfully closed; a different context was created and running on the second attempt.
- Second microphone acquisition and stream attachment succeeded with a new live track.
- Native `getDisplayMedia()` rejected **before** a shared stream existed, before shared-stream attachment, and before a second server session was admitted.
- Both `document.hasFocus()` and transient user activation were true at the failing call. They did not describe the native macOS foreground state accurately enough to diagnose it.

Chromium's native log explicitly records `HandleAccessRequestResponse(... result=CAPTURE_FROM_BACKGROUND_PAGE_ON_MAC)` and `FinalizeRequestFailed` for the second display request. This resolves the otherwise ambiguous generic error. Chromium also documents the [mapping of that native result to InvalidStateError](https://chromium.googlesource.com/chromium/src/third_party/+/afca670f9b55082431c4a1506673b55606498dc9).

## F2 — competing hypotheses and measured prototypes

Question: is the next acquisition using stale resources, or is the browser rejecting a correctly recreated capture before admission? Minimum primitives: native browser focus; one chooser request; owned audio resources; one server session. Invariants: each meeting gets new admission/sequence state; Stop closes its resources; subsequent meetings stay in the same document; microphone/system lane parameters, identity thresholds and phase attributes remain unchanged. Falsifier for a resource-reuse fix: rejection occurs before the new shared stream exists while the new microphone/context are valid.

| Intervention | Result | Interpretation |
|---|---|---|
| Original chooser; no test foregrounding | Second chooser fails in 3/3 baseline runs | Reproduces the reported blocker |
| `window.focus()` synchronously before chooser | Second chooser still fails | Discarded; not shipped |
| Conditional focus, `no-focus-change` prototype | 3 consecutive completed/final meetings | Focus transfer is causal; legacy spelling not shipped |
| Conditional focus, `focus-capturing-application` prototype | 3 consecutive completed/final meetings | Exact production choice measured before implementation |

The initial instrumented control used Playwright foregrounding and completed three meetings; its first row assertion incorrectly expected a session ID inside exported JSON. The export carries session identity in its **download filename**, not its JSON body. That assertion was corrected before the baseline/prototype rows above; the initial control is not counted as a passing E2E row.

The prototype wrappers called the original browser APIs and returned/rethrew their original results. Their only experimental intervention was the stated focus choice. The final E2E run has no native API wrappers or injected recovery. Throwaway prototypes are absorbed into row 14; retained traces and this verdict replace the temporary code.

## F3 — surgical production fix and regression

`CaptureClient.requestDisplayMedia()` detects conditional-focus support, constructs a **new controller per request**, sets `focus-capturing-application`, and passes it with the existing display constraints. All work remains synchronous inside the Share/Reshare click: no timeout, sleep, deferred chooser or automatic retry. New controllers avoid reusing a single-request controller across meetings or reshares. Browsers without this API retain their existing chooser behavior.

Chrome documents [conditional focus, including configuration before the chooser](https://developer.chrome.com/docs/web-platform/conditional-focus). The application keeps focus where Stop, meters and transcript are shown; selecting the shared audio source still uses the native chooser.

No ControlPanel phase transitions needed changing. `data-capture-phase` retains idle/configuring/ready/active/stopping/terminal behavior; microphone and shared audio remain required. Stop still tears down the old AudioContext and tracks, and Reset prepares a new client. Identity thresholds, decoder geometry, lane framing and acceptance predicates/selectors are unchanged.

The focused regression failed before the fix (1 failed / 40 passed), then passed with the fix. It checks focus configuration happens before the synchronous native call, a fresh controller is used for each new capture **and** reshare, and audio/video constraints remain intact. A test-helper type declaration was corrected after the first typecheck; final typecheck passes.

Validation completed: **202 frontend tests passed**, **52 focused capture/ControlPanel tests passed**, typecheck/build passed; **152 acceptance-facing workspace, locator, qualification and deployment tests passed**, no skips.

## E2E row 14

Row 14 performs **three** consecutive real live meetings, exceeding the requested two. It asserts:

- Same JavaScript document, no reload or replacement Page; no Playwright foregrounding during setup.
- Distinct meeting IDs, each starting frame sequence at zero.
- Every meeting reaches `completed` and `final`; UI moves active → terminal.
- Every meeting remains in history at the end.
- The pane's own downloaded export has the current meeting ID in its filename and nonempty turns, proving the second and third pane/export belong to the new capture.

One command for the focused scenario (stack running with the retained environment):

```sh
.venv/bin/python tests/e2e/verify_workspace.py --rows 14 \
  --base https://127.0.0.1:17863 \
  --corpus /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s \
  --output /tmp/moss-repeat-capture-new-run
```

Omit `--rows 14` for all fourteen rows. Use a fresh output directory. Full candidate result: **14/14 PASS** at `00ebcd10`. The retained run is `evidence/same-tab-repeat-capture-20260911/candidate/`; `results.json` links each row, screenshot, checked export and audio artefact. Both relay summaries pass; row 10 recognises the enrolled speaker in **3.6897 s**; both 3 s and 20 s outages survive and finalize. No previous row regressed.


## Final candidate evidence

| Row 14 cycle | Meeting | Server result | UI/export evidence |
|---:|---|---|---|
| 1 | `KG9-HjStVvGtqxEVczFIA9Bh` | completed / final; frame sequence 0 | [row-14-cycle-1.png](../../evidence/same-tab-repeat-capture-20260911/candidate/row-14-cycle-1.png); current meeting in export filename |
| 2 | `MTQ_bUUn1cyUTnwexgdQhz_i` | completed / final; frame sequence 0 | [row-14-cycle-2.png](../../evidence/same-tab-repeat-capture-20260911/candidate/row-14-cycle-2.png); current meeting in export filename |
| 3 | `Ap9X9sSfQhzvtOyVish2bXz5` | completed / final; frame sequence 0 | [row-14-cycle-3.png](../../evidence/same-tab-repeat-capture-20260911/candidate/row-14-cycle-3.png); current meeting in export filename |

All three were still in history at the end. No reload, replacement page, simulated recovery, automatic chooser retry or Playwright foreground operation occurred between those captures. The deployed capture client performed the focus intervention. Capture-phase attributes and acceptance predicates remain unchanged.


A final focused row-14 run adds an explicit empty-pane assertion **before each Start**. All three resets cleared the previous transcript, and all three subsequent captures produced nonempty exports bound to their new meeting IDs. This separates a fresh transcript from merely changing the export filename. Result: PASS, retained in `reset-proof/`. The change after `00ebcd10` is this harness assertion and evidence only; production bytes are identical.

Prevention: retain the same-document scenario as a required E2E row. Fresh-page fixtures still isolate unrelated checks, but cannot substitute for Stop → Reset → Start lifecycle coverage. Browser DOM focus alone is not sufficient evidence of native capture eligibility on macOS.

The isolated 17863 instance was stopped after measurement; its separate databases remain retained. No host operation, vLLM setting, identity threshold, first-decode boundary, acceptance predicate, or 17861 database was changed.
