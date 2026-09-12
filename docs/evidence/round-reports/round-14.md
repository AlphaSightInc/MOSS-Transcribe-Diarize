# Round 14

Sanitized archival copy, reviewed 2026-09-12: six corpus identifiers replaced consistently by neutral case numbers; measurements and verdicts unchanged. Original `/tmp/moss-round14-stage/result/report.md` is MacStudio-local (not in repo). Companion links are local-path annotations; no raw bundle, transcript, audio, screenshot or credential was copied.

**Phase-1 restored; handoff NOT met.** All 18 deterministic commands passed and all 48 main quality/capacity/overload sessions finalized. Remaining blockers beyond the three approved quality exceptions: account-product export `AttributeError` in both layers, and pre-admission `one_item_failure_isolated=false`.

Candidate **057a547c297dc34f7199154805861cb56d8a72df**. Fresh bundle clone of the immediately pulled private/auto-mvp-0911 head; canonical identity written before wheel build. Automated provider manifest revision verified equal to candidate before repointing.

Attempt: `/home/devcontainers/.local/state/moss-transcribe-diarize/cutover-attempts/restored-20260912T125402Z`. One detached `--terminal restored` run. Result: `{'admitted': False, 'attempt': '/home/devcontainers/.local/state/moss-transcribe-diarize/cutover-attempts/restored-20260912T125402Z', 'candidate_sha': '057a547c297dc34f7199154805861cb56d8a72df', 'error': 'RuntimeError', 'error_message': 'same-SHA three-wave qualification failed', 'g7': 'UNCLAIMED', 'schema': 'moss-phase2-cutover-result.v1', 'terminal': 'restored'}`. No admission or attended preadmission. G7 unclaimed.

## F1 — counts

| Layer | Collected | Passed | Failed | Unmeasured |
|---|---:|---:|---:|---:|
| Deterministic commands | 18 | 18 | 0 | 0 |
| deployed predicates | 19 | 17 | 2 | 0 |
| pre_admission predicates | 17 | 14 | 3 | 0 |

python test denominators: `{"collected": 1642, "executed": 1640, "failed": 0, "passed": 1640, "skipped": 2, "unmeasured": 0}`.

frontend-test test denominators: `{"collected": 204, "executed": 204, "failed": 0, "passed": 204, "skipped": 0, "unmeasured": 0}`.

## F2 — failures and browser evidence


**deployed / quality_corpus**

Retained message: `No collector exception; evaluator rejected observed values`.
- `deployed:G4:quality_corpus:failed`
- `deployed:G4:quality_corpus:reported diarization_error_rate=0.16263575 exceeds maximum 0.16143`
- `deployed:G4:quality_corpus:reported matched_speaker_accuracy=0.91133325 is below minimum 0.911512`
- `deployed:G4:quality_corpus:reported reference_speech_der=0.135679583333 exceeds maximum 0.134804`

**deployed / account_product_regression**

Retained message: `AttributeError`.
- `deployed:G10:account_product_regression:failed`

**pre_admission / meeting_modes_history_restart**

Retained message: `No collector exception; evaluator rejected observed values`.
- `pre_admission:G3:meeting_modes_history_restart:failed`

**pre_admission / quality_corpus**

Retained message: `No collector exception; evaluator rejected observed values`.
- `pre_admission:G4:quality_corpus:failed`
- `pre_admission:G4:quality_corpus:reported diarization_error_rate=0.162618333333 exceeds maximum 0.16143`
- `pre_admission:G4:quality_corpus:reported matched_speaker_accuracy=0.911188083333 is below minimum 0.911512`
- `pre_admission:G4:quality_corpus:reported reference_speech_der=0.135663583333 exceeds maximum 0.134804`

**pre_admission / account_product_regression**

Retained message: `AttributeError`.
- `pre_admission:G10:account_product_regression:failed`

## F3 — quality macros and approved band

Strict bounds remain unchanged. Exception means within the pre-approved **5% relative** band, not a strict gate pass. Speaker metrics use the settled surface.

| Metric | Strict bound | 5% limit | Deployed | pre_admission |
|---|---:|---:|---|---|
| final_wer | ≤0.095074000 | 0.099827700 | 0.091705333 **strict** | 0.091705333 **strict** |
| immediate_wer | ≤0.166655000 | 0.174987750 | 0.164927167 **strict** | 0.165072333 **strict** |
| settled_wer | ≤0.140442000 | 0.147464100 | 0.135672000 **strict** | 0.135817167 **strict** |
| diarization_error_rate | ≤0.161430000 | 0.169501500 | 0.162635750 **exception** | 0.162618333 **exception** |
| reference_speech_der | ≤0.134804000 | 0.141544200 | 0.135679583 **exception** | 0.135663583 **exception** |
| recall | ≥0.929636000 | 0.883154200 | 0.930956500 **strict** | 0.930811250 **strict** |
| matched_speaker_accuracy | ≥0.911512000 | 0.865936400 | 0.911333250 **exception** | 0.911188083 **exception** |
| time_speaker_attribution | ≥0.876970000 | 0.833121500 | 0.877720667 **strict** | 0.877703250 **strict** |

### Per-case values

Per-case observations, not separate gate verdicts. Two passes per corpus case. CSV: `/tmp/moss-round14-stage/result/quality-per-case.csv` — MacStudio-local (not in repo).

| Layer / pass / case | Final WER | Immediate WER | Settled WER | DER | Ref-speech DER | Recall | Matched accuracy | Time attribution |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deployed / 1 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| deployed / 1 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| deployed / 1 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| deployed / 1 / case-04 | 0.126177 | 0.131827 | 0.131827 | 0.097444 | 0.084179 | 0.941620 | 0.941620 | 0.895525 |
| deployed / 1 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.116362 | 0.104469 | 0.949477 | 0.909408 | 0.911838 |
| deployed / 1 / case-06 | 0.053398 | 0.140777 | 0.140777 | 0.419559 | 0.340241 | 0.922330 | 0.844660 | 0.801623 |
| deployed / 2 / case-06 | 0.053398 | 0.135922 | 0.135922 | 0.420216 | 0.340985 | 0.922330 | 0.844660 | 0.802905 |
| deployed / 2 / case-05 | 0.069686 | 0.106272 | 0.088850 | 0.115580 | 0.103761 | 0.951220 | 0.911150 | 0.912756 |
| deployed / 2 / case-04 | 0.126177 | 0.133710 | 0.133710 | 0.098000 | 0.084746 | 0.937853 | 0.937853 | 0.894619 |
| deployed / 2 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| deployed / 2 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| deployed / 2 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| pre_admission / 1 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| pre_admission / 1 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| pre_admission / 1 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| pre_admission / 1 / case-04 | 0.126177 | 0.131827 | 0.131827 | 0.097222 | 0.083952 | 0.941620 | 0.941620 | 0.895694 |
| pre_admission / 1 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.116306 | 0.104410 | 0.949477 | 0.909408 | 0.911883 |
| pre_admission / 1 / case-06 | 0.053398 | 0.140777 | 0.140777 | 0.419066 | 0.339870 | 0.922330 | 0.844660 | 0.801934 |
| pre_admission / 2 / case-06 | 0.053398 | 0.135922 | 0.135922 | 0.420052 | 0.340799 | 0.922330 | 0.844660 | 0.803047 |
| pre_admission / 2 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.116362 | 0.104469 | 0.949477 | 0.909408 | 0.911838 |
| pre_admission / 2 / case-04 | 0.126177 | 0.133710 | 0.133710 | 0.097944 | 0.084689 | 0.937853 | 0.937853 | 0.894661 |
| pre_admission / 2 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| pre_admission / 2 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| pre_admission / 2 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |

## F4 — load, backpressure and draft lane

HTTP completion rates below count service-wide vLLM transcription completions during each campaign interval; they do not attribute requests to individual sessions or lanes. Draft started counts are runtime invocations. KV usage is a fraction.

| Layer / load | Finalized / sessions | Terminal failures | Draft ticks / skipped / started / published / stale / errors | Draft calls/audio s | HTTP completions/audio s | KV peak |
|---|---|---:|---|---:|---|---:|
| deployed / four_session_capacity | 4/4 | 0 | 2400 / 2286 / 114 / 114 / 0 / 0 | 0.047500 | 1495/2400 = 0.622917 | 0.277215943 (27.722%) |
| deployed / eight_session_overload | 8/8 | 0 | 960 / 959 / 1 / 1 / 0 / 0 | 0.001037 | 529/964 = 0.548755 | 0.189173111 (18.917%) |
| pre_admission / four_session_capacity | 4/4 | 0 | 2400 / 2276 / 124 / 124 / 0 / 0 | 0.051667 | 1505/2400 = 0.627083 | 0.275431291 (27.543%) |
| pre_admission / eight_session_overload | 8/8 | 0 | 960 / 959 / 1 / 1 / 0 / 0 | 0.001037 | 529/964 = 0.548755 | 0.203450327 (20.345%) |

Backpressure exact refusal, peer progress, and same-frame retry evidence: deployed: `/tmp/moss-round14-stage/result/deployed-backpressure.json` — MacStudio-local (not in repo), pre_admission: `/tmp/moss-round14-stage/result/pre_admission-backpressure.json` — MacStudio-local (not in repo).

### Per-session load outcomes

| Layer / load / ordinal | Session | Accepted / accounted s | Finalization | Draft ticks / skipped / started / published / stale |
|---|---|---|---|---|
| deployed / four_session_capacity / 1 | `m8m-f0u78TH4jtxq1jT4mU08` | 600.0 / 600.0 | final | 600 / 537 / 63 / 63 / 0 |
| deployed / four_session_capacity / 2 | `GwTYH-FBa1zkRj3uNnrT1bYz` | 600.0 / 600.0 | final | 600 / 589 / 11 / 11 / 0 |
| deployed / four_session_capacity / 3 | `GRgY0Zw0DJvKtd8tXYm_hvub` | 600.0 / 600.0 | final | 600 / 586 / 14 / 14 / 0 |
| deployed / four_session_capacity / 4 | `SJUhY00LOyiv0q6W0PUBkMWu` | 600.0 / 600.0 | final | 600 / 574 / 26 / 26 / 0 |
| deployed / eight_session_overload / 1 | `55IzYkSjd5wHfo5PIEcdj-LN` | 120.5 / 120.5 | final | 120 / 119 / 1 / 1 / 0 |
| deployed / eight_session_overload / 2 | `NfRqpuQxuTaMMB_0dOY0t79o` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 3 | `wnXUQCXNcCf15pHuo6HtfiA3` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 4 | `w4_IyTUjAuOCxFN5Abe7kvbT` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 5 | `Q2AyWyKKlcltDqaY67PNsCOA` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 6 | `OtKj-A5gKDQtF2ClMBQNa4Uv` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 7 | `ILYX8oocLazws3OTMRgXknjb` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 8 | `6sG911ToDWN1k80EIheLwTgG` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / four_session_capacity / 1 | `0-9zcMJ99_-H6prQkLK_uiX1` | 600.0 / 600.0 | final | 600 / 593 / 7 / 7 / 0 |
| pre_admission / four_session_capacity / 2 | `2me8x8l0e0M7CcKZh-kuRDTP` | 600.0 / 600.0 | final | 600 / 578 / 22 / 22 / 0 |
| pre_admission / four_session_capacity / 3 | `Kxe9-ViB9f2bdAch1w8SJiod` | 600.0 / 600.0 | final | 600 / 517 / 83 / 83 / 0 |
| pre_admission / four_session_capacity / 4 | `3tQZnbcynNIOOs6EAkN79HzO` | 600.0 / 600.0 | final | 600 / 588 / 12 / 12 / 0 |
| pre_admission / eight_session_overload / 1 | `WDdqLvJOIOXcqiainGufidbC` | 120.5 / 120.5 | final | 120 / 119 / 1 / 1 / 0 |
| pre_admission / eight_session_overload / 2 | `Gc3BcBAe_4ommcMt9K2Luhdr` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 3 | `2dWtEUud9OYrjneJvmlXGwPq` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 4 | `S7vnPaY7PX9pb3wFleKkWzgW` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 5 | `j4XttX65Q6oA4i6AlwxD_mui` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 6 | `_5uZqkt4bZg6RydMoLsyTALX` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 7 | `dfPFSfwdY_JLMU_06it45SsB` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 8 | `LyEG7fjz_7SU0UyNqWr-uCNB` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |

## F5 — terminal diagnostics and restoration

Retained load terminal failure records: 0 (supplemental/native duplicates possible). Full status-only diagnostics: `/tmp/moss-round14-stage/result/terminal-failures.json` — MacStudio-local (not in repo).

**vllm-before.txt**
```
MainPID=324
NRestarts=0
ExecMainStartTimestampMonotonic=2306978
```

**vllm-after.txt**
```
MainPID=324
NRestarts=0
ExecMainStartTimestampMonotonic=2306978
```

**phase1-after.txt**
```
MainPID=58542
Id=moss-web.service
ActiveState=active
SubState=running

MainPID=58635
Id=moss-live-web.service
ActiveState=active
SubState=running
```

**views-after.json**
```
[
  {
    "origin": "http://127.0.0.1:7860",
    "phase1_creation": {
      "state": "open",
      "entrants": 0,
      "active_jobs": 0,
      "queued_jobs": 0,
      "active_live_sessions": 0
    }
  },
  {
    "origin": "https://127.0.0.1:7861",
    "phase1_creation": {
      "state": "open",
      "entrants": 0,
      "active_jobs": 0,
      "queued_jobs": 0,
      "active_live_sessions": 0
    }
  }
]
```

**profiles-after.json**
```
{
  "moss-cutover.json": {
    "mode": "0o600"
  },
  "phase2-acceptance.json": {
    "mode": "0o600"
  },
  "account_current": null,
  "staged_env": {
    "path": "/home/devcontainers/.config/moss-transcribe-diarize/staged/moss-account.env",
    "mode": "0o600",
    "draft_lane_seconds": "1.0",
    "upstreams": [
      {
        "name": "macstudio",
        "base_url": "http://macstudio.tailnet.aisight.us:1234/v1",
        "models": [
          "qwen/qwen3.6-35b-a3b"
        ]
      },
      {
        "name": "rtx4090",
        "base_url": "http://ga0-rtx4090.tailnet.aisight.us:1235/v1",
        "models": [
          "qwen38-27b-mtp"
        ]
      }
    ]
  }
}
```

**source-status.txt**
```
(empty)
```

## F6 — handoff decision

**Handoff NOT met.** Exception set: DER, reference-speech DER, matched-speaker accuracy (exact values: `/tmp/moss-round14-stage/result/quality-exceptions.json` — MacStudio-local (not in repo)). Two non-quality blockers remain: account-product regression in both layers, and pre-admission meeting/history failure isolation.

## F7 — failure detail and custody

Both account-product failures retain exactly:
```json
{"failure_code":"AttributeError","failure_message":"AttributeError","failure_operation":"phase2_acceptance_browser.py:401:product_regression","failure_type":"AttributeError","measurement_state":"FAIL"}
```
At candidate source line 401, the code reads `item = download.value` in the export-download loop. This locates the failed operation; the retained exception does not name the missing attribute. No timeout stage/selector/URL/screenshot is retained for this non-timeout exception. Do not reuse round-13's reload-observer screenshot as round-14 evidence.

Pre-admission `meeting_modes_history_restart` collection completed without an exception, but the final evaluator rejected **`one_item_failure_isolated=false`**. It was true in deployed. Both layers retained **history_mismatches=0**, **restart_failures=0**, same_account_clients=2, all five required modes and the required submission counts. The evaluator at `phase2_acceptance.py:1958` requires failure isolation to be true; that is the differing/rejected field. This is a retained failure-isolation observation, not evidence that restart recovery failed. No runtime/evaluator changes or second qualification were attempted.

## F8 — pre-flight and restoration

Successful staging guard, verbatim:
```json
{"filesystem": "root", "free_bytes": 774361694208, "minimum_bytes": 20000000000, "status": "ok"}
{"filesystem": "windows_c", "free_bytes": 622058840064, "minimum_bytes": 10000000000, "status": "ok"}
```
Cutover guard, verbatim:
```json
{"filesystem": "root", "free_bytes": 768282873856, "minimum_bytes": 20000000000, "status": "ok"}
{"filesystem": "windows_c", "free_bytes": 621959622656, "minimum_bytes": 10000000000, "status": "ok"}
```

Before launch: both Phase-1 views open with zero work; canonical name resolved to `127.0.0.1` through the durable `moss-canonical-host.service` prerequisite. Both MinerU tasks remained enabled/running throughout this task. Fresh clone includes `681d9239` and the later summary-provider test fix `139177d6`. No dirty shared-worktree source entered the wheel; canonical identity writer ran before `uv build`. Provider descriptor revision equals the full candidate SHA. Both profiles and staged env are mode 0600, relay upstreams unchanged, draft lane `1.0`.

One packaging transport correction occurred before cutover: the first staging used shortened transfer filename `moss-round14.whl`, rejected by pip as an invalid wheel filename. Restaged identical bytes under `moss_transcribe_diarize-0.1.0-py3-none-any.whl`; successful staging then preceded the **only qualification attempt**. No product service was touched by that failed staging.

Restoration reached journal sequence **18**, `phase=restored`, admitted=false, G7=UNCLAIMED. Both Phase-1 views open with entrants/active jobs/queued jobs/active live sessions all **zero**; both web units active. Canonical tailnet origin HTTP **200** with the configured Phase-1 CA. vLLM **PID 324**, NRestarts=0, ExecMainStartTimestampMonotonic=2306978: exact before/after equality. Both MinerU tasks verified enabled/running after the run at **11:09:55 EDT**. No admission, attended preadmission, or subsequent run.

## F9 — complete outcomes and archive

Main sessions: **24/24 quality, 8/8 capacity, 16/16 overload finalized = 48/48**. All quality post-Stop surfaces are final/closed. Supplemental retained terminal failures: **0** (diagnostics: `/tmp/moss-round14-stage/result/terminal-failures.json` — MacStudio-local (not in repo)); intentional interruption probes are separate from the main finalization denominator. Additional G9 capacity: **4/4 final in each layer**, terminal_failures=0, separate from those 48.

Both overload layers retain **observed_429=true**, **per_session_backpressure_observed=true**, **peer_progress_during_backpressure=true**, **refused_frame_retry_succeeded=true**, terminal_failures=0, all eight final. Same microphone frame sequence **69** was refused then retried; peer session 2 progressed at sequence **8**. Full metadata/timestamps in the linked backpressure JSON files. All main load accepted seconds equal accounted seconds.

Highest observed vLLM `kv_cache_usage_perc`: supplementary monitor **0.28375966686496135 (28.376%)**. Highest native main-load peak: **0.277215943 (27.722%)**; G9 native peaks deployed **0.276621059**, pre-admission **0.276026175**. These are different sampling streams, not contradictory maxima. Draft invocation and skipped-tick counts plus service-wide decoder completions/audio-second are in F4; service-wide rates are not per-session request attribution.

Complete evidence bundle copied to the Mac: evidence.tar: `/tmp/moss-round14-stage/result/evidence.tar` — MacStudio-local (not in repo), **232,581,120 bytes**, **4,492 archive members**. Per-case values: 24-row CSV: `/tmp/moss-round14-stage/result/quality-per-case.csv` — MacStudio-local (not in repo), with all eight metrics and actual session identifiers. No exception outside the three approved quality metrics was waived.
