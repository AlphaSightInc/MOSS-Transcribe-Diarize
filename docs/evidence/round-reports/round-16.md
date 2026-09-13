# Round 16

Sanitized copy: corpus case IDs replaced with neutral case numbers; all numbers and verdicts unchanged. Original `/tmp/moss-round16-stage/result/report.md` and companion artifacts remain MacStudio-local (not in repo). No transcript, audio, screenshots or credentials copied.

**Product-predicate condition met; full qualification/handoff remains blocked by a stale rehearsal manifest.** All 18 deterministic commands and all non-quality predicates pass. Only the three approved quality exceptions remain in each layer. A separate cutover rehearsal uses removed candidate 8720503f, not this candidate. Phase-1 restored safely.

Candidate **e47ab229cdbfcfe0dcb2bcfa3f1d1c9ca9f94361**. Fresh bundle clone of the immediately pulled private/auto-mvp-0911 head; canonical identity written before wheel build. Automated provider manifest revision verified equal to candidate before repointing.

Attempt: `/home/devcontainers/.local/state/moss-transcribe-diarize/cutover-attempts/restored-20260912T224626Z`. One detached `--terminal restored` run. Result: `{'admitted': False, 'attempt': '/home/devcontainers/.local/state/moss-transcribe-diarize/cutover-attempts/restored-20260912T224626Z', 'candidate_sha': 'e47ab229cdbfcfe0dcb2bcfa3f1d1c9ca9f94361', 'error': 'RuntimeError', 'error_message': 'same-SHA three-wave qualification failed', 'g7': 'UNCLAIMED', 'schema': 'moss-phase2-cutover-result.v1', 'terminal': 'restored'}`. No admission or attended preadmission. G7 unclaimed.

## F1 — counts

| Layer | Collected | Passed | Failed | Unmeasured |
|---|---:|---:|---:|---:|
| Deterministic commands | 18 | 18 | 0 | 0 |
| deployed predicates | 19 | 18 | 1 | 0 |
| pre_admission predicates | 17 | 16 | 1 | 0 |

python test denominators: `{"collected": 1656, "executed": 1654, "failed": 0, "passed": 1654, "skipped": 2, "unmeasured": 0}`.

frontend-test test denominators: `{"collected": 204, "executed": 204, "failed": 0, "passed": 204, "skipped": 0, "unmeasured": 0}`.

## F2 — failures and browser evidence


**deployed / quality_corpus**

Retained message: `No collector exception; evaluator rejected observed values`.
- `deployed:G4:quality_corpus:failed`
- `deployed:G4:quality_corpus:reported diarization_error_rate=0.162571916667 exceeds maximum 0.16143`
- `deployed:G4:quality_corpus:reported matched_speaker_accuracy=0.911502 is below minimum 0.911512`
- `deployed:G4:quality_corpus:reported reference_speech_der=0.13561775 exceeds maximum 0.134804`

**pre_admission / quality_corpus**

Retained message: `No collector exception; evaluator rejected observed values`.
- `pre_admission:G4:quality_corpus:failed`
- `pre_admission:G4:quality_corpus:reported diarization_error_rate=0.162751416667 exceeds maximum 0.16143`
- `pre_admission:G4:quality_corpus:reported matched_speaker_accuracy=0.91133325 is below minimum 0.911512`
- `pre_admission:G4:quality_corpus:reported reference_speech_der=0.135793333333 exceeds maximum 0.134804`

**Separate cutover rehearsal failure (outside the 18 deterministic commands):** `cutover_rehearsal_failed`, exit 1. Retained stderr:

```
ValueError: staged candidate release is incomplete
```

Path: `scripts/phase2-acceptance/rehearse.py:21` → `phase2_cutover_rehearsal.py:130` → `installed_candidate.py:65`. The acceptance profile's separate `cutover_rehearsal.candidate_manifest` still points to candidate **8720503f17ea703d3081cbce79e4b453be72e8eb**. Its release, checkout, four launchers and two unit paths are absent. Both measurement-layer manifests correctly point to **e47ab229**. This is a stale rehearsal configuration, not missing artifacts in the candidate that passed installed-candidate checks in both layers. I missed updating this separate field in preparation. Read-only diagnosis: `/tmp/moss-round16-stage/result/rehearsal-diagnosis.json` — MacStudio-local (not in repo). No evaluator change, profile repair or further run performed after this result.

**Round-15 regression cleared:** Python, final-summary-real-cors, and browser_final_summary all pass; G9 has all 19 checks true in both layers, including relay_path_qualified. No failed browser predicate or timeout evidence this round.

## F3 — quality macros and approved band

Strict bounds remain unchanged. Exception means within the pre-approved **5% relative** band, not a strict gate pass. Speaker metrics use the settled surface.

| Metric | Strict bound | 5% limit | Deployed | pre_admission |
|---|---:|---:|---|---|
| final_wer | ≤0.095074000 | 0.099827700 | 0.091705333 **strict** | 0.091705333 **strict** |
| immediate_wer | ≤0.166655000 | 0.174987750 | 0.164915417 **strict** | 0.164927167 **strict** |
| settled_wer | ≤0.140442000 | 0.147464100 | 0.135660250 **strict** | 0.135672000 **strict** |
| diarization_error_rate | ≤0.161430000 | 0.169501500 | 0.162571917 **exception** | 0.162751417 **exception** |
| reference_speech_der | ≤0.134804000 | 0.141544200 | 0.135617750 **exception** | 0.135793333 **exception** |
| recall | ≥0.929636000 | 0.883154200 | 0.931125167 **strict** | 0.930956500 **strict** |
| matched_speaker_accuracy | ≥0.911512000 | 0.865936400 | 0.911502000 **exception** | 0.911333250 **exception** |
| time_speaker_attribution | ≥0.876970000 | 0.833121500 | 0.877772333 **strict** | 0.877680500 **strict** |

### Per-case values

Per-case observations, not separate gate verdicts. Two passes per corpus case. CSV: `/tmp/moss-round16-stage/result/quality-per-case.csv` — MacStudio-local (not in repo).

| Layer / pass / case | Final WER | Immediate WER | Settled WER | DER | Ref-speech DER | Recall | Matched accuracy | Time attribution |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deployed / 1 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| deployed / 1 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889471 |
| deployed / 1 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| deployed / 1 / case-04 | 0.126177 | 0.131827 | 0.131827 | 0.097167 | 0.083895 | 0.941620 | 0.941620 | 0.895736 |
| deployed / 1 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.116418 | 0.104528 | 0.949477 | 0.909408 | 0.911797 |
| deployed / 1 / case-06 | 0.053398 | 0.140777 | 0.140777 | 0.419230 | 0.340055 | 0.922330 | 0.844660 | 0.801793 |
| deployed / 2 / case-06 | 0.053398 | 0.135922 | 0.135922 | 0.420052 | 0.340799 | 0.922330 | 0.844660 | 0.803047 |
| deployed / 2 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.116306 | 0.104410 | 0.949477 | 0.909408 | 0.911883 |
| deployed / 2 / case-04 | 0.126177 | 0.131827 | 0.131827 | 0.097222 | 0.083952 | 0.941620 | 0.941620 | 0.895694 |
| deployed / 2 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| deployed / 2 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| deployed / 2 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| pre_admission / 1 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |
| pre_admission / 1 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| pre_admission / 1 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| pre_admission / 1 / case-04 | 0.126177 | 0.131827 | 0.131827 | 0.097444 | 0.084179 | 0.941620 | 0.941620 | 0.895525 |
| pre_admission / 1 / case-05 | 0.069686 | 0.108014 | 0.090592 | 0.116474 | 0.104587 | 0.949477 | 0.909408 | 0.911752 |
| pre_admission / 1 / case-06 | 0.053398 | 0.140777 | 0.140777 | 0.419395 | 0.340055 | 0.922330 | 0.844660 | 0.801833 |
| pre_admission / 2 / case-06 | 0.053398 | 0.135922 | 0.135922 | 0.420708 | 0.341542 | 0.922330 | 0.844660 | 0.802905 |
| pre_admission / 2 / case-05 | 0.069686 | 0.106272 | 0.088850 | 0.116306 | 0.104410 | 0.951220 | 0.911150 | 0.912319 |
| pre_admission / 2 / case-04 | 0.126177 | 0.133710 | 0.133710 | 0.098222 | 0.084973 | 0.937853 | 0.937853 | 0.894450 |
| pre_admission / 2 / case-03 | 0.064748 | 0.143885 | 0.100719 | 0.089667 | 0.078152 | 0.985612 | 0.985612 | 0.913779 |
| pre_admission / 2 / case-02 | 0.147727 | 0.272727 | 0.193182 | 0.110167 | 0.101674 | 0.920455 | 0.920455 | 0.889535 |
| pre_admission / 2 / case-01 | 0.088496 | 0.194690 | 0.159292 | 0.142400 | 0.105061 | 0.867257 | 0.867257 | 0.853377 |

## F4 — load, backpressure and draft lane

HTTP completion rates below count service-wide vLLM transcription completions during each campaign interval; they do not attribute requests to individual sessions or lanes. Draft started counts are runtime invocations. KV usage is a fraction.

| Layer / load | Finalized / sessions | Terminal failures | Draft ticks / skipped / started / published / stale / errors | Draft calls/audio s | HTTP completions/audio s | KV peak |
|---|---|---:|---|---:|---|---:|
| deployed / four_session_capacity | 4/4 | 0 | 2400 / 2282 / 118 / 117 / 1 / 0 | 0.049167 | 1499/2400 = 0.624583 | 0.285544319 (28.554%) |
| deployed / eight_session_overload | 8/8 | 0 | 960 / 959 / 1 / 1 / 0 / 0 | 0.001037 | 529/964 = 0.548755 | 0.196311719 (19.631%) |
| pre_admission / four_session_capacity | 4/4 | 0 | 2400 / 2284 / 116 / 116 / 0 / 0 | 0.048333 | 1497/2400 = 0.623750 | 0.281380131 (28.138%) |
| pre_admission / eight_session_overload | 8/8 | 0 | 960 / 959 / 1 / 1 / 0 / 0 | 0.001037 | 529/964 = 0.548755 | 0.199881023 (19.988%) |

Backpressure exact refusal, peer progress, and same-frame retry evidence: deployed: `/tmp/moss-round16-stage/result/deployed-backpressure.json` — MacStudio-local (not in repo), pre_admission: `/tmp/moss-round16-stage/result/pre_admission-backpressure.json` — MacStudio-local (not in repo).

### Per-session load outcomes

| Layer / load / ordinal | Session | Accepted / accounted s | Finalization | Draft ticks / skipped / started / published / stale |
|---|---|---|---|---|
| deployed / four_session_capacity / 1 | `ahURXACKFX2Ru47cqAZWkMtw` | 600.0 / 600.0 | final | 600 / 592 / 8 / 8 / 0 |
| deployed / four_session_capacity / 2 | `3O5gjnpp8ef-jbrbIi7syfk9` | 600.0 / 600.0 | final | 600 / 557 / 43 / 43 / 0 |
| deployed / four_session_capacity / 3 | `gdK04S9ojrljmHoWXUKTvzTh` | 600.0 / 600.0 | final | 600 / 547 / 53 / 52 / 1 |
| deployed / four_session_capacity / 4 | `1Cyr--4ZRYLeh-w5eetyoH1a` | 600.0 / 600.0 | final | 600 / 586 / 14 / 14 / 0 |
| deployed / eight_session_overload / 1 | `GEvIP4papOPJxj8YQnJS1Ilf` | 120.5 / 120.5 | final | 120 / 119 / 1 / 1 / 0 |
| deployed / eight_session_overload / 2 | `yllcQm1xhtK0Otz0nyYG0Y89` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 3 | `p3fTkcJGlhNCL14FWJDiJiAi` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 4 | `7sgYLO80A1qa_sP5ueqSPqCF` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 5 | `C-6TGb0-h81EooLmE1fXo2uR` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 6 | `-925qVqhChx2Zd9T9btkElKH` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 7 | `g8QeS7BNgXq6Efrv8uQP23Th` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| deployed / eight_session_overload / 8 | `r85erW32ZGKUO9X367eujiMo` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / four_session_capacity / 1 | `z8LjhDZChxlKm40v63lwtrkX` | 600.0 / 600.0 | final | 600 / 588 / 12 / 12 / 0 |
| pre_admission / four_session_capacity / 2 | `2ZRwzRx4xcNQaKzH2ZqIOCNn` | 600.0 / 600.0 | final | 600 / 556 / 44 / 44 / 0 |
| pre_admission / four_session_capacity / 3 | `EmfnpVXVg6xYIn_OBrkuGDr9` | 600.0 / 600.0 | final | 600 / 541 / 59 / 59 / 0 |
| pre_admission / four_session_capacity / 4 | `_ldSDz-yw0a8Y8HGK--PQrAH` | 600.0 / 600.0 | final | 600 / 599 / 1 / 1 / 0 |
| pre_admission / eight_session_overload / 1 | `Bbn-mzIafKsH5yskFxQC6aQz` | 120.5 / 120.5 | final | 120 / 119 / 1 / 1 / 0 |
| pre_admission / eight_session_overload / 2 | `F47F35cMgdh-U_2xRSsLmv71` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 3 | `DHgy4YdbZjSy_72flDlK9WIE` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 4 | `GI4vmTvI-TyzWyx3ZefiIdvn` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 5 | `yXu3s4UrFzfeSDZMnokxWS06` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 6 | `uy251IGojLMSfE9bgE45IZmY` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 7 | `RTijB7sPj2KsX2ttg2BIeh2X` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |
| pre_admission / eight_session_overload / 8 | `AFeCEaNCMgFb5m56hcsWkjTx` | 120.5 / 120.5 | final | 120 / 120 / 0 / 0 / 0 |

## F5 — terminal diagnostics and restoration

Quality final surfaces: **24/24 closed/final**; main capacity **8/8**, overload **16/16** — **48/48 main sessions finalized**. Separately, G9 has **8/8 additional load sessions final** across both layers.

Retained load terminal failure records: 0 (supplemental/native duplicates possible). Full status-only diagnostics: `/tmp/moss-round16-stage/result/terminal-failures.json` — MacStudio-local (not in repo).

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
MainPID=177619
Id=moss-web.service
ActiveState=active
SubState=running

MainPID=177709
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

## F6 — pre-flight guards and handoff

Staging guard, verbatim:
```
{"filesystem": "root", "free_bytes": 743133691904, "minimum_bytes": 20000000000, "status": "ok"}
{"filesystem": "windows_c", "free_bytes": 613354676224, "minimum_bytes": 10000000000, "status": "ok"}
```
Cutover guard, verbatim:
```
{"filesystem": "root", "free_bytes": 759480819712, "minimum_bytes": 20000000000, "status": "ok"}
{"filesystem": "windows_c", "free_bytes": 613354647552, "minimum_bytes": 10000000000, "status": "ok"}
```

Both overload campaigns prove HTTP429 refusal, peer progress during backpressure and successful retry of the same frame; all eight finalized in each layer. Maximum native sampled KV occupancy **0.285544319 (28.554%)**; independent periodic monitor peak **0.266508031 (26.651%)**. These are sampled maxima. One stale draft completion in deployed capacity; zero draft errors. Service-wide HTTP rates above are not per-lane attribution.

Phase-1 both services active, views open with zero work; canonical tailnet HTTPS **200**. vLLM before/after byte-identical: **PID324**, NRestarts0, start monotonic2306978. MinerU tasks both enabled/running. Staged relay configuration and draft1.0 preserved; env and both profiles0600. Hosts prerequisite verified before start. Source checkout clean. No admission or attended preadmission; G7 unclaimed.

**Handoff NOT MET overall:** product-predicate condition is met, with exactly DER, reference-speech DER and matched-speaker accuracy inside the approved 5% band in both layers. The separate rehearsal configuration error prevents a clean full qualification. Bounds, identity policy and implemented zero-terminal-failure/all-eight-finalized checks remain unchanged; no closed fix reopened.

Evidence archived to Mac: evidence.tar: `/tmp/moss-round16-stage/result/evidence.tar` — MacStudio-local (not in repo), **232,683,520 bytes, 4,494 readable members**. Per-case quality CSV: `/tmp/moss-round16-stage/result/quality-per-case.csv` — MacStudio-local (not in repo) and full per-case table above. Do not conflate the successfully restored actual attempt with the failed isolated rehearsal.

Documentation task completed and pushed privately as **55be0f48**: round-15 handback section2, explicit pre-admission-only exception scope for that historical round, requested regression sentence, sanitized round15 report and index link. PR32 draft/unmerged references preserved. No merge performed.
