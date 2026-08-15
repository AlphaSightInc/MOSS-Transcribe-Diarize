# PRD — x4-journal-mode

## Goal

The journal's four target gaps are genuinely fixed and were reproduced end-to-end — torn-tail
recovery, named refusals, `vector_journal_failed` coverage, and provisional distinguishability.
Keep all of it. What remains is a real privacy hole and three correctness gaps.

**1. HIGH — file mode is enforced only at create.** `live_vector_journal.py:104` passes `0o600` to
`os.open`, which is **ignored for a file that already exists**, and nothing ever `chmod`s. A
pre-existing `0644` journal stays world-readable forever. Same at `:57`: `mkdir(mode=0o700,
exist_ok=True)` leaves an existing `0777` directory alone, and `parents=True` creates intermediate
dirs at umask-masked `0775`. This is **biometric data**, and it disproves the ticket's own
"0600/0700" criterion. Fix the leaf file, the leaf dir, and refuse (or repair) a loose ancestor.
The only permission test asserts `0o600` on a *freshly created* file, so it structurally cannot
catch this.

**2. The new Protocol fields are unvalidated, and a missing one destroys the whole batch.**
`_observation_refusal` validates centroid, `sample_seconds`, `embedder_id`, `embedder_state_sha`
— but not `exemplar_count`/`provisional`: `exemplar_count=-5, provisional="yes"` journals
verbatim. Worse, an observation lacking the new attributes raises `AttributeError` at `:86`,
caught upstream as `vector_journal_failed`, **losing every other speaker's row in that session** —
the exact inverse of this ticket's by-name refusal policy. `LiveVectorJournalObservation` is a
structural Protocol and the plumbing is `getattr` duck-typing, so a second provider not updated in
lockstep turns a 4-speaker meeting into zero rows.

**3. No reader contract exists.** The fix deliberately leaves unparseable forensic lines in the
file, and the recovery guard sits inside `if rows:` so a refusal-only session leaves a torn tail
unterminated; a truncation between `fstat` and `read` writes a leading blank line. All harmless
**only if** the reader skips blank and malformed lines — and nothing in the tree documents or
tests that. Write the contract down and test it. This is the item most likely to become a Phase 2
outage.

**4. `exemplar_count` does not mean what a consumer will assume.** It is the *current bank size*,
capped at 10 with shortest-first eviction: 200 s of admitted speech journals
`exemplar_count=10, sample_seconds=50.0`. Defensible as centroid provenance — but say so, and pin
it with a test under eviction. Also `provisional` is 100% redundant with `exemplar_count == 0`
among written rows; keep it only if you document why.

**Gate:** `.venv/bin/pytest -q tests/test_live_service_runtime.py tests/test_live_api.py` plus
committed probes for a pre-existing loose-mode file and directory, a missing Protocol attribute
declining by name without losing the batch, and a reader-contract test over a file containing a
forensic line.


## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py x4-journal-mode` before every
iteration: prerequisites, file ownership, banned patterns, and any evidence artifact citing a
probe not in the tree. You may only modify the paths this ticket owns
(`scripts/afk-guardrails/ownership.json`), plus your own loop dir, `evidence/phase1/`, `docs/`,
`tests/`. If you need a file you do not own, say so on the issue — do not edit it.

## Rules that come from real failures on this repo

1. **Do not certify yourself.** Emit `<promise>COMPLETE</promise>` only when the gate below
   passes with raw artifacts behind every claim. A separate reviewer reads them. Last round's
   honest blocked-stops were correct behaviour; false completions are the failure being fixed.
2. **If a test would pass with the feature deleted, it is not a test.** Real examples caught
   here: an assertion that sequence numbers are contiguous when the code makes them contiguous
   by construction; `code in FROZEN_SET` where the parametrize list *is* that set; a fairness
   "measurement" with zero decode cost.
3. **Build the thing, then measure it.** Two tickets shipped evidence scaffolding and no
   deliverable.
4. **Every artifact names a committed, re-runnable probe.** Three artifacts citing deleted
   probes were quarantined today; preflight now fails on this.
5. **Say exactly what you ran** and what your tests do *not* cover.

## You do NOT merge

Work only on your branch. Do not push to `dev`, do not take the merge lock. When your gate
passes, stop and report. The orchestrator reviews, then reconciles. You may
`git merge --no-edit dev` *into* your branch and must validate on that merged result.

## Definition of done

Gate passes · validation green after merging `dev` in · raw artifacts under
`evidence/phase1/x4-journal-mode/` with their probes committed · an issue-style summary in
`progress.txt` stating criterion-by-criterion what proves it and what is not covered.
