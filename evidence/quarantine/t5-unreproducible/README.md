# Quarantined: unreproducible evidence from the first fleet's ticket 5

These three artifacts each cite a probe script that was never committed:

| artifact | cited probe |
|---|---|
| `iteration-2-helper-vocabulary-probe.txt` | `prototypes/browser-capture-feasibility/probe_helper_failure_vocabulary.py` |
| `iteration-3-capture-status-projection.txt` | `prototypes/streaming-diarization/proto_capture_status_projection.py` |
| `iteration-5-g7-worklet-lease.txt` | `prototypes/browser-capture-feasibility/probe_g7_worklet_lease.py` |

A gate whose probe is absent cannot be re-run by anyone, so none of this can be
verified or refuted. The G7 one is the clearest case: it was the only proof of the
backgrounded-tab gate, its own payload records `verdict.full_g7_gate: false`, it ran
for 65 s against a 2.0 s lease with synthetic oscillators, and Chrome does not reach
intensive throttling until roughly five minutes hidden — so it never entered the
regime the gate exists to test.

They are moved here rather than deleted so the record of what was claimed survives.
They are **not evidence** and must not be cited as such. `evidence/phase1/` is the
live evidence tree and the guardrail scans it; this directory is outside that scan.

Ticket 5 was independently reviewed and returned FAIL. Its real replacement work is
tracked under the rebuild fleet.
