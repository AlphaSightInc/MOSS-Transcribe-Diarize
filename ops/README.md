# Candidate disk guards and retention

Staging and a new cutover run check free bytes **before build or Phase-1 mutation**.
A refusal exits with `insufficient_disk_space`, filesystem, available bytes and
required bytes. It does not stop, block or restart Phase-1. Restore remains available
without the new-run check.

| Setting | Default | Meaning |
|---|---:|---|
| `MOSS_MIN_ROOT_FREE_GB` | 20 | Minimum available on `/`, including the WSL root filesystem |
| `MOSS_MIN_WINDOWS_FREE_GB` | 10 | Minimum available on Windows C: when running under WSL |
| `MOSS_RETAIN_CANDIDATES` | 2 | Recent attempts and recent completed candidate runtimes to keep |

GB is decimal (1,000,000,000 bytes). Disk thresholds must be positive; retention
must be at least one. These are operational headroom floors, not measured upper
bounds on a qualification run's total growth. Export overrides in the staging or
cutover shell. Defaults do not change identity policy or quality bounds.

On WSL, the check queries a mounted `/mnt/c`; if unavailable, it tries
`powershell.exe` with a five-second timeout. If neither works, it explicitly prints
`windows_c` / `unavailable` and still enforces the Linux floor. That fallback is
**not proof of Windows capacity**. Outside WSL, only the root check applies.

## Pruning

`ops/stage-account-candidate.sh` automatically prunes before construction and again
when the new runtime is complete. Staging holds the same host lock as cutover for
its entire build; either operation refuses if the other owns that lock.

Selection uses descending directory modification time, with name as a stable tie
break. Only direct, non-symlink directories in these families are eligible:

- `~/.local/state/moss-transcribe-diarize/cutover-attempts/`: retain the newest N,
  plus **every incomplete, unreadable or SAFE_STOPPED attempt**. Only older attempts
  whose result says `restored` or `preadmission` can be removed.
- `~/.local/share/moss-transcribe-diarize/account-runtimes/`: retain the newest N
  completed runtimes, the `account-current` target, the candidate being staged and
  runtime references in retained attempts. Abandoned hidden construction directories
  become eligible after 24 hours.
- `~/.local/share/moss-transcribe-diarize/candidate-checkouts/` and `staging/`, plus
  `~/.local/state/moss-transcribe-diarize/qualification-workspaces/`: remove entries
  older than 24 hours unless pinned by a retained runtime/attempt or the invoking
  staging checkout. Incomplete attempts with missing candidate identity suppress
  runtime/workspace pruning, rather than guessing what recovery needs.

New cutover qualification sets `MOSS_ACCEPTANCE_WORK_ROOT` to the attempt's
`measurement-workspaces/`; its qualification clone and large measurement directories
therefore share the attempt's protection and lifetime. Global `TMPDIR` is unchanged
to avoid lengthening browser Unix-socket paths. Older arbitrary `/tmp` clones and
measurements are **not swept**. Neither application databases nor model caches are
pruning targets. Symlinks and symlinked directory roots are not traversed for deletion.

Print the plan only (no wheel required, no build, no deletions):

```sh
ops/stage-account-candidate.sh --dry-run
```

If the disk check refuses before automatic pruning, the operator can first inspect
and then explicitly prune the same bounded families without starting staging:

```sh
python3 moss_transcribe_diarize/candidate_storage.py --dry-run
python3 moss_transcribe_diarize/candidate_storage.py --prune
```

Output lists each removed relative path and allocated bytes, the aggregate allocated
bytes removed (or reclaimable in dry-run), and the observed filesystem free-byte
delta. Concurrent non-MOSS writes can affect that delta; hard links can make the
allocated sum exceed reclaimed storage. **Deleting Linux files does not shrink the
WSL VHDX or necessarily free Windows C: space.** Windows recovery/compaction is a
separate operator action; these scripts never shut down WSL or compact its disk.

Local validation uses fake directory layouts and mocked free-space probes: Linux
and Windows thresholds, unavailable Windows probes, protected/current/active
survivors, read-only runtimes, symlink boundaries, lock refusal and dry-run. The
cutover regression verifies a disk refusal leaves Phase-1 running and its marker
and journal untouched. No host recovery or filesystem pruning was run to validate
this change.
