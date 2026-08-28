# Phase-2 operator status projection probe

Run from the repository root:

```bash
uv run --frozen python prototypes/phase2-operator-status/probe.py
```

The probe attacks the policy boundary before production integration: one allowlisted current-state
projection, a restart baseline that invents no history, meaningful aggregate transition edges, and
a bounded content-free recent-event buffer. The verdict requires all four claimed edge families,
a same-phase lane-health edge, stable lifecycle safe-error tokens, and non-vacuous exclusion of
nine forbidden values injected into both fake Store and Live sources.

Each required family can be removed from the verdict input to prove the command exits nonzero:

```bash
uv run --frozen python prototypes/phase2-operator-status/probe.py \
  --suppress-event-code account_authority_changed
```

The other accepted suppressions are `active_meetings_changed`, `queue_depth_changed`, and
`capture_health_changed`.
