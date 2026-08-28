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

All nine forbidden source sentinels were absent from both status and journal serialization. After
more than the configured bound, exactly 64 recent events remained. The largest measured event was
324 bytes, putting that private diagnostic buffer below 20,736 serialized bytes. The buffer is not
returned by status and is not an audit record; every allowed edge is emitted immediately to the
service journal. External log retention remains operator policy.

Production therefore absorbs one current-state projection, one aggregate edge reducer, a private
64-event bound, and a baseline rule: first observation records readiness but invents no earlier
Account or Meeting transition.
