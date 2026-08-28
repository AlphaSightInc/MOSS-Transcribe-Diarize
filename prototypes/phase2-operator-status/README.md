# Phase-2 operator status projection probe

Run from the repository root:

```bash
uv run --frozen python prototypes/phase2-operator-status/probe.py
```

The probe attacks the policy boundary before production integration: one allowlisted current-state
projection, a restart baseline that invents no history, meaningful aggregate transition edges, and
a bounded content-free recent-event buffer.
