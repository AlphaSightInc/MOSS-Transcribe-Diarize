# Live concurrency bench

Ticket #3's bounded-dispatcher measurement extension. The first artifact freezes the gates and
metric definitions before any concurrency run.

Question: what is the largest dispatcher concurrency in `{1, 2, 4}` that keeps live transcript
lag and memory below the frozen gates on the production live path?

One-command preregistration check (prints the full frozen state):

```bash
python3 prototypes/streaming-diarization/concurrency/validate_preregistration.py
```

CPU/HF-local preregistration (the deployed geometry is read from descriptors at run time;
this profile deliberately does not claim GPU figures):

```bash
python3 prototypes/streaming-diarization/concurrency/validate_cpu_hf_local_preregistration.py
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

The CPU/HF-local runner must instead hash-pin `cpu_hf_local_preregistration.json`, compare its local
descriptor with the read-only deployed descriptor before capture, and retain the raw arrays named in
that contract. It may establish the local portions of G4 and G5, never deployed GPU latency or GPU
utilisation.
