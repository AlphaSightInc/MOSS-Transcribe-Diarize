> Historical report, copied from `/tmp/moss-host-recovery/incident-status.md` (MacStudio-local source, not in repo). Only reference annotations changed; results and original decisions are preserved. This is not current host status. Uncopied artifacts remain local.

# Recovery paused 2026-09-12

All timestamps EDT. Keepalive disabled 04:43:58; PID 5740 stopped. WSL shutdown exit 0; 04:44:22 no vmmemWSL/wslhost, unrelated vmmem instances remained. Move retry 04:44:46 failed WSL_E_DISTRO_NOT_STOPPED, exit -1. No further move or reboot. Keepalive re-enabled and started 04:46:01, enabled=true/running; Ubuntu Running, TimeMachineServer Stopped.

04:46:31 read-only: moss-vllm active PID 298 (observed only, not validated baseline); moss-web inactive; moss-live-web active PID 305. Phase-1 NOT restored or verified. GPU 6232/16376 MiB, utilization 5%; compute PIDs 92/1181 reported names unavailable.

Keepalive script runs only a persistent shell with stat /mnt/d fallback /mnt/c every 45 s; it does not directly launch GPU inference. No MinerU GPU attribution established.

No pruning. Before any attempt deletion, copy round 10/11/12 bundles to Mac result/evidence.tar and verify. Preserve round 12 and round 13 restored-20260912T082343Z attempts. Round13 not rerun.

## Final single-session attempt
04:49:33 EDT keepalive disabled, process 103944 stopped. No local remote.py/poll.sh process found; no WSL-starting tool call during script. Shutdown exit 0 at 04:49:34. By 04:49:58 Ubuntu Running again, vmmemWSL PID 16588; move failed WSL_E_DISTRO_NOT_STOPPED exit -1. Post-failure inventory has WslService and wslhost but no wsl.exe caller; restarter not identified. All enumerated WSL scheduled tasks disabled. Stopped per instruction; keepalive remains disabled. No recovery/pruning or further retry. See `/tmp/moss-host-recovery/final-move-readable.log` — MacStudio-local (not in repo).

Product restored and pruning completed; supersedes prior outage status. Baseline PID293. See `/tmp/moss-host-recovery/recovery-report.md` — MacStudio-local (not in repo) and `/tmp/moss-host-recovery/final-product.txt` — MacStudio-local (not in repo). Keepalive enabled/running04:56:41. Watchdog/GPU sharing identified read-only; no further move.

Sparse operation refused E_INVALIDARG due corruption warning; no override/fstrim/Round13. Both tasks enabled/running; product verified05:03:39; current vLLM baseline320. See [sparse result](host-sparse-result-20260912.md).

2026-09-12 07:39 EDT: Move succeeded; round13 retry 73236fcd completed restored. vLLM292 unchanged; both MinerU tasks running; tailnet200. Handoff NOT met: browser regression both layers +2 Python failures beyond3approved quality exceptions. Final report `/tmp/moss-round13-retry-stage/result/report.md` — MacStudio-local (not in repo). No further run authorized.

2026-09-12 08:46 EDT: Durable hosts user prerequisite installed for both web units; controlled WSL reboot passed. MinerU tasks disabled08:44:02, reenabled08:44:32. NEW vLLM baseline324, NRestarts0, models200, both Phase1 views open/zero, tailnet200. Batch unit previouslydisabled, manuallystarted (enablement unchanged). Doc pushed private auto-mvp-0911 576638bb. No round14.
