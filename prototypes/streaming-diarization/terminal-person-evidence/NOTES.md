# Terminal person evidence

## Contract

- **Question:** Does terminal long-context decode hear Jamie as a distinct local speaker that the existing live album already represents acoustically, but the time-overlap mapper cannot connect?
- **Minimum primitives:** terminal local-speaker interval; live album evidence interval; existing cosine match floor and runner-up margin; time overlap as the current control.
- **Invariants:** no new person from label count; no threshold change; one terminal local maps to at most one live canonical; ambiguous acoustic evidence remains unattributed.
- **Unknown:** whether Jamie speech and the adjacent live-labelled Jamie laughter are stable enough for the production encoder.
- **Falsifier:** Jamie-to-live-third score misses 0.35, fails the 0.1 runner-up margin, or a different live person is competitive.
- **Tool:** production pinned encoder on the actual retained meeting MP3 and exact source-adjudicated intervals. No decoder calls.

## Run

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/terminal-person-evidence/probe.py
```

## Verdict

**Rejected.** The terminal Jamie phrase and the live third identity's adjacent Jamie
laughter have zero time overlap, explaining why overlap mapping cannot connect them. But
the production encoder also cannot connect them: terminal-to-live-third cosine was 0.027,
below Ben 0.082 and David 0.061, and far below the existing 0.35 / 0.1 rule. Acoustic
terminal mapping would therefore abstain correctly. The missed-participant gate remains
unmet; neither label-count forcing nor a lower threshold is justified.
