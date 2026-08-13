## Iteration 8 blocker — supervisor decision requested

The sole unchecked criterion is: **“The existing auth gate and mutation batteries still pass
unmodified.”**

I ran both historical A-025 reviewer harnesses byte-for-byte unchanged against isolated clones of
this ticket branch at `65e46b1`. Source/copy SHA-256 pairs and raw transcripts are committed under
`evidence/phase1/t2/iteration-05-auth-mutation-battery/`.

- The re-review runner passes unmutated controls U, A, C, B, S, L3, and D, then its unmutated R
  control fails because the July spike does not supply required `live_helper_lease_seconds`.
  Requirement commit `1f17def6` predates this ticket's baseline `76a86b8`.
- The original 33-row runner kills M01 through M16 (19 rows including variants), then aborts before
  applying M17 because its old view-expiry anchor has count zero. Session-lifecycle view authority
  commit `4445a49` predates this ticket's baseline.
- No mutant survived. The unchanged historical runners cannot complete on the pre-ticket baseline,
  so I cannot honestly claim 33/33.
- A repository search finds no newer repository-owned mutation runner; only the reviewer mutation
  contract and ordinary tests are tracked.

Please choose one gate interpretation:

1. Identify/provide the current authoritative mutation harness. I will run that artifact unchanged.
2. Confirm the historical A-025 runners are no longer the applicable gate and approve a rebaselined
   replacement. That changes the issue's meaning and requires supervisor authority.

I will not add unrelated backward-compatibility behavior merely to satisfy stale anchors, and I
will not rewrite a runner while claiming it passed unmodified. The other six criteria have direct
evidence on branch `afk/t2-shared-token-auth` at `28d6a56`; merge/full validation/push remain gated
until this criterion is adjudicated.
