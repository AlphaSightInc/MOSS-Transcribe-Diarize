# Round 4 settlement stress verdicts

## 2026-09-22 — frozen `8d6cd287`

- Settlement failures must record exact durable terminal truth: refused-resume fallback is
  `failed/resume_failed`; successful operator interruption remains `interrupted`.
- S9 ruling: Account revocation never depends on filesystem cleanup. A committed revoke may
  leave retained work after a cleanup error; the warning names its Account and Meeting, and a
  later product boot retries removal.
