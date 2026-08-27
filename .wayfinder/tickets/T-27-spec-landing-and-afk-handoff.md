---
id: T-27
map: map-002-phase2-multiuser
title: Where the Phase-2 spec lands and how the AFK loop consumes it
type: grilling
status: closed
assignee: operator+codex
blocked_by: []
---

## Question

Where does the decision-complete Phase-2 spec physically live, and in what form does the AFK
builder loop consume it?

Phase-1 precedent (closed ticket *Where the Phase 1 spec lands and how the AFK loop consumes
it*): several ADRs under `docs/adr/` continuing the numbered sequence, `.wayfinder/` committed
and git-tracked, planning artifacts living with the code, plus a binding charter
(`docs/phase1-afk-charter.md`) carrying authority/limits/gates.

Decide, with the operator:

- **Follow the precedent or diverge** — ADR-per-family + a `phase2-afk-charter.md`, vs one
  consolidated spec document, vs the control-plane PRD form the older MCW map used.
- **Implementation tracker** — Phase-1 cut implementation tickets on the private `aiSight-us`
  GitHub tracker (never upstream, C7): same for Phase 2?
- **Branch/merge posture for the fleet** — Phase-1's serialized self-merge to `dev` protocol:
  inherit, or does multi-user work (schema migrations, auth cutover) need a stricter gate?
- **Commit of this map** — `.wayfinder/` map-002 files are currently uncommitted in a
  user-owned dirty worktree; when and by whom they get committed.

Resolution records the landing form, tracker, merge posture, and commit plan. Small ticket,
no blockers — takeable first; its answer templates every later resolution's "where does this
decision get written" step.

## Resolution

**Follow the Phase-1 landing pattern, with unrestricted agent self-merge under the existing
serialization protocol (operator, 2026-08-26).**

- **D1 — Landing form:** the durable product specification lives in this target repo as one
  independently revisable ADR per hard-to-reverse Phase-2 family, continuing the existing
  `docs/adr/` sequence, plus one binding `docs/phase2-afk-charter.md` for fleet authority,
  limits, sequencing, and acceptance gates. The AFK loop consumes implementation tickets that
  cite the applicable ADRs and charter sections. The control plane keeps process state,
  ledgers, evidence, and review decisions; it is not the product specification.
- **D2 — Implementation tracker:** after this map reaches its destination, cut implementation
  tickets on the private `aiSight-us/MOSS-Transcribe-Diarize` GitHub tracker. Never create them
  on upstream `OpenMOSS`.
- **D3 — Merge posture:** every implementation agent may self-merge to `dev`. Inherit the
  Phase-1 merge-only protocol unchanged: acquire the shared merge lock, merge current `dev`
  into the ticket branch, validate the merged result, fast-forward `dev`, and revert a breaking
  merge. There is no supervisor-only class for schema or authentication changes.
- **D4 — Commit plan:** after the map closes, the Wayfinder owner makes a path-scoped Phase-2
  planning commit containing map-002, its tickets/research, the Phase-2 ADRs, and the charter;
  then merges that commit into `dev` before AFK builders launch. Unrelated user-owned dirty
  work is never staged, cleaned, stashed, switched, or committed.
