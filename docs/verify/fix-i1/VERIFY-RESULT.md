# fix-i1 verification result

**PASS.** Executed the `VERIFY.md` gates under the prescribed CPython 3.12.12
runtime with SQLite 3.53.4 and imports from this clone.

- RED: copied F1/F4 controls were exactly 2 strict xfails on `85aec978`.
- GREEN: focused controls 8 passed; neighboring File/retained suites 64 passed.
- Backend: 2,207 passed, 0 failed, 5 skipped, 2 xfailed, 37 subtests in 393.57 s.
- Frontend: 312/312; typecheck PASS; Vite build PASS, 34 modules; no asset drift.
- Scope: only `phase2_file.py` in the product diff; hunks only in the three owned methods.
- Custody: secrets gate empty; candidate clean; GPU lease `FREE`.
- Calls: decoder 0, provider 0, external network 0, tunnel 0.

## Lead fresh-context verification (2026-09-21T21:48:33Z)

**QA verdict: PASS.** Exact branch `round4/fix-i1`, HEAD
`e4386b8cb5f6e24e218ce536617de2e17a5b088d`, base
`85aec9787b817fbd413c623fc550a6395a91591b`, initially clean.

- **C1 PASS — scope.** Product diff is only
  `moss_transcribe_diarize/app/phase2_file.py`; all 10 zero-context hunks map
  inside unchanged signatures: `retained_work_owners` (`-364/+364`,
  `-366/+371`), `accept` (`-393/+403`, `-396/+407`, `-397/+416`,
  `-405/+425`), and `accept_url` (`-420/+439`, `-423/+443`, `-424/+452`,
  `-432/+461`).
- **C2 PASS — success parity.** Existing File/URL acceptance controls passed
  (focused 8/8; F1 acceptance controls 9/9). The lead scratch differential
  compared base with HEAD using deterministic identity/time: complete Meeting
  rows, every owner path and byte, returned handle type/key/snapshot, and the
  registered-handle identity were exactly equal for File and URL (2/2; 2,232
  JSON bytes).
- **C3 PASS — creation/registration faults.** Four arms (File/URL x task
  creation/registration) re-raised; coroutine bodies entered 0/4; both created
  registration tasks were cancelled and joined; all four durable outcomes
  exactly matched the retention-failure outcome (`failed`, `storage_failed`,
  `The meeting could not be saved.`); own directories removed, three sibling
  classes preserved, and RuntimeWarnings were 0.
- **C4 PASS — unreadable retained work/startup.** Real `create_phase2_app`
  lifespan reached readiness. One unreadable account and one unreadable owner
  entry each emitted exactly one content-free class-only warning; symlinks and
  non-directories remained excluded; a valid terminal sibling was reclaimed;
  unreadable and outside entries remained untouched.
- **C5 PASS — original stress controls.** The two selected controls passed 2/2
  with expected-failure markers disabled. First attempt was a harness-path
  failure (`_browser_workspace_fixtures` absent from `PYTHONPATH`), so its F1
  assertion did not run; rerun with this clone's `tests/phase2` path passed 2/2.
- **C6 PASS — literal VERIFY/full gates.** Prescribed CPython 3.12.12, SQLite
  3.53.4, import from this clone; backend 2,207 passed / 0 failed / 5 skipped /
  exactly 2 expected Jamie failures / 37 subtests in 240.76 s; frontend 312/312;
  TypeScript and Vite build clean (34 modules; no tracked asset drift).
- **C7 PASS — custody/secrets.** Required `git grep` returned no matches;
  candidate status output empty; GPU lease `FREE`; decoder/provider/network/
  tunnel calls 0/0/0/0.

Review axes: **Spec PASS**, with no missing requirement, scope creep, or wrong
behavior after the lead scratch receipts. **Standards FAIL (documentation
only):** the pre-existing result paragraph uses unexplained shorthand. Two
non-blocking judgement findings remain: duplicated lifecycle shapes in `accept`
and `accept_url`, and generic copied-control names in `probe_01.py`.
