# Phase-2 one-Meeting operator interruption

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python prototypes/phase2-operator-interrupt/probe.py
```

The probe prints its full contract, every Meeting state, derived checks, and `PASS`/`FAIL`.
It exits nonzero when a load-bearing fence or cleanup behavior is suppressed.

This prototype decides only the new composition policy: one opaque Meeting claim and one
service-owned interrupt lifetime. Production Live/File owners remain the only authors of
transcript, audio, and working-source settlement.
