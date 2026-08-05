# Campaign L1.5 bench

Prototype-only live-mode identity uplift campaign governed by
`docs/plans/l15-live-uplift-0804.md`.

L1.a freezes corpus membership before measurement. Candidate families are not
authorized until the supervisor accepts the L1.a boundary. Golden references are
evaluation-only; candidate runtime inputs must later pass the full-chain D8 audit.

L1.b runtime input chain: deployed blind ASR segments → production endpoint planner →
production WeSpeaker evidence. Golden truth enters only after an arm returns decisions.
