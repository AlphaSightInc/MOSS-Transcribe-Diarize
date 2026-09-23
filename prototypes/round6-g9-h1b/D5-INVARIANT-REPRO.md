# G9 D5 invariant review — falsifiable replay

## Question

Do H1B's two false G9 bits show a D5 product violation, or did the qualification predicates reject valid browser serialization / unrelated revision telemetry?

## Hypotheses

- `owner_payloads_only`: stale exact-shape predicate. The candidate sends only the selected completed Meeting's finalized transcript plus browser-owned request fields directly to its provider. Product defect remains possible only if a call contains another Meeting's content, sends settings to MOSS, or violates the owner's provider controls.
- `speech_capacity_unchanged`: the old predicate rejects `text_revision_applied` rows without a runtime clock, although those rows are not capacity reducer inputs. This stale guard is demonstrated on same-layer G4. H1B's full G9 capacity outcome remains a possible product defect because its aggregate operands were not retained.

## Falsifiers

- Payload hypothesis fails if a measured request contains nonselected or foreign Meeting text, provider settings in a MOSS request, ambient credentials, wrong owner prompt/model, `stream=true`, or fewer than 2048 tokens.
- Capacity hypothesis fails if the complete two-session G9 aggregate has any named capacity check outside its bound, or if the false bit reproduces after all retained and missing aggregates are checked and the untimed revision rows are excluded from reducers.

## One command

From this clone:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/round6-g9-h1b/run.py
```

The command prints only booleans, counts, key/type differences, and named check paths. It uses synthetic transcript text in a short-lived local fixture and a loopback fake provider; it makes no external provider or decoder request.

## Measured

- H1B `campaign/summary-checks.json` has 19 bits: 17 true; `owner_payloads_only` and `speech_capacity_unchanged` false. It has no per-bit diagnostics. The deployed G9 raw record retains only aggregate `RuntimeError` at `_record_summary_result`, not the nested capacity object.
- At the pinned `7f54b12f` candidate, the original owner predicate requires exact top-level keys `{model, stream, messages, max_tokens}` and raw numeric `{start,end,speaker,text}` segments. The production browser uses `providerBody(meeting, settings)`, requires a completed meeting, projects that meeting's transcript, preserves optional `source_lane`, formats times as `HH:MM:SS`, maps D45b `S00` to `Speaker uncertain`, and sends the request directly from the browser. D5 allows browser-owned request parameters; the lane consumer contract says summary input includes lane context. The local fake-provider replay passed 8/8 checks with two loopback POSTs, matching the owner model/prompt/token controls and only its synthetic owner's transcript. The old exact-shape predicate therefore explains the measured false bit; no D5 product violation was observed in that route. The H1B artifact does not retain the deployed request body itself.
- Both retained G9 summary-load sessions contain 60 `text_revision_applied` events without `runtime_monotonic_ns`. The old capacity predicate rejected any untimed event. Same-layer G4's recorded PASS artifact reproduced that guard; removing only those rows or supplying sentinel clocks made its complete capacity validator pass. G9's retained event reductions show pre-Stop RTF 0.10845 and 0.09821 (<1), with zero terminal-failure events. The full G9 aggregate is absent, including duration/requested duration, session/account rows, wrong-owner observations, RSS/cache samples, log counts, backpressure and campaign interval. Thus the old guard is a demonstrated predicate defect, but H1B product capacity remains **POSSIBLE / UNMEASURED**; do not report `speech_capacity_unchanged` as proven.

## Disposition

No product code or capacity bound was changed. Keep the owner predicate fix, retain named diagnostics, and require a complete future G9 aggregate before clearing the possible capacity defect. Attempts at this point: payload 2/3; capacity 3/3 (parked).

## Correction (lead, 2026-09-23, review F6)
The server already projects `S00` to "Speaker uncertain" before either the browser or the harness reads `GET /api/meetings/{id}`
(`app/phase2.py:2618-2628`), so `S00` was not a cause of the old `owner_payloads_only` mismatch; the real differences were
`response_format`, segment `source_lane`, `HH:MM:SS` timestamps and product ordering. D45b is the DER ruling, not a display projection.
