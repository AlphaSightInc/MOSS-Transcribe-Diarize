# PRD — x5-auth-residual

## Goal

The orchestrator already fixed three findings on `dev` — the reserved-`device_id` privilege
escalation, whitespace-only token acceptance, and the missing token-file permission check. Merge
`dev` in first and build on them; do not re-implement or revert them.

**What remains:**

**1. Operator revocation of the shared principal silently resurrects on restart.**
`live_auth.py:317-335` + `:434` + `:188-189`: `revoke_device(loopback, "shared-token")` returns a
successful `RevocationResult` and kills the token in-process — but the synthetic principal is
excluded from `_persist()` and re-armed unconditionally on the next start. An operator responding
to a leaked shared token believes they revoked it; they did not. That is the worst kind of
security defect: one that reports success. Make revocation durable, or make the call refuse
loudly so the operator learns the truth.

**2. The constant-time test measures nothing and is brittle.** `tests/test_live_auth.py:57-81`
patches `live_auth.hmac.compare_digest` — which **is** the stdlib module, so it mutates
`hmac.compare_digest` process-wide inside the block — and then pins an exact three-element
`call_args_list`. It does bind the feature (swap to `==` and it fails), so it is not
stub-satisfiable, just fragile and unable to detect an actual timing leak. Replace it with
something that tests the property rather than the mock.

**3. Padded tokens are preserved verbatim** including padding — a silent mismatch source. The
orchestrator's fix strips the *file* read; check the comparison path end to end.

**Verify, do not assume:** the orchestrator's three fixes were tested but not adversarially
reviewed. Probe them yourself through the real routes, including the reverse direction of the
reserved-id fix (a device legitimately paired *before* the fix landed, still on disk).

**Gate:** `.venv/bin/pytest -q tests/test_live_auth.py tests/test_live_api.py
tests/test_live_service_deployment.py tests/test_speaker_identity_provider.py`, plus a committed
probe for revocation durability across a restart, and one confirming the reserved-id and
whitespace fixes hold on the real wire (uvicorn, not just TestClient — ASGI and h11 disagreed on
the single-space case, so that gap is load-bearing).


## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py x5-auth-residual` before every
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
`evidence/phase1/x5-auth-residual/` with their probes committed · an issue-style summary in
`progress.txt` stating criterion-by-criterion what proves it and what is not covered.
