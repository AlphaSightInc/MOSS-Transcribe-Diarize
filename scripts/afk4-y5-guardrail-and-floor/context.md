# context — y5-guardrail-and-floor

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Known state (verified 2026-08-16, `dev` @ 5b20a95)

- `check_forbidden` in `preflight.py` was repaired 2026-08-16 (broadened runner regex; cited Python
  runners are compiled; `:<line>` frames and out-of-repo absolute paths ignored). Post-fix it reports
  **0 violations** on the tree. **No committed regression fixture exists** — that is your job 1.
- The repair surfaced a real finding, recorded in the ledger: T-02's auth mutation battery cites
  harnesses in deleted `/tmp` copies and in the control-plane repo, so it cannot be re-run from here.
- Queue-depth floor, measured (do not re-derive; a closed-form attempt got this wrong):
  deployed geometry floor = **1**; aggressive geometry (`hard_cap 1600`) = **25**.
  Stop tail = **1 in all 2268 geometry combinations searched**, so `live_service_runtime.py:643`
  is unreachable. Nothing is broken at the shipping config.
- `_close_open_partition` (`live_endpoint.py:155-165`) emits hard-cap spans during `observe()`.
  That is why the open partition never exceeds one hard cap.

## Candidates (ranked; re-rank as you learn)

1. Guardrail regression fixtures — five cases in the PRD, built as real files in a temp tree.
   Must fail against the pre-repair guardrail. Verify that claim by actually running it against the
   old version (`git show 4e8cae5:scripts/afk-guardrails/preflight.py`).
2. State in the test what it does not cover (parse ≠ runs).
3. Failing seam test for an unadmittable frame geometry. **Before** any guard.
4. The derived floor guard at manifest finalization: run the configured policy, count spans, compare.
5. Confirm the guard fires at config load with a message naming computed floor and configured value.

## Hard line

You own the guardrail that gates every other ticket. A change that makes preflight more permissive,
or stops it running, is the worst outcome available to you. Fixture first, always.
