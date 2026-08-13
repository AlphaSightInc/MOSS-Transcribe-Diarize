---
id: T-11
map: map-001-phase1-chrome-client
title: Phase 1 acceptance gates and the Gate 2 end-to-end canary
type: grilling
status: closed
assignee: claude
blocked_by: [T-01, T-04, T-05, T-06, T-07, T-09]
---

## Question

What must be true to call Phase 1 done? This is the spec's gate section — the thing the AFK
loop's Reviewer role checks against, and the last ticket on the map.

Resolve:

1. **Gate 2 — the canary that has never run.** Real Chrome audio → 4070 inference → diarized
   transcript → browser rendering is still unproved; every existing proof used either a local
   stub or synthetic frames. Define the run precisely: verify `/api/live/descriptor` on
   `:7861`, establish the same-origin TLS exception, play a known **two-speaker** fixture in
   the selected tab, send both lanes for 30–60 s, verify frame ACKs, exact sample counts,
   transcript text, generic speaker ids, and browser rendering. Then prove a **second
   simultaneous browser receives only its own** marker/transcript. Stop both sessions cleanly.
   Record p50/p95 commit-to-render latency, dropped/discontinuous frames, 429s, GPU memory,
   GPU utilization, queue depth. **Track presence alone is not completion.**
2. **Latency budget as a number.** What p95 commit-to-render is acceptable, decided before
   measuring, including the adaptive poller's contribution.
3. **Isolation proof under the Phase 1 auth posture.** Question 1 above assumes cross-client
   isolation holds — but T-01 may rule that a shared token means a single trust domain, in
   which case the historical `403` cross-read result **cannot** be an acceptance criterion.
   Restate the isolation gate to match whatever T-01 decided. Do not carry forward a criterion
   the chosen posture makes unsatisfiable.
4. **Concurrency gate.** From T-04's measured bound: N concurrent sessions sustained for how
   long, at what fairness, with what backpressure behaviour.
5. **Fidelity gate.** From T-10, in whatever form that ticket settled on.
6. **Mode coverage.** Live (both lanes) and file mode both working through the one UI, plus
   live-transcript export per T-08.
7. **Failure-path gates.** Denied microphone permission; a surface picked without share-audio
   (preflight must fail, not silently produce an empty lane); one lane dying mid-session;
   429 backpressure; a terminal 409; reload mid-capture (see the map's *Not yet specified*).
8. **What is explicitly NOT gated in Phase 1** — Windows Chrome (Gate 4), Safari, trusted
   certificates, and every Phase 2 subsystem. Write the exclusions down so a reviewer does not
   invent them.
9. **Evidence form.** Where the canary's raw artifacts land, and how the ruling is archived at
   ruling time per operator practice.

Do not accept a controller's or builder's claim that a gate passed. Re-run it from raw
artifacts and check its **scope** — a rail satisfiable by stub evidence has been shipped in
this project before.

Ground truth: `docs/research-chrome-capture-mvp-2026-08-03.md` §"Gate 2";
control plane's `roles/REVIEWER.md`, `context/VALIDATION_COMMANDS.md`, `POLICY.md`
(at `/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize`).

## Resolution (2026-08-13) — ruled by the supervisor on the operator's behalf

The operator delegated overnight decision authority. This ticket is resolved in
**`docs/phase1-afk-charter.md` §6** — acceptance gates G1–G10 + the attended checklist in §7.

It lives there rather than here because it is **binding on the AFK fleet**: every ralph-afk agent
reads that charter as its contract, and a decision split between two documents would drift. The
charter is committed to `dev` before any worktree is created, so all six agents see the same text.

Do not re-litigate. If new evidence contradicts it, bring numbers and update the charter in the
same change.
