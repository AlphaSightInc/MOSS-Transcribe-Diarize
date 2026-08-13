# Live concurrency bench

Ticket #3's bounded-dispatcher measurement extension. The first artifact freezes the gates and
metric definitions before any concurrency run.

Question: what is the largest dispatcher concurrency in `{1, 2, 4}` that keeps live transcript
lag and memory below the frozen gates on the production live path?

One-command preregistration check (prints the full frozen state):

```bash
python3 prototypes/streaming-diarization/concurrency/validate_preregistration.py
```

The future measurement runner must load and hash-pin `preregistration.json`. Missing real decoder
results or missing local vLLM active/queued metrics cannot qualify a bound. Stubbed decoder runs may
exercise fairness and queue semantics, but remain labelled non-gating.
