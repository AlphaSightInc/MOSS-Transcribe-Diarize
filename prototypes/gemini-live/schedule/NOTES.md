# P65 schedule prototype — cheaper speaker-label context (THROWAWAY)

## Contract (written before running)

**Question.** Can the Gemini canonical speaker lane send much less audio than S15/Lmax180 growing
windows (~11.6× audio re-sent per meeting-hour) while keeping live speaker accuracy good enough that
the after-Stop clean-up pass could be OFF?

**Structural question.** Cross-window speaker identity is what the ~165 s of re-sent context buys
(C1 overlap anchoring inside Gemini's own labels). Can a cheaper context carry identity?

**Minimum primitives.** Gemini window call (words, window-local labels, timestamps, usage); the
production continuity registry (C1 overlap ≥.3 s + C3 WeSpeaker link E .46 / W .60 + 2 s birth) —
the prototype registry in `continuity/registry.py` has recorded assignment parity with
`moss_transcribe_diarize/app/gemini_continuity_registry.py` (continuity/parity.py); the production
WeSpeaker ONNX; H1-exact scorer (`harness/h1_offline.py`) for accept6; `common.score` for long form.

**Arms** (cost multiplier ≈ context ÷ stride at steady state):
- A0 S15/L180 growing — baseline, cached receipts in evidence/P61 (no calls).
- A1 S30/L180 growing (6×) — every A1 window is an A0 window (cache hits); only Stop is new.
- A2 S15/L90 growing (6×) — new calls.
- A3 S30/L90 growing (3×) — every A3 window is an A2 window.
- A4 exemplar-anchored (~3–4×): each 15 s tick sends ≤5 known speakers' clean exemplar clips
  (≤6 s each, longest clean committed span, outside the recent window, 0.8 s digital silence between)
  + the latest 30 s. Gemini labels on exemplar spans become extra overlap support for the registry;
  prefix words are discarded; C1 overlap (15 s between consecutive recent windows) + C3 + 2 s birth
  as product.
- Cited, not rerun (continuity/NOTES.md): S10/L60, S15/L60, S15/L120, S20/L60, S20/L120, S20/L180.

**Corpora (public only).** accept6 (H1 #3 refs), E1 system lane (3 true), complete Bill Ackman 30 min
(2 true), long60 (43 min, 5 true).

**Metrics.** First-committed (settled) DER (H1 ruled + raw on accept6; common.score on long form);
displayed IDs; label lag p50/p90 = schedule wait + recorded API latency of the actual call (cached
windows carry their original single measurement; concurrency recorded per run); audio sent; cost/h
(a) metered input + $0.30 Live words, (b) + output text at Google's published $0.002/min of audio sent
+ $0.24/h Live output. Clean-up pass excluded (it is what "final off" removes). Parser anomalies.
A4: exemplar label consistency (split / merged / missing exemplars).

**Invariants.** Same registry thresholds as product; public audio only; key never printed; ledger lane
`P65-schedule`; content cache reused; hard cap $15 new spend incl. estimated output.

**Falsifier / decision rule.** An arm is *final-off eligible* iff accept6 settled DER ≤ .110, E1 IDs ≤ 4,
and on BOTH Bill30m and long60: IDs ≤ true+1 and DER ≤ A0 + .03. Lowest-cost eligible arm wins; if
none is eligible, that is an escalation, stated plainly.

**Tool decision.** Replaying the bench's own runner (`continuity/c4_stop.py`) isolates schedule
effects from registry/scorer changes; A4 needs a sequential call→map→commit loop because exemplar
choice depends on earlier mappings.

## Run

```
cd <worktree>; PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/schedule/run.py --arms A1 A2 A3 A4 --tiers accept6 e1 long30m long60
... run.py --summary      # table + decision rule from receipts (no calls)
```
Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P65/schedule/`.

## Results (2026-09-29; receipts `evidence/P65/schedule/`, `run.py --summary`; new spend ~$3.4 incl. estimated output)

First-committed (settled) DER, H0; accept6 = H1-exact six-case macro; long-form = common.score. Cost/h = metered input
+ $0.30 Live words (| + output at Google's $0.002/min sent + $0.24 Live output); clean-up pass excluded.

| Arm (stride/context) | Audio re-sent | accept6 | E1 IDs | Bill30m IDs / DER | long60 IDs / DER | Lag p50/p90 s (long60) | $/h |
|---|---:|---:|---:|---:|---:|---:|---:|
| A0 15/180 (current) | 11.6x | .0985 | 3 | 2 / .056 | 5/5 / .048 | 17.5 / 23.8 | 2.39 / 4.02 |
| A1 30/180 | 5.8x | .0823 | 3 | 2 / .048 | 5/5 / .043 | 25.3 / 37.1 | 1.35 / 2.28 |
| **A2 15/90** | **5.9x** | **.1014** | **3** | **2 / .053** | **5/6 / .046** | **13.3 / 19.5** | **1.36 / 2.31** |
| A3 30/90 | ~3x | .1000 | 3 | 3 / **.487** | 6/6 / **.350** | 21.1 / 33.0 | ~0.8 / ~1.3 |
| A4 exemplar-anchored 15 s (30 s recent + <=5x6 s exemplars) | 3.1x | .1303 (RTFL .589) | 3 | 2 / .060 | 4/4 / **.101** (merged 2 people) | 11.2 / 17.4 | 0.86 / 1.47 |
| A5 15/120 (re-run, cached) | 7.7x | — | — | 3 / **.510** | — | 15.0 / 21.1 (Bill) | — |

A2 repeat draw (fresh responses, `P65_DRAW=2`): Bill .0527 / 2 IDs, long60 .0459 / 5-6 IDs — identical to draw 1 because
Gemini 3.5 Transcribe is near-deterministic on identical audio; draws do not sample cross-meeting risk.

**Verdict.** A1 and A2 are final-off eligible by the rule; A2 wins on the user's priority (half the audio of A0 AND faster
labels, 13.3 s vs 17.5 s p50). A3 and A5 show identity *collapse* (a Bill/Lex swap-or-merge that persists) on the same
Gemini responses that pass at A2 and A0 — pass/fail is non-monotonic in context length, so A2's pass on two long meetings
does not prove robustness on other meetings. A4 (exemplar-anchored) is rejected (merges two long60 voices; RTFL .589).
Follow-up P4 (`../guard/`) tests a registry guard against collapse before any schedule is adopted as default with clean-up OFF.

### P5 — 60 s context (A6 S15/L60, 4x) with and without the P4 fingerprint veto (2026-09-29)
| Case | No veto DER / IDs | Veto T.46 M.20 DER / IDs |
|---|---|---|
| accept6 macro | .0956 | .0956 |
| E1 (true 3) | 5 IDs | 5 IDs |
| Bill30m (true 2) | .384 / 3 | .110 / 3 |
| long60 (true 5) | .372 / 6 | .174 / 6 |
**Verdict: 60 s rejected.** Fingerprints recover most of the swap damage but not the over-splitting from short replies that
fall outside a 45 s overlap and are too short to fingerprint (E1 5 IDs, long60 6 IDs). 90 s is the floor for the Gemini
presets; saving vs 90 s would have been only ~$0.36/h metered. Receipts: `evidence/P65/schedule/run-A6.log`,
`evidence/P65/guard/final60.json`.
