# Round 15

Sanitized copy: corpus case IDs replaced with neutral case numbers; numbers and verdicts unchanged. Original and companion artifacts remain MacStudio-local. No transcript, audio, screenshots or credentials copied.

**Handoff condition NOT MET.** Deployed quality passes all eight strict bounds; pre-admission quality has only the three approved exceptions. All 48 quality/capacity/overload sessions finalized. Two deterministic commands and both G9 predicates failed. Round-14 account-product and history-isolation blockers passed in both layers.

Candidate **767965d71787ab0772c7c569ff882fc670ea540a**. Fresh bundle clone of the immediately pulled private/auto-mvp-0911 head; canonical identity written before wheel build. Automated provider manifest revision verified equal to candidate before repointing.

Attempt: `/home/devcontainers/.local/state/moss-transcribe-diarize/cutover-attempts/restored-20260912T193919Z`. One detached `--terminal restored` run. Result: `{'admitted': False, 'attempt': '/home/devcontainers/.local/state/moss-transcribe-diarize/cutover-attempts/restored-20260912T193919Z', 'candidate_sha': '767965d71787ab0772c7c569ff882fc670ea540a', 'error': 'RuntimeError', 'error_message': 'same-SHA three-wave qualification failed', 'g7': 'UNCLAIMED', 'schema': 'moss-phase2-cutover-result.v1', 'terminal': 'restored'}`. No admission or attended preadmission. G7 unclaimed.

## F1 — counts

| Layer | Collected | Passed | Failed | Unmeasured |
|---|---:|---:|---:|---:|
| Deterministic commands | 18 | 16 | 2 | 0 |
| deployed predicates | 19 | 18 | 1 | 0 |
| pre_admission predicates | 17 | 15 | 2 | 0 |

python test denominators: `{"collected": 1650, "executed": 1648, "failed": 1, "passed": 1647, "skipped": 2, "unmeasured": 0}`.

frontend-test test denominators: `{"collected": 204, "executed": 204, "failed": 0, "passed": 204, "skipped": 0, "unmeasured": 0}`.

## F2 — failures and browser evidence

- Command `python`: exit 1; stdout — `/tmp/moss-round15-stage/result/raw/python.stdout` (MacStudio-local, not in repo), stderr — `/tmp/moss-round15-stage/result/raw/python.stderr` (MacStudio-local, not in repo).
- Command `final-summary-real-cors`: exit 1; stdout — `/tmp/moss-round15-stage/result/raw/final-summary-real-cors.stdout` (MacStudio-local, not in repo), stderr — `/tmp/moss-round15-stage/result/raw/final-summary-real-cors.stderr` (MacStudio-local, not in repo).

**deployed / browser_final_summary**

Retained message: `CalledProcessError`.
- `deployed:G9:browser_final_summary:failed`

**pre_admission / quality_corpus**

Retained message: `No collector exception; evaluator rejected observed values`.
- `pre_admission:G4:quality_corpus:failed`
- `pre_admission:G4:quality_corpus:reported diarization_error_rate=0.162669083333 exceeds maximum 0.16143`
- `pre_admission:G4:quality_corpus:reported matched_speaker_accuracy=0.91133325 is below minimum 0.911512`
- `pre_admission:G4:quality_corpus:reported reference_speech_der=0.135703416667 exceeds maximum 0.134804`

**pre_admission / browser_final_summary**

Retained message: `CalledProcessError`.
- `pre_admission:G9:browser_final_summary:failed`

The Python failure is `tests/phase2/test_summary_provider_paths.py::test_real_browser_external_and_relay_paths_with_fake_upstreams`. It and `final-summary-real-cors` retain the same exception at `prototypes/client-configured-llm/final_browser_probe.py:36`, called by `run` at line 129:

```
TypeError: 'EvidenceExpectation' object does not support the asynchronous context manager protocol
```

The failing statement is `async with page.expect_response(...)` in `regenerate_summary`. G9 invokes this same subprocess (`phase2_acceptance_summary.py:274`) but retains only `CalledProcessError`, operation `subprocess.py:571:run`, exit status 1. The shared cause is a code-path inference from the two detailed deterministic tracebacks; G9 did not retain its own subprocess stderr. No selector/stage/URL/screenshot was retained for these non-timeout failures. No fix or additional run performed.

Python counts above include subtests: console output reports 1,610 passed plus 37 passed subtests, 1 failed, 2 skipped.

## F3 — quality macros and approved band

Strict bounds remain unchanged. Exception means within the pre-approved **5% relative** band, not a strict gate pass. Speaker metrics use the settled surface.

| Metric | Strict bound | 5% limit | Deployed | pre_admission |
|---|---:|---:|---|---|
| final_wer | ≤0.095074000 | 0.099827700 | 0.091705333 **strict** | 0.091705333 **strict** |
| immediate_wer | ≤0.166655000 | 0.174987750 | 0.165072333 **strict** | 0.164927167 **strict** |
| settled_wer | ≤0.140442000 | 0.147464100 | 0.135817167 **strict** | 0.135672000 **strict** |
| diarization_error_rate | ≤0.161430000 | 0.169501500 | 0.160881583 **strict** | 0.162669083 **exception** |
| reference_speech_der | ≤0.134804000 | 0.141544200 | 0.133706500 **strict** | 0.135703417 **exception** |
| recall | ≥0.929636000 | 0.883154200 | 0.930811250 **strict** | 0.930956500 **strict** |
| matched_speaker_accuracy | ≥0.911512000 | 0.865936400 | 0.913220583 **strict** | 0.911333250 **exception** |
| time_speaker_attribution | ≥0.876970000 | 0.833121500 | 0.878384667 **strict** | 0.877713167 **strict** |

### Per-case values

Per-case observations, not separate gate verdicts. Two passes per corpus case. CSV — `/tmp/moss-round15-stage/result/quality-per-case.csv` (MacStudio-local, not in repo).

| Layer / pass / case | Final WER | Immediate WER | Settled WER | DER | Ref-speech DER | Recall | Matched accuracy | Time attribution |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deployed / 1 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| deployed / 1 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889471 |
| deployed / 1 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| deployed / 1 / case-04 | 0.126177 | 0.133710 | 0.133710 | 0.098000 | 0.084746 | 0.937853 | 0.937853 | 0.894619 |
| deployed / 1 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.094967 | 0.080769 | 0.949477 | 0.933798 | 0.919838 |
| deployed / 1 / case-06 | 0.053398 | 0.140777 | 0.140777 | 0.419395 | 0.340055 | 0.922330 | 0.844660 | 0.801833 |
| deployed / 2 / case-06 | 0.053398 | 0.135922 | 0.135922 | 0.419887 | 0.340427 | 0.922330 | 0.844660 | 0.803686 |
| deployed / 2 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.116418 | 0.104528 | 0.949477 | 0.909408 | 0.911797 |
| deployed / 2 / case-04 | 0.126177 | 0.131827 | 0.131827 | 0.097444 | 0.084179 | 0.941620 | 0.941620 | 0.895525 |
| deployed / 2 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| deployed / 2 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| deployed / 2 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| pre_admission / 1 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| pre_admission / 1 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| pre_admission / 1 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| pre_admission / 1 / case-04 | 0.126177 | 0.131827 | 0.131827 | 0.097222 | 0.083952 | 0.941620 | 0.941620 | 0.895694 |
| pre_admission / 1 / case-05 | 0.069686 | 0.106272 | 0.088850 | 0.116362 | 0.104469 | 0.951220 | 0.911150 | 0.912274 |
| pre_admission / 1 / case-06 | 0.053398 | 0.140777 | 0.140777 | 0.419395 | 0.340055 | 0.922330 | 0.844660 | 0.801833 |
| pre_admission / 2 / case-06 | 0.053398 | 0.135922 | 0.135922 | 0.420052 | 0.340799 | 0.922330 | 0.844660 | 0.803047 |
| pre_admission / 2 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.116530 | 0.104646 | 0.949477 | 0.909408 | 0.911709 |
| pre_admission / 2 / case-04 | 0.126177 | 0.133710 | 0.133710 | 0.098000 | 0.084746 | 0.937853 | 0.937853 | 0.894619 |
| pre_admission / 2 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| pre_admission / 2 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| pre_admission / 2 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |

## F4 — load, backpressure and draft lane

HTTP completion rates below count service-wide vLLM transcription completions during each campaign interval; they do not attribute requests to individual sessions or lanes. Draft started counts are runtime invocations. KV usage is a fraction.

| Layer / load | Finalized / sessions | Terminal failures | Draft ticks / skipped / started / published / stale / errors | Draft calls/audio s | HTTP completions/audio s | KV peak |
|---|---|---:|---|---:|---|---:|
| deployed / four_session_capacity | 4/4 | 0 | 2400 / 2281 / 119 / 119 / 0 / 0 | 0.049583 | 1500/2400 = 0.625000 | 0.274836407 (27.484%) |
| deployed / eight_session_overload | 8/8 | 0 | 960 / 959 / 1 / 1 / 0 / 0 | 0.001037 | 529/964 = 0.548755 | 0.202855443 (20.286%) |
| pre_admission / four_session_capacity | 4/4 | 0 | 2400 / 2294 / 106 / 106 / 0 / 0 | 0.044167 | 1487/2400 = 0.619583 | 0.254015467 (25.402%) |
| pre_admission / eight_session_overload | 8/8 | 0 | 960 / 959 / 1 / 1 / 0 / 0 | 0.001037 | 529/964 = 0.548755 | 0.195716835 (19.572%) |

Backpressure exact refusal, peer progress, and same-frame retry evidence: deployed — `/tmp/moss-round15-stage/result/deployed-backpressure.json` (MacStudio-local, not in repo), pre_admission — `/tmp/moss-round15-stage/result/pre_admission-backpressure.json` (MacStudio-local, not in repo).

### Per-session load outcomes

| Layer / load / ordinal | Session | Accepted / accounted s | Finalization | Draft ticks / skipped / started / published / stale |
|---|---|---|---|---|
| deployed / four_session_capacity / 1 | `qbjfzYWyRPbCitPV-488aPz5` | 600.0 / 600.0 | final | 600 / 593 / 7 / 7 / 0 |
| deployed / four_session_capacity / 2 | `hUsWcXxe83Ba7e56Sr-DTF2n` | 600.0 / 600.0 | final | 600 / 593 / 7 / 7 / 0 |
| deployed / four_session_capacity / 3 | `4-HdICNlD9Pyg6BZt-5W0LeK` | 600.0 / 600.0 | final | 600 / 527 / 73 / 73 / 0 |
| deployed / four_session_capacity / 4 | `dkGtWQ7OuW4-Y3s9SQ05LDjq` | 600.0 / 600.0 | final | 600 / 568 / 32 / 32 / 0 |
| deployed / eight_session_overload / 1 | `8WmFeD_Q2gzRGDHRxG9HDwkF` | 120.5 / 120.5 | final | 120 / 119 / 1 / 1 / 0 |
| deployed / eight_session_overload / 2 | `iJzoHTlndBVqwN6K0zdmW9tt` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 3 | `PM36gzpBsxsSw2jXiskMxDOM` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 4 | `RIWJWaWNW2yBYXem8GM0FYvT` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 5 | `HjSsUg6MOMMBT0oYUAGE6mDZ` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 6 | `oQ7xHX6zwrJWnV0czH2DNxdj` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 7 | `w6Q43aj2o5A3lSY0kmmT0_F_` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 8 | `SKbJ3DjBFWGrdjSDFUERvc1j` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / four_session_capacity / 1 | `rm8wTUb3WLHc8W1_SfGsa39r` | 600.0 / 600.0 | final | 600 / 541 / 59 / 59 / 0 |
| pre_admission / four_session_capacity / 2 | `rXxTMirSRpdq0b2ArUQyfSBF` | 600.0 / 600.0 | final | 600 / 586 / 14 / 14 / 0 |
| pre_admission / four_session_capacity / 3 | `AxGHzpTzSjFNDxdNj1kdqWAj` | 600.0 / 600.0 | final | 600 / 588 / 12 / 12 / 0 |
| pre_admission / four_session_capacity / 4 | `4toK9lBE_1SAZFsFntML6Qwa` | 600.0 / 600.0 | final | 600 / 579 / 21 / 21 / 0 |
| pre_admission / eight_session_overload / 1 | `wmozJo2ND-YP4lnCzzK9pxsj` | 120.5 / 120.5 | final | 120 / 119 / 1 / 1 / 0 |
| pre_admission / eight_session_overload / 2 | `fzjHG5uGM8zenOLkYOTdJYl3` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 3 | `fHCfwV4CVILnVCekuAzZvg1P` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 4 | `-b5yoDNTAwPpOUXrDNh-3QNf` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 5 | `yHco4fUnq4lYSCw9MZOJ_tBI` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 6 | `DutKWFhLD0JhOOCvyniWQiiz` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 7 | `3Z0yA-M-9sUskAKV5KRbeREA` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 8 | `Y2cbmbCutPWCejijDkrJp8Tj` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |

## F5 — terminal diagnostics and restoration

Quality final surfaces: **24/24 closed/final**, plus capacity **8/8** and overload **16/16**, totaling **48/48 finalized** across both layers. No failed quality session.

Retained load terminal failure records: 0 (supplemental/native duplicates possible). Full status-only diagnostics — `/tmp/moss-round15-stage/result/terminal-failures.json` (MacStudio-local, not in repo).

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
MainPID=119899
Id=moss-web.service
ActiveState=active
SubState=running

MainPID=119992
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

## F6 — guards, archive and handoff decision

Staging guard, verbatim:
```
{"filesystem": "root", "free_bytes": 751075250176, "minimum_bytes": 20000000000, "status": "ok"}
{"filesystem": "windows_c", "free_bytes": 615624093696, "minimum_bytes": 10000000000, "status": "ok"}
```
Cutover guard, verbatim:
```
{"filesystem": "root", "free_bytes": 760303407104, "minimum_bytes": 20000000000, "status": "ok"}
{"filesystem": "windows_c", "free_bytes": 615625220096, "minimum_bytes": 10000000000, "status": "ok"}
```

Both layers prove HTTP 429 backpressure, peer progress during refusal, and successful retry of the same refused frame (sequence 69). All eight overload sessions finalized in each layer. Maximum retained native KV occupancy: **0.274836407 (27.484%)**; independent periodic monitor peak **0.273051755 (27.305%)**. Sampled peaks are not continuous maxima. No draft errors or stale completions in these load campaigns.

Post-run verification: both Phase-1 services active, both creation views open with zero work, canonical HTTPS origin **200**. vLLM before/after records byte-identical: **PID 324**, zero restarts. Both MinerU tasks enabled and running (Windows task state 4). Staged relay env and draft `1.0` preserved; env and both profiles mode **0600**. Candidate checkout clean.

Evidence bundle archived to this Mac: evidence.tar — `/tmp/moss-round15-stage/result/evidence.tar` (MacStudio-local, not in repo), **209,940,480 bytes, 4,492 tar members**, archive readable. Full per-case quality is above and in CSV — `/tmp/moss-round15-stage/result/quality-per-case.csv` (MacStudio-local, not in repo).

**Handoff NOT MET** because deterministic Python/summary and both G9 failures remain. Approved exception set applies only to pre-admission this round: DER, reference-speech DER, matched-speaker accuracy, each inside 5% relative tolerance. Deployed requires no quality exceptions. Bounds and identity policy unchanged. Restored terminal only; no admission or attended preadmission; G7 unclaimed.

Earlier requested documentation is pushed privately: `0e31e166` (round-14 handback and content-screened report), `de1398f6` (draft, unmerged PR 32 references in handback and report index). No merge performed.
