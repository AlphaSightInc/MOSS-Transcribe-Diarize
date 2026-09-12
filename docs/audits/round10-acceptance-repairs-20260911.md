# Round 10 acceptance repairs — no qualification run

These are code/test repairs, not evidence that Round 10 passes. No host service, policy,
quality bound, admission state, or candidate was changed by this work.

| Finding | Mechanism and repair | Regression |
|---|---|---|
| F1: crash probe strands subsequent measurements during restart | After the main-process kill, wait up to 60 seconds for systemd to supply a different positive PID **and** HTTP 200 from `/api/auth/session` (the existing readiness probe). Do not issue an explicit service start. Retain `crash-recovery-wait.json` before returning or failing, including kill result, PID, polls, elapsed time and readiness. A nonzero kill command result does not preempt recovery observation. | `tests/phase2/test_crash_recovery_wait.py`; existing archive-oracle crash test also exercises kill return codes 0 and 1. |
| F2: embedded identity changes RECORD on rebuild | `candidate_identity.write_build_candidate` owns sorted, indented UTF-8 JSON with one trailing newline. Both the documented `run.sh` recipe and qualification wheel rebuild call it. | `test_recipe_and_qualification_round_trip_identical_embedded_identity` compares CLI-recipe bytes, qualification bytes and embedded-wheel bytes with deliberately reordered input mappings. |
| F3: operator measurement uses invalid oracles | Retained systemd messages about `moss-web.service` come from `init.scope`, with `_COMM=systemd` and `USER_UNIT=moss-web.service`. Accept that exact provenance as well as direct unit messages. Status reads contain changing time/resource counters: three requests cannot be compared as one snapshot. A transparent local UDS relay captures the exact real response each installed CLI invocation renders. Compare each output with its own response. | `test_manager_records_are_bound_to_the_target_unit`; `test_status_capture_binds_each_rendering_to_its_own_response` accepts changing responses and rejects deliberately corrupted human/JSON output. Evaluator unchanged. |
| F4: capacity observes unfinished or truncated bookkeeping | Resumable Stop's 202 `stop_in_progress` was treated as completed by the acceptance replay adapter. Await terminal publication using the adapter's existing request budget (300 seconds for capacity), preserving the browser's five-second Stop payload. Also drain events incrementally: the product ring retains only 1,000 events. Retain per-session Stop waits and content-free events before evaluation. | `test_four_resumable_stops_close_the_rolling_ledger_before_measurement`; pending/failed/aborted/timeout tests; `test_capacity_event_capture_retains_all_600_seconds_past_product_ring_limit`; missing-sequence rejection test. |

## F4 evidence and limits

A deterministic 600-second production-runtime test emits 2,584 events. Reading only its
last 1,000 counts **93/240 canonical** and **24/60 rolling** completions. Incremental collection
retains all **240 canonical and 60 rolling** completions, totaling 3.0 measured fake-decoder
seconds. Neither the 1,000-event runtime bound nor any evaluator expectation changes.

The four-session pending-Stop regression reproduces the exact
`rolling admitted/completed accounting is incomplete` exception when sampled at accepted
Stop, and passes only after all four completion records exist. This establishes a reachable
collector defect, not the missing item IDs in Round 9: that run did not retain its relevant
Stop response or complete capacity ledger. No runtime counter defect has been established.

The minimal measurement contract is: accepted Stop is distinct from terminal publication;
every observed event sequence is collected once, with no silent gaps; all admitted work must
still meet the unchanged evaluator. A missing completion after genuine terminal publication
would falsify the premature-observation explanation and is now diagnosable from retained
`load-4/session-N-events.json` and `load-4/session-N-stop-wait.json`.

Validation (211 tests plus 9 subtests passed):

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/moss-prompt-fix/.venv/bin/python -m pytest -q \
  tests/phase2/test_crash_recovery_wait.py tests/phase2/test_candidate_identity_writer.py \
  tests/phase2/test_admin_status_capture.py tests/phase2/test_acceptance_journal.py \
  tests/phase2/test_acceptance_stop_pending.py tests/phase2/test_acceptance_stop_deadline.py \
  tests/phase2/test_wave1_qualification.py tests/phase2/test_operator_status.py \
  tests/test_live_service_replay.py tests/test_live_rolling_wiring.py
```
