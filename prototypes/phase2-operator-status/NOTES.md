# Phase-2 operator status projection verdict

Run:

```bash
uv run --frozen python prototypes/phase2-operator-status/probe.py
```

**VERDICT: PASS.** The absorbed production reducer emitted one readiness event on the first
observation, zero events for an identical observation, and exactly Account-authority,
Meeting-lifecycle, queue-depth, and capture-health edges after the measured state change. A fresh
production reducer observing the already-active state emitted readiness only; it did not fabricate
an admission or Meeting-lifecycle history.

The pre-correction production seam failed exactly three falsifiers: `Account revoked by operator`
and `service shutdown` each raised `OperatorProjectionError`, and a microphone `active`→`failed`
change emitted no edge while the capture phase remained `recording`. After correction, the same
paths remained available with `meeting_authority_revoked` and `service_shutdown` safe-error codes,
and the lane change emitted `capture_health_changed` with bounded aggregate health counts.

A second correction attacked the runtime fallback that names an unexpected exception by class.
The production `_failure_from_exception(RuntimeError(...))` shape produced code `RuntimeError` and
made the pre-correction status serializer fail. The corrected projection preserved existing safe
codes but reduced that invalid class-name code to `live_terminal_failure`; status remained
available and no class name or exception text crossed the projection. The measured shutdown trace
was `live_settlement_started` → `live_settlement_finished` → `operator_stopped`, so the final
stopping snapshot observed the settlement-created `service_shutdown` error rather than preceding
it.

All nine forbidden sentinels were first verified present in the fake Store/Live sources and absent
from every status and emitted journal serialization. Suppressing each required transition code
independently produced verdict `FAIL` and process exit 1. After more than the configured bound,
exactly 64 recent events remained. The largest event across every emitted family was 433 bytes,
putting that private diagnostic buffer below 27,712 serialized bytes. The buffer is not returned by
status and is not an audit record; every allowed edge is emitted immediately to the service
journal. External log retention remains operator policy.

Production therefore absorbs one current-state projection, one aggregate edge reducer, a private
64-event bound, canonical lifecycle-error reduction, and a baseline rule: first observation records
readiness but invents no earlier Account or Meeting transition. Per-File work phase remains an
internal input to aggregate queue/worker truth and never crosses the status surface. These measured
choices implement `docs/phase2-afk-charter.md` §7; no operator-observability ADR exists.
