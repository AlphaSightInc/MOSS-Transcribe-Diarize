# Local deployment

## Canonical topology

One product process serves HTTPS on port **7861** and owns the Account SQLite database,
File work root, Meeting audio archive, browser Live capture, and mode-0600 control socket.
`moss-vllm.service` remains a loopback inference dependency on port 8000. Port 7860 must not
listen.

```text
browser -- HTTPS :7861 --> mtd-phase2-web -- HTTP loopback :8000 --> vLLM
                              |
                              +-- SQLite Account database
                              +-- owner-partitioned Meeting MP3 archive
                              +-- transient file-work root
                              +-- mode-0600 Unix control socket <-- mtd-admin
```

## Ext4 host profiles

Create `%h/.config/moss-transcribe-diarize/moss-account.env` from
`ops/moss-account.env.example` and `%h/.config/moss-transcribe-diarize/vllm.env` from
`ops/moss-vllm.env.example`. Both files live on the Linux ext4 filesystem, are mode `0600`,
and replace every placeholder. Required Account facts are:

- Google client ID and a file containing the Google client secret;
- a file containing the OAuth cookie secret;
- a trusted TLS certificate and private key;
- the reviewed Live provider manifest and a positive helper lease;
- absolute Account database, control socket, File work, and Meeting audio paths.

The server never stores Google passwords. Browser authority is the opaque Sign-in session
cookie; the host-local admin command is authorized by the Unix socket filesystem mode.

## Stage without activating

```bash
ops/install-wsl.sh
MOSS_CANDIDATE_WHEEL=/absolute/path/to/reviewed.whl ops/stage-account-candidate.sh
```

Staging creates an immutable Account release, exact SQLite 3.53.4 runtime, detached candidate
checkout, and mode-0600 candidate manifest. It does **not** change the live checkout,
`account-current`, either systemd unit, or the shared GPU/vLLM environment.

Issue #22 rehearses cutover only in an isolated root. Issue #23 owns the attended production
sequence: Phase-1 creation quiesce, drain-to-zero, one snapshot, atomic `account-current`
activation, web-unit installation, same-SHA proof, canary, and whole rollback. The staged release
owns the command:

```bash
/absolute/staged/release/bin/mtd-phase2-cutover run \
  --profile /absolute/private/moss-cutover.json \
  --attempt /absolute/new/attempt \
  --terminal restored

/absolute/staged/release/bin/mtd-phase2-cutover run \
  --profile /absolute/private/moss-cutover.json \
  --attempt /absolute/new/attempt \
  --terminal preadmission

/absolute/staged/release/bin/mtd-phase2-cutover restore \
  --attempt /absolute/incomplete/attempt
```

`restored` runs the complete same-SHA Wave-1 qualification and then proves whole rollback without
running the attended browser collector; G7 remains `UNCLAIMED`. `preadmission` additionally
requires the command's own attended headful-Chrome
collector: real microphone plus meeting-tab shared audio, then real microphone plus entire-screen
System Audio. It seals content-free source/meter/frame/speaker/Stop/audio observations and returns
`G7 PASS`; absent or synthetic evidence restores Phase 1. There is no admit, resume, retry, skip, or
force command.
Copy `ops/moss-cutover-profile.example.json` to an ext4 mode-`0600` path and replace every
placeholder before either forward command.

Only after that activation boundary may the service installer run:

```bash
ops/install-services.sh --dry-run
ops/install-services.sh
```

The installer fails closed unless both ext4 profiles are mode `0600` and `account-current`
resolves to a release containing all four reviewed launchers. It writes only
`moss-vllm.service` and `moss-web.service`; `systemctl start` does not restart an already-running
vLLM process. Issue #23 must preserve the vLLM PID, arguments, and active timestamp while
activating only the Account web runtime.

Windows WSL forwarding exposes only TLS port 7861:

```powershell
& 'D:\Coding\MOSS-Transcribe-Diarize\ops\configure-windows-network.ps1'
```

## Operator checks

```bash
systemctl --user status moss-vllm.service moss-web.service
journalctl --user -u moss-web.service -n 100 --no-pager
mtd-admin --socket "$MOSS_PHASE2_CONTROL_SOCKET" status
```

`ops/smoke-test.ps1` checks vLLM, the signed-out TLS root, and that port 7860 is closed. A
smoke test is not release qualification; Issue #22 owns the one-command Wave-1 evidence and
Issue #23 owns attended cutover.

## Rollback boundary

Rollback restores the prior `account-current` pointer and unit/profile bytes, then restarts only
the Account web process during the attended operation. The shared GPU/vLLM environment and
running process remain untouched. The Account database and Meeting archive are forward-only
product data and are not deleted by source rollback.

The sealed Phase-1 roots are recovery evidence, not routinely rewritten rollback targets. Restore
preserves every present explicit old-image root, reconstructs only a missing root, and always restores
the automatically captured unit/profile/pointer targets. Replay stops both web units before applying
snapshot bytes. `SAFE_STOPPED` is reported only after the creation marker and both unit/listener views
are verified; journal or stop-state uncertainty remains an explicit nonterminal error.
