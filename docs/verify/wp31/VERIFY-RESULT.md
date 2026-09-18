# WP31 fresh-context verification result

2026-09-18. Branch `mvpfix/wp31-data-durability`.
Tested initial SHA: `40ac0f139ee01c734df0849f4866cc8c4f971e92`.
Final tree: same product/test/harness code, verification documents relocated and results added.

## Verdict

Initial literal run: **FAIL**, one verification-document layout defect (F1).
After documentation correction: **PASS**.
Copied real-store preservation: **PASS**. No product-source repair demonstrated or made.
This is local durability verification, not deployed acceptance or a new live campaign.

## Commands and results

All commands ran in the requested WP31 worktree with:

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp31/tmp"
WP31_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git status --short --branch
git rev-parse HEAD
"$WP31_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
"$WP31_PY" prototypes/data-durability/verify_retained.py > evidence/mvpfix/wp31/fresh-retained.txt 2> .wp31/fresh-retained-errors.txt
"$WP31_PY" -m pytest -q -p no:cacheprovider --basetemp=.wp31/pytest-fresh tests > .wp31/python-fresh.txt 2>&1
npm --prefix frontend test -- --run > .wp31/frontend-fresh.txt 2>&1
git diff --check
lsof -nP -iTCP:18131 -iTCP:18132 -iTCP:18133 -sTCP:LISTEN
```

- T1: Clean initial branch and requested SHA; package resolved inside this worktree.
- T2: Retained verifier exit 0; independent copies reopened: 13 stores, 60 meetings,
  47 preserved old transcripts, 13 new meetings, 60 referenced audio files.
- T3: Initial Python exit 1: **1 failed, 1944 passed, 4 skipped, 37 subtests passed,
  21 warnings, 152.09 s**. Sole failure: `test_verify_layout_current_tree`.
- T4: Initial frontend exit 0: **264 passed / 28 files, 2.92 s**.
- T5: Initial diff check exit 0; listener check exit 1 with no listeners (expected).

Repair validation commands (distinct logs preserve the failed run):

```sh
bash scripts/check_verify_layout.sh
"$WP31_PY" -m pytest -q -p no:cacheprovider --basetemp=.wp31/pytest-fresh-final tests > .wp31/python-fresh-final.txt 2>&1
npm --prefix frontend test -- --run > .wp31/frontend-fresh-final.txt 2>&1
git diff --check
lsof -nP -iTCP:18131 -iTCP:18132 -iTCP:18133 -sTCP:LISTEN
```

Final Python exit 0: **1945 passed, 4 skipped, 21 warnings, 37 subtests passed,
149.06 s**. Final frontend exit 0: **264 passed / 28 files, 2.53 s**.
Layout guard PASS; final diff checks PASS; listener check exit 1, no listeners (expected).
Fresh runs retain both the failed initial result and the successful corrected result.

## Case table

Opened/served/rendered/exported/extended below are retained implementation observations
from `prototype.json` and `journeys.json`, not repeated live in this session.
Every row independently reopened after extension in this session; full-suite durability
cases additionally open fresh copies of all 13 idle backups and test schema refusals.

| Case / copied store | Old opened / served / rendered | Exports | New completed | Fresh reopened meetings |
|---|---:|---:|---:|---:|
| C1 codex-prelane | 8/8; 8/8; 8/8 | 40/40 | 1/1 | 9/9 |
| C1 lead-prelane | 13/13; 13/13; 13/13 | 65/65 | 1/1 | 14/14 |
| C1 lead-perlane | 8/8; 8/8; 8/8 | 40/40 | 1/1 | 9/9 |
| C1 wp6-0 | 1/1; 1/1; 1/1 | 5/5 | 1/1 | 2/2 |
| C1 wp6-1 | 2/2; 2/2; 2/2 | 10/10 | 1/1 | 3/3 |
| C1 wp6-2 | 2/2; 2/2; 2/2 | 10/10 | 1/1 | 3/3 |
| C1 wp6-3 | 4/4; 4/4; 4/4 | 20/20 | 1/1 | 5/5 |
| C1 wp6-4 | 4/4; 4/4; 4/4 | 20/20 | 1/1 | 5/5 |
| C1 wp15-0 | 1/1; 1/1; 1/1 | 5/5 | 1/1 | 2/2 |
| C1 wp15-1 | 1/1; 1/1; 1/1 | 5/5 | 1/1 | 2/2 |
| C1 wp15-2 | 1/1; 1/1; 1/1 | 5/5 | 1/1 | 2/2 |
| C1 wp15-3 | 1/1; 1/1; 1/1 | 5/5 | 1/1 | 2/2 |
| C1 wp22-0 | 1/1; 1/1; 1/1 | 5/5 | 1/1 | 2/2 |
| C1 total | 47/47 each | 235/235 | 13/13 | 60/60 |

| Case | Evidence / outcome | Boundary |
|---|---|---|
| C2 schema refusal | 1/3/999 + corrupt header: 4/4 refuse unchanged; exercised in fresh full suite | Refusal, not migration |
| C3 idle backup/restore | Retained 13/13 byte/row/audio equality; fresh full suite reopens their copies | Stopped process; DB + sidecars + complete audio root |
| C3 active backup/restore | Retained one active-ingress copy restored interrupted; transcript rows preserved; partial audio resolves | One observation; no atomic live backup guarantee |
| C3 WAL control | Retained committed transcript: source 1; DB-only 0; SQLite online backup 1 | DB-only hot-copy claim falsified; online DB backup excludes external audio |
| C4 restart mid-capture | Retained TERM/restart: 2/2 committed segments; playable 27,693-byte partial MP3; same-document new capture completed, 4 segments | No automatic capture resume; untranscribed frames not certified durable |
| C5 cold boot | Retained new-state process: first HTTP 3.867 s; descriptor 200 / 1.25 ms; restart 3.861 s | Installed warm assets; host reboot/cold caches unmeasured |
| C5 preflight | Retained valid admitted; missing/invalid manifest and missing model refused | No provider calls for these controls |
| C6 rollback | Retained integrated → base 37979e53 → integrated: unchanged rows; base 8/8 reads, 0/8 lane rendering, 32/40 exports; integrated 8/8 lanes, 40/40 exports | Base read compatibility only; lane-faithful rollback falsified |

## Defects and changes

- F1 FIXED here: root `VERIFY.md:1` violated `scripts/check_verify_layout.sh:6`,
  detected by `tests/phase2/test_tls_preparation.py:146`. Moved to
  `docs/verify/wp31/VERIFY.md:1`; result also lives in that directory. No guard relaxed.
  Earlier full-suite preflight did not certify the later-added root verification file.
- F2 Retained instrument corrections: exception field at
  `prototypes/data-durability/preflight.py:12`; authenticated descriptor at
  `prototypes/data-durability/recovery.py:28`; actual terminal/error phase at `:58`;
  actual Stop and finalize button at `:62`. Two failed recovery attempts remain retained.
- F3 No integrated data-loss defect found. Database-only active copying and lane-faithful
  base rollback were falsified claims; operational limits documented, no workaround added.

Changed this session: relocated/amended VERIFY.md; added this result; added content-free
fresh summaries under `evidence/mvpfix/wp31/`; appended fresh finding to that directory's
NOTES.md. Raw logs, copies and private data remain ignored under `.wp31/`.

## Upgrade / rollback boundaries

- B1 `docs/data-durability-upgrades.md:13`: schema version 2; optional lane metadata;
  legacy mono remains mono. Preserve refused files; never reset versions to force admission.
- B2 `docs/data-durability-upgrades.md:26`: stop owning web process, copy DB/sidecars/audio,
  restore into a fresh directory. Active copying is unqualified (`:46`).
- B3 `docs/data-durability-upgrades.md:54`: interrupted recovery preserves committed
  transcript and recoverable partial audio; Reset and explicitly start a new capture.
- B4 `docs/data-durability-upgrades.md:66`: base reader loses lanes; base writes to
  per-lane meetings unmeasured. Restoring old backup discards later work; CutoverRun.restore
  is interrupted-cutover recovery, not a post-release data rollback command.

Nonempty real voiceprint banks (all 13 were empty), host reboot/cold model cache,
shared-host autostart and base writes to per-lane meetings remain **UNMEASURED**.
Browser device input in retained live drills was simulated public speech; HTTP/ASR/storage real.
Exact SQLite runtime-pin bypass remains confined to the supplied local harness/test fixture.
Retained request accounting: **107/200**, including failed instruments; maximum 2 in flight.
This fresh session: **0/60 decoder requests**, no tunnel/server started; none needed or authorized
by VERIFY.md. No push/merge/deploy, shared-service changes or external-tree file edits.
Only deviation from literal instructions: after preserving the failure, relocate documents
to satisfy the existing layout contract and rerun full suites. Single-use retained verifier
was not rerun and no failed live measurement was overwritten.
