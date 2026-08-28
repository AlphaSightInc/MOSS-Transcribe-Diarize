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

## Host profile

Copy `ops/moss-account.env.example` to the gitignored `ops/moss-account.env` and replace every
placeholder. Required facts are:

- Google client ID and a file containing the Google client secret;
- a file containing the OAuth cookie secret;
- a trusted TLS certificate and private key;
- the reviewed Live provider manifest and a positive helper lease;
- absolute Account database, control socket, File work, and Meeting audio paths.

The server never stores Google passwords. Browser authority is the opaque Sign-in session
cookie; the host-local admin command is authorized by the Unix socket filesystem mode.

## Install without deploying a candidate

```bash
ops/install-wsl.sh
ops/install-services.sh --dry-run
ops/install-services.sh
```

The installer writes only `moss-vllm.service` and `moss-web.service`. It does not restart an
already-running changed service; attended cutover owns restart, same-SHA proof, canary, and
rollback.

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

Rollback changes the installed source/environment/unit to the previously reviewed SHA, then
restarts only during the attended operation. The Account database and Meeting archive are
forward-only product data and are not deleted by source rollback.
