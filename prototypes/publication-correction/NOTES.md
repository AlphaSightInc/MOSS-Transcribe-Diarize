# Publication/correction prototype

## Contract

- **Question:** can abort wait for its last inference reader, and can a settled recording reassign exactly one persisted passage without changing words or enrolling a voiceprint?
- **Minimum state:** runtime reader/owner state; one scratch SQLite meeting with stable segment IDs; terminal status; recording-local speaker attribution.
- **Invariants:** no owner release while a reader is in flight; release immediately after the last reader; preserve terminal journal; reject active edits; mutate only selected segments; preserve words; expose unresolved settled speech as `Speaker uncertain` and `Needs review`; create no voiceprint.
- **Assumptions/unknowns:** persisted segment IDs are the existing stable passage identity. Physical microphone/AEC behavior is intentionally unmeasured here.
- **Falsifier:** retained bytes become zero during the blocked decoder, identity owners remain after it exits, active passage edit succeeds, terminal passage edit fails, unrelated segments/words change, or reopened uncertainty is hidden.
- **Tool decision:** one deterministic command drives the real runtime and FastAPI/SQLite seams. No decoder/GPU/network call is needed. A failure blocks production implementation until its cause is isolated.

Run from the checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python prototypes/publication-correction/probe.py
```

## Base falsification

`REJECT CURRENT DESIGN` on the base candidate (`b4e8e52c`), host semantic SQLite 3.50.4 override only; production's exact 3.53.4 guard was unchanged.

- Blocked canonical reader retained 4,000 bytes before abort, but 0 bytes immediately after abort while the reader was still blocked. Tape release was premature.
- After the reader exited, identity release calls were 0. The failure path retained identity owners.
- Event order ended `canonical_started`, `session_aborted`, `session_tape_released`; no canonical result was published, so the journal remained truthful.
- Active and terminal passage endpoints both returned 404. The existing interface cannot express passage correction.
- Reopened settled speakers were `S01`, `S01`, `S00`; no `needs_review` field existed. All three word strings were preserved. Voiceprints remained empty.

Diagnosis: `_fail` releases tape unconditionally before scheduler `finally`; neither canonical/refinement completion releases finalized identity after a terminal fence. Persistence exposes whole-speaker naming only. The smallest repair is deferred terminal-owner cleanup at the existing scheduler completion seams plus one atomic terminal-only segment-ID correction operation and derived saved review projection.

## Implemented verdict

`PASS` on the repaired checkout using the same one-command production-seam probe.

- Abort retained all 4,000 tape bytes while the canonical reader was blocked. Identity release calls and tape release both remained zero until that last reader exited; afterwards identity release was exactly 1 and retained bytes were 0.
- The terminal journal stayed ordered and truthful: `canonical_started`, `session_aborted`, then `session_tape_released`; no canonical result was published after the terminal fence.
- An active meeting rejected passage correction with HTTP 409. A completed meeting accepted one exact segment-ID reassignment with HTTP 200, preserved all word strings, reopened with `Speaker uncertain` plus `needs_review: true`, and created no voiceprint.
- Producer-backed regressions cover persisted `S00` and the legacy transcript fallback `UNKNOWN`. Both project to the same uncertain saved state, remain reviewable when a different passage is edited, and cannot be used as an existing-person target.
- A closed session whose terminal finalizer is still running keeps `Identity provisional` and exposes no correction control. The terminal refresh hydrates the saved notice, retained words, and `Needs review` without a manual reopen; backend status remains the final fence.
- The isolated browser stub performed a real UI/API/storage round trip: one merged selected passage changed from Alex to Blair, transcript version advanced 1→2, reload/reopen retained Blair and the untouched uncertain passage, all five export actions remained available, browser errors/console were empty, and the voiceprint table stayed empty. No capture, microphone, decoder, GPU, or external network was used.

Machine-readable measurements are in `results.json`. Physical capture remains for the attended guide; this prototype makes no microphone, acoustic quality, or deployment claim.
