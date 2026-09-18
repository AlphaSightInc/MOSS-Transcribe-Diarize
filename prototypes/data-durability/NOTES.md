# WP31 durability prototype and measurement bench

## Contract

- **Q1 Structural question:** can an integrated reader preserve real old content and
  recover durable work through upgrade, restart and restore?
- **P1 Minimum primitives:** versioned SQLite records (content/ownership), referenced
  audio bytes (separate lifetime), process/capture lifecycle (recovery), reader version
  (interpretation). Removing any loses a distinct durability boundary.
- **I1 Invariants:** acknowledged transcript content survives; lane/label meaning is
  preserved by compatible readers; unavailable audio is truthful; refused files remain
  untouched; interrupted captures never silently resume.
- **U1 Unknowns:** nonempty real voiceprint banks, whole-host cold boot, atomic live
  DB-plus-audio snapshots, and base-version writes to per-lane meetings.
- **F1 Falsifier:** content disappears, an incompatible store is mutated, or a reader
  silently claims capabilities it cannot preserve.
- **T1 Tool decision:** copied real stores attack schema/content assumptions; browser
  downloads attack actual consumer meaning; real ASR tests extension; TERM tests
  durable recovery; WAL omission attacks backup completeness; archive 37979e53 tests
  rollback without changing branches or shared services.

## Run / custody

All writes belong to this worktree. `.wp31/` is ignored private scratch. No databases,
credentials, audio or transcript text enter retained evidence. Older originals were
copied using filesystem reads, never opened by SQLite. 13 sources are listed in
`evidence/mvpfix/wp31/prototype.json`. Extra stores: all 5 WP6 real state directories,
all 4 WP15 `real-*` directories, and 1 WP22 real directory; pytest-generated stores
were excluded. The three explicitly named stores contributed 8 + 13 + 8 meetings.
Total real population: 47 meetings. All 13 real voiceprint banks contained zero rows.

Python:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`
with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp31/tmp"` and this cwd.
The supplied launcher only overrides the local exact SQLite runtime pin; installed
runtime and counts are in `prototype.json`. All provider, protocol and policy values
remain unchanged. Private HTTPS ports 18132/18133, own decoder tunnel 18131.

One command for copied-store baseline: `python prototypes/data-durability/probe.py`.
One command per remaining drill: `python prototypes/data-durability/{journeys,recovery,rollback,preflight,wal_control}.py`
(select one filename; the brace expression is documentation, not a batch runner).
These prototype observations are absorbed as a retained measurement bench; they use
private single-run directories and refuse/refrain from silently overwriting old runs.
For regression verification without new ASR calls, use `tests/phase2/test_data_durability.py`.
Original real inputs must be available to recreate the baseline; database fixtures are
intentionally not committed. The rollback bench uses `git archive 37979e53` under
`.wp31/base`; it imports base source, with only the supplied local launcher copied in.

## Case table

| Case | Measured result | Verdict / limit |
|---|---|---|
| C1 old-store APIs | 13 stores; 47/47 history, open, exact transcript, rename, truthful audio checks | PASS |
| C1 actual browser | 47/47 words/labels and lane/legacy rendering; 235/235 downloaded exports | PASS |
| C1 extend every store | 13/13 new 8-second real-decoder meetings completed; 13/13 coexistence | PASS; 65 requests |
| C1 voiceprint bank | 13/13 empty banks unchanged | nonempty real-bank preservation UNMEASURED |
| C2 refusal | schema 1/3/999 and corrupt header: 4/4 refused, database bytes unchanged | PASS; startup-lifespan regressions added |
| C3 idle backup | 13/13 database-byte, row and audio-byte equality | PASS |
| C3 active backup | see recovery.json; ACTIVE ingress copy includes WAL and audio | single observed snapshot, no atomicity guarantee |
| C3 WAL omission | committed transcript count source=1, database-only=0, online SQLite backup=1 | database-only hot copy FALSIFIED |
| C4 TERM/restart | 2/2 committed segments; 27,693-byte playable partial MP3; new capture completed with 4 segments | PASS, same browser document |
| C5 cold path | first HTTP 3.867 s, descriptor 200 in 1.25 ms; restart 3.861 s | fresh state path with warm installed assets; no host reboot |
| C5 preflight | valid manifest admitted; missing/invalid manifest and missing asset refused | PASS, fixed codes; no provider calls |
| C6 base rollback | 8/8 reads, unchanged rows; 0/8 lane rendering, 32/40 complete exports | reduced-capability read only; JSON lanes lost |
| C6 return integrated | 8/8 lane rendering, 40/40 exports, unchanged rows | PASS |

## Interpretation / changes

No integrated store defect requiring production repair was demonstrated. The stronger
claims "database-only hot copying is lossless" and "base rollback retains lanes" are
falsified. Per COMMON's stop-on-falsification instruction, no production workaround,
migration machinery or new backup policy was invented. `docs/data-durability-upgrades.md`
records the measured operational boundaries and the existing stopped-process backup
procedure. Regression tests protect startup refusal and real copied-store preservation.
`QUALITY_BOUNDS`, lease/retention/identity/readiness values, two-Refresh sentinel and
nine-key frame protocol are unchanged. No push, merge, deployment, GitHub write or
shared-service restart occurred.

## Failed attempts / instrument corrections

- Initial exploration looked for nonexistent `phase2/store.py` and `phase2_app.py`;
  actual store/application live in `app/phase2.py`. No mutation resulted.
- Manifest probe first read `exception.code`; actual field is `exception.failure.code`.
  Corrected instrument; final `preflight.json` contains the refusal codes.
- Recovery attempt 1 preserved 2/2 committed segments and playable 30,501-byte partial
  audio, then timed out waiting for nonexistent UI phase `failed`. Product phases are
  `terminal`/`error`. Also its unauthenticated descriptor request returned 401.
- Attempt 2 bootstrapped before descriptor (200), proved same-document terminal state,
  then used nonexistent button label `Stop capture`; actual label is `Stop and finalize`.
  Continued capture during the timeout consumed extra requests. Both numeric failed
  attempts remain in `recovery-first-attempt.json` / `recovery-second-attempt.json`.
- Final attempt uses the actual phase and button contracts. Private tracebacks remain
  under `.wp31/`; no failures were deleted or silently relabelled product successes.

## Tests

Baseline: full Python 1928 passed, 4 skipped, 37 subtests, 21 warnings (159.13 s).
Full frontend: 264 passed in 28 files (2.69 s).
New durability subset: 17 passed (13 real stores + 4 refusal controls), before moving
refusal assertions from store-only to the production startup lifespan.
Final full Python: 1945 passed, 4 skipped, 37 subtests, 21 warnings (152.58 s).
Total real decoder requests: 107/200, including both failed instruments; maximum
in-flight enforced at 2. Fresh-context result belongs in VERIFY-RESULT.md.
