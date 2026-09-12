> Historical report, copied from `/tmp/moss-host-recovery/sparse-result.md` (MacStudio-local source, not in repo). Only reference annotations changed; results and original decisions are preserved. This is not current host status. Uncopied artifacts remain local.

# Sparse maintenance result — 2026-09-12

05:02:02 EDT: both MinerU tasks disabled/stopped in one PowerShell session. WSL shutdown succeeded; four five-second stopped-state checks passed with no vmmemWSL. Other non-WSL vmmem instances not stopped.
05:02:26: wsl --manage Ubuntu --set-sparse true failed E_INVALIDARG, exit -1. Exact output: "Sparse VHD support is currently disabled due to potential data corruption." WSL requests --allow-unsafe. That override was NOT used. No fstrim ran and no trimmed-byte result exists.
05:02:28: finally block re-enabled and started both tasks, both enabled/running.
VHDX logical file size before/after612482678784 bytes (unchanged). C free before9607491584 bytes; after9607467008 bytes. No reclamation. Below10000000000 bytes, so Round13 was NOT built/staged/run. Cutover guard was not invoked or overridden; no guard pre-flight output exists for a new run.
05:03:39: vLLM models endpoint ready; PID320, ActiveEnterTimestampMonotonic1934371. Baseline saved on host ~/.local/state/moss-transcribe-diarize/host-recovery-baseline.json. Batch web had not auto-started; explicitly started it. Both Phase1 runtime views open with zero work; Mac canonical tailnet HTTP200 with configured Phase1 CA. Completed prior restore evidence left intact.

Maintenance script from private/auto-mvp-0911 head3712ae85 was copied to D:\wsl\moss-maintenance-3712ae85-parse-only.ps1 and parsed using System.Management.Automation.Language.Parser.ParseFile. Zero syntax errors. Script NOT executed.

MinerU idle evidence: three15-second-spaced samples, stable13583MiB combined GPU residency, GPUutilization0%, same MinerU enginePID93 and MOSS engine1096. MinerU startup logs show model2.1641GiB + KVcache3.07GiB + graphs0.27GiB =5.5041GiB before CUDA/other overhead. Thus roughly5.5GiB plus overhead resident; exact per-process total unavailable under NVIDIA WSL (N/A). Resident model demonstrated over short idle sample; burst workload behavior and effect on past gates unmeasured. MinerU unchanged.
