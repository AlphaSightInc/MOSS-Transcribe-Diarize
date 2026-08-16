# Phase 1 gate status

Single rollup of the ten acceptance gates ruled in `docs/phase1-afk-charter.md` §6.
**This file, not the handoff chain, is the answer to "what is done."**

Measured 2026-08-16 on `dev` @ `4e8cae5`, post-reboot, host validated, no concurrent suites.
Every row cites a raw artifact and states what that artifact does **not** cover — charter §3
requires it, and nothing else in this repo enforces it at gate level.

## Baseline (supersedes every earlier number)

```
.venv/bin/python -m pytest -q -p no:randomly
2 failed, 1063 passed, 2 skipped, 4 warnings, 394 subtests passed in 107.45s
```

Frontend: typecheck clean · vitest 99/99 · 13 files.

The pre-reboot `6 failed` reading is **retired**. The four `test_macos_uds_tracer` failures were
environmental — they tracked the wedged trust subsystem (`codesign` → `CSSMERR_TP_NOT_TRUSTED`,
Chrome → exit 134) and cleared with the reboot exactly as predicted. Codex's `2 failed / 1063 passed`
reproduces byte-for-byte; the standing disagreement is resolved in its favour.

The two remaining failures are deliberate and permanent for Phase 1:

| Failure | Why it stays |
|---|---|
| `l15/test_l1_baseline.py::test_a2_instrument_is_hash_pinned_and_production_bound` | The pin correctly refuses L1.5 measurement when the product tree has moved. Fixing it would disarm the guard. |
| `l2-stage0/test_legacy_ingest.py::test_all_92_archived_units_render_into_parseable_preparations` | The 92-unit corpus is untracked, so the count varies per worktree. Environmental, not a defect. |

**No-regression bar (G10) is now `2 failed / 1063 passed / 394 subtests`.**

## Gate rollup

| Gate | Verdict | Basis |
|---|---|---|
| G1 mic lane e2e, real | ✅ **PASS** | `evidence/phase1/t1/iteration-10-real-model-browser.json`, `iteration-14` |
| G2 system lane, synthetic | ✅ **PASS** | `t1/iteration-10-real-model-browser.json` |
| G3 two-lane display capture | ⛔ **OPERATOR** | charter §7 attended checklist; no agent may claim it |
| G4 concurrency ≥10 min | ❌ **NOT MET** | `t3/iteration-4-controlled-dispatcher.json` self-declares `qualifies_g4_or_g5: false` |
| G5 cross-session integrity | 🟡 **PARTIAL** | `t1/iteration-12`, `iteration-14` — 2 sessions proven; overload + reconnect not |
| G6 failure paths | 🟡 **PARTIAL** | `x3-capture-health/review-01`, `review-02` — 5 of 6 paths; two known holes |
| G7 background tab | ✅ **PASS** | `x1-frame-drop/postreboot-g7-hidden-8000.json` — reproduced 2026-08-16 on the repaired host, tautological assertions replaced first |
| G8 fidelity | ❌ **FAIL** | `r1-reference-ui/screenshot-diff-iteration-10-blocked/report.json` — 11.56 % / 17.04 % vs a 2 % bar |
| G9 modes | ❌ **NOT BUILT** | file mode is a cosmetic stub; no `/api/jobs` call exists in `frontend/src/` |
| G10 no regression | ✅ **PASS** | baseline above; +53 passed, +7 subtests vs `f6353eb` |

---

## G1 — mic lane e2e, real · PASS

`t1/iteration-10-real-model-browser.json`: Chrome fake-device microphone → production v2 routes →
manifest-admitted provider bundle → local production `ModelRunner` → browser render.

```
chrome_microphone_to_real_model_to_browser_render : true
at_least_two_distinct_speaker_ids_rendered        : true
exact_descriptor_frame_geometry                   : true
zero_sequence_gaps                                : true
```

That artifact records `clean_stop: false`; it is superseded by `t1/iteration-14-concurrent-clean-stop.json`,
which reaches `concurrent_clean_stop_gate: true` and `both_sessions_stopped_cleanly: true`.

**Does not cover:** real display capture (`real_display_capture: false` — that is G3), any deployed
host, the GPU host's model, or attended operation.

## G2 — system lane, synthetic · PASS

`synthetic_system_to_production_routes: true` in the same artifact, through the production live routes.

**Does not cover:** real display capture. Recorded as such, per the charter's explicit instruction that
G2 must state it does not prove G3.

## G3 — two-lane display capture · OPERATOR

Deferred to charter §7 by ruling. Charter §1 forbids automating the display chooser: the standard
requires a fresh user gesture per capture and permits no persistent grant; the 2026-08-03 CDP-flag
attempt failed with `NotReadableError`. **Do not retry it.**

~10 minutes attended. It is the only artifact that demonstrates the product as a product.

## G4 — concurrency ≥10 min · NOT MET

`t3/iteration-4-controlled-dispatcher.json` is a prototype that **declares its own insufficiency**:

```
qualifies_g4_or_g5                             : false
correct_nonterminal_429_semantics_observed     : false
all_markers_isolated                           : true
fairness_skew_within_frozen_gate               : true
queue_capacity_is_session_local                : true
```

Nothing in `evidence/` sustains the measured bound for ten minutes, and no p95 transcript-lag figure
exists. `t1/iteration-12` does observe `per_session_backpressure_observed: true`, which is the
per-session-not-global half of the bar — but over a short run at concurrency 2.

**To close:** a ≥10-minute run at the ticket-3 bound recording p95 lag, round-robin fairness, absence
of OOM, and per-session 429.

## G5 — cross-session integrity · PARTIAL

`t1/iteration-12` and `iteration-14` both record, with the real model:

```
distinct_real_model_transcripts_rendered  : true
no_cross_session_marker_in_rendered_text  : true
stopped_views_revoked                     : true
only_test_capture_credential_revoked      : true
```

Note the criterion is *text never crosses*, not *reads are forbidden* — T-01 accepted a single trust
domain, so the historical `403` cross-read result is **not** a criterion.

**Does not cover:** overload, or reconnect. Both are named in the charter bar. Two sessions is not
overload. Closing G5 most likely rides along with the G4 run.

## G6 — failure paths · PARTIAL

`x3-capture-health/review-01-five-scenario-route.json` (`all_checks_passed: true`) and
`review-02-live-uvicorn-wire.json` (`all_checks_passed: true`, real TLS socket, own uvicorn, no
TestClient) cover:

| Charter path | Covered |
|---|---|
| microphone permission denied | ✅ `6-microphone-denied-terminal-capture-credential` |
| surface without share-audio → preflight fails | ✅ `1-system-lane-never-sent-a-frame` |
| one lane dying mid-session | ✅ `2-one-frame-each-then-nothing`, `5-server-lane-health-failed` |
| 429 backpressure | ✅ `4-sequence-gap-58-consecutive-rejects` |
| terminal 409 | ✅ `7-terminal-repoll-with-since-version` |
| **reload mid-capture reattaching from `sessionStorage`** | ❌ **not implemented** |

Two holes, both real:

1. **Reattach is unwired.** `frontend/src/lib/persistence.ts` exports `loadSessionId` /
   `saveSessionId` / `clearSessionId`, and `storageKeys.sessionId` exists — but the only production
   consumer of that module is `state/ui.ts`, and it reads the two panel-collapse booleans. **No code
   calls the session-id functions.** A library with no caller does not satisfy a failure path.
2. **A viewer cannot learn why its session died.** `live_auth.py:26` —
   `VIEWABLE_SESSION_STATUSES = frozenset({"active", "closing"})`. Measured directly in
   `x3/iteration-10-terminal-readable.json`:
   ```
   snapshot_returns_server_authored_reason_to_capture_credential : true
   snapshot_returns_server_authored_reason_to_view_credential    : false
   ```
   The capture credential gets a readable reason; the view credential gets nothing.

**Does not cover** (recorded in the artifacts' own `scope`): no browser, no real permission prompt,
no deployed host, single process.

## G7 — background tab · PASS

Re-run 2026-08-16 on the repaired host — the first execution since Chrome could launch again.
`x1-frame-drop/postreboot-g7-hidden-8000.json`, `passed: true`, **all 14 assertions pass**:

```
hidden_duration_ms                     : 309491   (> the 300 s intensive-throttling threshold)
heartbeats                             : 621 total, 620 hidden, all HTTP 200, zero sequence gaps
hidden frames per lane                 : 620 microphone, 620 system
cadence: accepted_minus_elapsed_expected : 0 on both lanes (620 accepted, 620 expected)
live_helper_lease_seconds              : 2.0    · max hidden heartbeat delta stayed below it
failed_samples                         : 0 on both lanes · lane health: active
session status after hidden phase      : active
```

The heartbeat-throttling trap is discharged: worklet port messages carried the cadence where timers
would have collapsed to ~1/min in a hidden tab.

**The probe was strengthened before the re-run**, because the prior sign-off rested on artifact
inspection and two of its assertions could not fail
(`prototypes/browser-capture-feasibility/probe_g7_hidden_tab.py`):

| Removed | Why it was vacuous | Replaced with |
|---|---|---|
| `each_lane_has_contiguous_hidden_accepted_sequence_progression` | Strict v2 only ever admits `next_frame_sequence`, so the admitted set is contiguous by construction; a worklet that stopped producing looks identical to one that never missed a beat. | `each_lane_hidden_worklet_emissions_are_contiguous_and_admitted_unrenumbered` — contiguity of the **worklet's own** `emitted_sequence`, plus `emitted_sequence == sequence`. The route cannot influence either. |
| `strict_v2_accounting_matches_descriptor_frames` | Asserted `accepted_samples == next_sequence * frame_samples`, an identity the server maintains by construction. Would hold if the tab had been silent for an hour. | `server_lane_accounting_matches_client_frame_telemetry` — the lane's `next_sequence` must equal the frames the **client** recorded emitting (hidden + visible), with `failed_samples == 0`. |

Both replacements were falsified before use: run against a deliberately truncated record set
(520 frames dropped), the old assertions still returned `true` and the new ones returned `false`.

**Does not cover** (probe's own `scope`): no model inference, no display capture, synthetic 48 kHz
sources, headless Chrome hidden by a DevTools-created sibling rather than a real user backgrounding
the window.

The pre-reboot artifact `iteration-5-g7-hidden-8000.json` is retained unmodified for comparison; its
numbers match this run closely, which is itself evidence the degraded host had not corrupted it.

## G8 — fidelity · FAIL

Bar (charter §5): ≤ 2 % differing pixels per viewport, no single 4-connected region > 1 % of viewport.

| Run | 1440×900 | 1280×800 |
|---|---|---|
| iteration-7 | 27.29 % / 17.42 % | 29.87 % / 22.45 % |
| iteration-9 | 11.52 % / 3.13 % | 17.04 % / 7.55 % |
| **iteration-10 (latest)** | **11.56 % / 3.13 %** | **17.04 % / 7.55 %** |

*(differing-pixel % / largest-region %; both bars are 2.0 % and 1.0 %)*

Real progress — 27 % → 11.6 % — but still ~5.8× the pixel budget and ~3.1× the region budget, and the
last two iterations moved essentially nothing. `passed: false` in every recorded run.

Where the difference lives, at 1440×900:

| Region | px | share of masked difference |
|---|---|---|
| `#control-panel` | 75 756 | **50.6 %** |
| `#transcript-panel` | 73 055 | **48.8 %** |
| `.topbar` | 3 412 | 2.3 % |

**Two structural problems with the gate itself, not just the pixels:**

1. **The config implemented 2 of the 4 ruled exemptions.** `tests/fixtures/reference_ui_screenshot_diff.json`
   carried only `right-column-rail` and `mode-segmented-control`. Charter §5 also rules exempt the
   **preflight modal** and the **`.tr-legend-right` Transcript|Summary toggle** (added 2026-08-14).
   - `transcript-summary-toggle` (`.tr-legend-right`, present in both trees) **added 2026-08-16** —
     implementing a ruling the config had simply missed. The harness raises on an exemption selector
     that does not render (`reference_ui_screenshot_diff.py:210`), so this cannot silently no-op.
   - The preflight-modal exemption has no selector to bind, because preflight ships inline in
     `ControlPanel` rather than as a modal (see *Deviations* below). Superseded by point 2.
2. **`#control-panel` is largely outside the numeric bar by ruling, yet supplies half the failure.**
   Charter §5: *"Where reference pixels do not exist (preflight, token entry): the standard is the
   reference's own CSS custom properties, type scale, spacing, and four bundled font families reused
   verbatim. Reviewed by the supervisor, not gated numerically."* The capture-bearer field, the
   echo-route choice, the two lane meters and the share-audio step all live inside `#control-panel`
   and have no reference pixels. The config does not encode that ruling.

**Also: every recorded run is stale.** All four used
`candidate_frontend: ~/.treehouse/MOSS-Transcribe-Diarize-e7521b/1/…/frontend` — a worktree that
predates the `App.tsx` orchestration and `ControlPanel` port on `dev`. No fidelity number exists for
the code that actually ships.

**Open decision — not taken unilaterally.** Every Phase 1 control without reference pixels sits
inside one wrapper, `.capture-supervisor` (`ControlPanel.tsx:184`): capture-bearer field, the
memory-only note, the headphones/speakers select, both lane meters, and the capture buttons. Exempting
that one selector would be the faithful reading of §5 — but it masks roughly half of the remaining
difference and could turn a failing gate into a passing one. Charter §8 forbids weakening a test to
make a gate pass, so this is the operator's call, not an agent's. **It is a ruling to confirm, not a
measurement to take.**

**To close, in order:** confirm (or refuse) the `.capture-supervisor` exemption → re-measure against
`dev` rather than the stale worktree → then treat whatever remains in `#transcript-panel` as the real
fidelity debt. Charter §5 is explicit that the transcript-pane exemption is deliberately narrow: it
covers the toggle's own box and nothing else in the pane.

## G9 — modes · NOT BUILT

Bar: *"Live mode and file mode both work through the one UI."*

Live mode works. **File mode is a cosmetic stub.** `frontend/src/App.tsx:68-96` renders a file input
that sets a filename string into local state and does nothing further:

```tsx
onChange={(event) => setSelectedFileName(event.currentTarget.files?.[0]?.name ?? "")}
```

`grep -rn "api/jobs" frontend/src/` returns **nothing**. Tracker issue #8 (client-side adapter over
the certified `/api/jobs` pipeline) is unimplemented.

Related, tracker issue #9 — live transcript export to file (md, txt, json) — is also unimplemented.
`frontend/src/lib/transcriptExport.ts` exports only `formatTranscriptClockTime` and
`buildTranscriptExportText`; its sole consumer is the **Copy** button in `TranscriptPane.tsx:258`.
There is no download path and no md/txt/json serializer.

## G10 — no regression · PASS

| | `dev` @ `f6353eb` | `dev` @ `4e8cae5` |
|---|---|---|
| failed | 6 (4 environmental) | **2** |
| passed | 1006 | **1063** (+53 net) |
| subtests | 387 | **394** (+7) |

---

## Tracker

All **9** implementation issues on `github.com/aiSight-us/MOSS-Transcribe-Diarize` remain **open**.
Per charter §1 an agent may not close them — comment evidence; the orchestrator closes.

Issues 8 and 9 are the only ones with no implementation at all (see G9). The other seven have
substantial implementations on `dev` whose gates are the rows above.

## Deviations from the charter, accepted rather than defects

- **Preflight ships inline in `ControlPanel`, not as the modal charter §4 ruled.** Functionally
  complete: bearer entry, headphones/speakers echo choice, dual-meter gating that refuses session
  creation until both lanes read non-zero, share-audio step, lane replacement. Building a modal shell
  around working controls buys pixels that are exempt from the pixel gate anyway. Recorded, not fixed.

## Known-open, unowned

- ~~`scripts/afk-guardrails/preflight.py` citation blind spots~~ — **both addressed 2026-08-16**, because
  this ledger's credibility rests on the cited artifacts being real and re-runnable.
  - The citation pattern matched only filenames containing `probe`/`proto`, so a generator named
    anything else (`run-final-gate.sh`, `regenerate_*.py`, a `measure_*.py`) could be deleted
    invisibly. It now matches any cited `.py`/`.sh`/`.js`/`.ts`/`.mjs` runner.
  - Existence was the only check, so a probe rotted past loading still passed. Cited Python runners
    are now compiled.
  - Noise controls, both necessary: a citation followed by `:<line>` is a traceback frame, not a
    runner claim (captured vLLM and pytest output is full of them); an absolute path outside the repo
    describes someone else's disk, not this tree.
  - **What this still does not cover, stated plainly:** compiling proves a file parses, not that it
    runs. A probe importing a deleted module, needing an uncommitted fixture, or failing against
    current `dev` passes. Proving re-runnability means running it, which a per-iteration preflight
    cannot afford — these probes drive Chrome for minutes. Re-running stays the reviewer's job.
  - Post-fix the check reports **0 violations**, and the broadened pattern demonstrably sees runners
    the old one could not.
- **T-02's auth mutation battery is not re-runnable from this repo.** Surfaced by the broadened
  citation check before it was scoped back to repo-relative paths.
  `evidence/phase1/t2/iteration-05-auth-mutation-battery/harness-sha256.txt` cites
  `mutation-harness.py` and `rereview-harness.py` at `/tmp/A-025-rr/`, `/tmp/A-025-mut/`, and in the
  **control-plane** repo (`0.AISIGHT_LOOP/moss-transcribe-diarize/runs/A-025/validation/`). The
  `/tmp` copies are gone; the control-plane copies are in a different repository. The SHA-256 file
  proves the copies were byte-identical, so the evidence is honest — but nobody working in this repo
  can reproduce it. Deliberately *not* a preflight stop condition (it would halt the fleet over a
  cross-repo artifact); it is a review finding against tracker issue #2.
- No post-`1db447c` adversarial review has been run, per the AFK3 stop order. New findings are
  follow-up work, **not** grounds to reopen AFK3 reconciliation.

## Open decisions carried forward

1. **Minimum canonical queue depth — measured 2026-08-16, and the urgency is lower than reported.**

   Weighted admission (`1db447c`) means a frame or Stop tail whose predicted span weight alone
   exceeds `max_queue_depth` can never be admitted: `accept_frame` returns retryable backpressure
   forever (`live_service_runtime.py:516-533`) and `stop` raises `TimeoutError` (`:643`). The
   handback left the floor as an open human decision. It is measurable, so it was measured — by
   driving the real `EndpointPolicy` over one `frame_samples` frame across every speech pattern:

   | Endpoint geometry | worst spans / frame | worst Stop tail | floor |
   |---|---|---|---|
   | **deployed** (`min_speech 1600`, `min_silence 8000`, `pad 1600`, `hard_cap 40000`) | 1 | 1 | **1** |
   | same, no hard cap | 1 | 1 | **1** |
   | aggressive (`min_speech 160`, `min_silence 320`, `pad 0`, `hard_cap 1600`) | **25** | 1 | **25** |

   Two corrections to the received account:

   - **Nothing is broken at the shipping geometry.** `min_silence_samples` (8000) equals
     `frame_samples` (8000), so at most one span can close per frame. `max_queue_depth` is already
     validated positive (`:141`), so the floor of 1 is met by construction. No configuration in this
     repo (2, 16, 20, 21, 64, 256) is unadmittable today.
   - **The Stop tail is never the binding constraint.** `_close_open_partition`
     (`live_endpoint.py:155-165`) emits hard-cap spans *during* `observe()`, so the open partition
     never exceeds one `hard_cap_samples`, and `preview_stop_work_items()` measured 1 in every
     geometry. The `required_work_items > max_queue_depth` `TimeoutError` at `:643` is effectively
     unreachable.

   The hazard is real but conditional: it appears only if endpoint config is tightened. At
   `hard_cap_samples 1600` a single frame yields 25 spans, and any deployment below that silently
   retries forever.

   **Recommended: a derived floor at manifest finalization, not a product-policy debate.** Do not
   hand-derive a formula — the closed form drifts from the policy (a first attempt here predicted 25
   for the deployed geometry, where the true answer is 1). Instead instantiate the *configured*
   `EndpointPolicy`, drive one `frame_samples` frame with the alternating worst-case pattern, count
   the spans, and require `max_queue_depth >= that`. It cannot drift, because it is the policy. It
   cannot live in `LiveServiceBounds.__post_init__` (`:139-148`) — that dataclass cannot see endpoint
   geometry — so it belongs beside `bounds_config` parsing in `live_provider_bundle.py:1279` /
   `live_manifest_finalizer.py`, where a misconfigured deployment fails at load instead of at 3 a.m.
2. **The 1-second browser terminal-request bound** is explicit policy. Change only deliberately.
3. **L15 pin and the archived 92-unit L2 corpus** — recorded above as permanent Phase 1 baselines.
4. **Two design calls Codex made on the operator's behalf**: threading `terminal_session_status` into
   `live_capture_status.py`, and a distinct `"stopped"` → *"Audio capture stopped."* capture phase so
   a clean stop no longer reports `failed`.

## Provenance

- `docs/handoffs/handback-afk3-20260815.md` — Codex's close-out; authoritative for what AFK3 did.
- `~/.claude/reboot-checkpoints/moss-20260814-174105/` — 1218-file forensic checkpoint, SHA-256
  manifest. Read `POST_CHECKPOINT_UPDATE.md` first; it supersedes the rest.
- `docs/phase1-afk-charter.md` — binding authority. `.wayfinder/map-001-phase1-chrome-client.md` and
  the 12 closed tickets are settled premises; do not re-litigate.
