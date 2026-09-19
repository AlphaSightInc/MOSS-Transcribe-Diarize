# P1 mixed-work scheduler prototype

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/streaming-diarization/mixed-work-scheduler/probe.py
```

## Contract

- **Question:** Can two unequal-arrival Live meetings remain current while File/URL uses
  spare decoder capacity and yields at a real window boundary?
- **Minimum state:** ordered per-meeting items, source-audio frontier, arrival/start/finish
  clocks, non-preemptible decoder slots, and cancellation/Stop.
- **Invariants:** every Live item runs once in meeting order; peak calls stay bounded; queued
  background cancellation dispatches nothing later; Live outranks queued background work;
  changing scheduling alone does not change request geometry.
- **Assumptions:** retained R1 service times transfer to a two-session replay; one
  `WindowedRunner` window is File/URL's safe yield boundary. Production retains one serial
  canonical pump across both Live meetings. Real mixed throughput is unmeasured until a GPU
  lease is granted.
- **Falsifier:** sustained pending Live audio at Stop, reorder/drop/duplicate, peak above the
  selected bound, Live waiting behind queued background work, or two stopped-meeting
  settlement calls occupying both slots while another meeting is still recording.
- **Tool rationale:** replaying content-free production queue events isolates scheduling
  causality. A real decoder run is still required to measure the non-preemptible window and
  output preservation.

## Verdict

**Promote a two-slot dispatch gate with one background maximum; retain the existing serial
Live pump and request geometry. Classify File/URL and stopped-meeting terminal settlement as
background. Reject coalescing and a second Live pump.**

The 120-second retained replay used 54 `mono_javier_intro_50s` items and 50
`discussion_jamie_dimon_panel` items plus a 12-second non-preemptible File window. Letting
background share the only serial slot put Live queue-wait p95 around 10.6–11.5 seconds.
Coalescing barely helped and changes decoder context, so it failed the semantic-risk bar.

The production-shape arm kept **one serial Live pump** and allowed one background call in
the second decoder slot. It preserved every item once and in order, drained both meetings
by simultaneous Stop, and never exceeded two total calls or one Live call. Its replay p95
was below 0.60 seconds, but that number is **not a production latency estimate**: replayed
service times do not model provider contention. The existing real two-session baseline is
1.7–2.65 seconds; only the counted mixed run may decide whether this change preserves it.
The two-Live-pump arm is retained solely as a rejected counterfactual.

A deliberate naive two-worker run initially failed ordering because two items from one
meeting overlapped. That failure plus the actual runtime topology rejects a second Live
pump; production keeps one serial pump across meetings.

The 2/5/10/12/20-second background sweep left the Live replay unchanged because the gate
allows at most one background request. The asymmetric Stop falsifier started two 30-second
terminal settlement calls at 45 seconds: the second waited until 75 seconds while 26 Live
items dispatched during the first settlement. Thus bulk finalization cannot monopolize the
reserved realtime slot. These are deterministic policy results, not throughput evidence.
Actual File window duration, provider interaction, saved words/identity, and end-to-end
backlog remain pending a counted real run after lease.

`results.json` retains full arrival/start/finish/display records and summary projections.
