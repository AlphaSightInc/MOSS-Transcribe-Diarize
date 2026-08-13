# Live concurrency bench

Ticket #3's bounded-dispatcher measurement extension. The first artifact freezes the gates and
metric definitions before any concurrency run.

Question: what is the largest dispatcher concurrency in `{1, 2, 4}` that keeps live transcript
lag and memory below the frozen gates on the production live path?

One-command preregistration check (prints the full frozen state):

```bash
python3 prototypes/streaming-diarization/concurrency/validate_preregistration.py
```

Controlled scheduler/queue probe (about 40 seconds; prints full state):

```bash
python3 prototypes/streaming-diarization/concurrency/proto_controlled_dispatcher.py
```

This replays hash-pinned real human-speech PCM in 0.5 s frames through the production runtime and
scheduler, but deliberately controls speech observations, decode, identity, and scheduler release.
It can reject scheduler/queue hypotheses; it cannot qualify G4 or G5.

The future measurement runner must load and hash-pin `preregistration.json`. Missing real decoder
results or missing local vLLM active/queued metrics cannot qualify a bound. Stubbed decoder runs may
exercise fairness and queue semantics, but remain labelled non-gating.
