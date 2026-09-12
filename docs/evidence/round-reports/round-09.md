> Historical report, copied from `/tmp/moss-round9-stage/result/report.md` (MacStudio-local source, not in repo). Only reference annotations changed; results and original decisions are preserved. This is not current host status. Uncopied artifacts remain local.

# Round 9 — restored; qualification failed

Candidate **433e67b25274e98eabc4d3523e5256525e7349f7**; tree **7935b6a0e7710c474430d05c5714ce466d7ff70f**. Fresh local clone `/tmp/moss-round9-stage/source`; fresh host bundle clone `/tmp/moss-round9-source`. Guard commit 433e67b2 was present before build. No code from the shared worktree was packaged.

Attempt: `/home/devcontainers/.local/state/moss-transcribe-diarize/cutover-attempts/restored-20260911T233910Z`. Terminal **restored**, admitted **false**, G7 **UNCLAIMED**. Retained error: `same-SHA three-wave qualification failed`. One qualification run, `--terminal restored`; no preadmission terminal or rerun.

## F1 — build custody failure: my recipe mistake

I omitted `sort_keys=True` when writing the wheel's embedded build_candidate.json. The documented recipe and qualification rebuild sort those keys. Identity values are equal, but the serialized bytes and wheel RECORD projection differ. Both installed_candidate_identity predicates therefore fail. Direct comparison of the staged and qualification wheels found only two differing members: `moss_transcribe_diarize/build_candidate.json` and `.dist-info/RECORD`; all other members are byte-identical. This is my packaging error, not evidence of dirty source or different product code. No bypass or remediation rerun was performed.

Installed RECORD projection: `a9319a8998ef6409312896b71f34308af6fe102739e4b4013b28e76ac2192be1`. Qualification expectation: `57d37ef0d21babe7d2f6b7b4ecd996e05ae7b0d0c5079446d2fa4910014cf390`. The sample says collection PASS and RECORD verified against the installed wheel; the final evaluator correctly rejects the cross-wheel mismatch.

Both profile files were repointed at the candidate manifest and kept mode 0600; both acceptance layers matched. Provider source_revision changed to this SHA; all other provider fields, bounds, and identity policy were equal to the prior manifest. Staged relay environment was preserved. Sourcemap dirty-tree failure did not recur; staged checkout remains clean.

## F2 — final denominators

Counts below use final evaluated predicates, not merely successful collection. A collected observation can still fail its semantic checks.

| Layer | Executed | Passed | Failed | Unmeasured |
|---|---:|---:|---:|---:|
| Deterministic commands | 18 | 18 | 0 | 0 |
| deployed predicates | 19 | 8 | 11 | 0 |
| pre_admission predicates | 17 | 7 | 10 | 0 |

Python: **1337 passed, 2 skipped, 37 subtests passed**; retained JUnit counts **1376 collected / 1374 executed / 1374 passed / 0 failed / 2 skipped**. Frontend **195/195 passed**. All 18 deterministic commands passed, including final-summary-real-cors.

Quality: pre_admission **12 sessions / 118 windows scored**; deployed **0 scored** due transport failure. Verdict campaign counters label all 12/118 failed because quality gates fail; these are not terminal-decoder failures. Capacity campaign counters contain zero collected rows because collection raised before returning campaign observations; supplemental session evidence below establishes what actually completed.

## F3 — every failed predicate

| Predicate | Deployed retained message/result | pre_admission retained message/result |
|---|---|---|
| `account_product_regression` | Account HTTP POST /api/live/sessions transport failed: ConnectError | Page.wait_for_function: Timeout 30000ms exceeded. |
| `audio_durability_download` | Page.goto: net::ERR_CONNECTION_REFUSED at https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/ | Live Meeting did not Stop: HTTP 409 b'{"detail":"live Meeting is terminal."}' |
| `browser_final_summary` | Locator.fill: Timeout 30000ms exceeded. | Locator.fill: Timeout 30000ms exceeded. |
| `crash_recovery` | forced Account web restart failed | Not required |
| `eight_session_overload` | moss-web.service is not running | live load failed in 1 session/probe paths |
| `four_session_capacity` | moss-web.service is not running | rolling admitted/completed accounting is incomplete |
| `installed_candidate_identity` | Final evaluator: installed_candidate_identity:failed. RECORD projection mismatch; see F1. | Final evaluator: installed_candidate_identity:failed. RECORD projection mismatch; see F1. |
| `meeting_modes_history_restart` | Live Meeting did not Stop: HTTP 409 b'{"detail":"live Meeting is terminal."}' | Live Meeting did not Stop: HTTP 409 b'{"detail":"live Meeting is terminal."}' |
| `operator_control` | Service journal unit/message provenance is invalid | Final evaluator: operator_control:failed. human_exact_projection=false; json_exact_projection=false; admitted_item_processed_events=0; queued_item_discarded_events=0. |
| `quality_corpus` | ambiguous Account HTTP replay result: URLError | Six strict macro bounds fail: settled_wer, recall, time_speaker_attribution, diarization_error_rate, matched_speaker_accuracy, reference_speech_der. See F4. |
| `transcript_pane_fidelity` | Account HTTP GET /api/meetings transport failed: ConnectError | Page.wait_for_selector: Timeout 30000ms exceeded. |

The deployed crash probe killed the main web process, then the systemd kill operation reported failure signaling auxiliary processes. Code raises before `_await_service()` if kill/start returns nonzero. Systemd subsequently restarted the service; several following probes failed during that outage. The deployed journal baseline contained systemd-emitted records with `_SYSTEMD_USER_UNIT=init.scope` and `USER_UNIT=moss-web.service`; the collector requires the former to equal moss-web.service. These are retained mechanisms, not repaired gates. Service records: `/tmp/moss-round9-stage/result/service-events.json` — MacStudio-local (not in repo).

## F4 — eight quality macros and authorized 5% relative tolerance

Deployed macros are all **UNMEASURED**. The table shows the actual pre_admission two-pass macro. Exception limits are strict maximum ×1.05 or strict minimum ×0.95; no evaluator or policy value was changed.

| Metric | Strict bound | 5% exception limit | pre_admission | Result |
|---|---:|---:|---:|---|
| immediate_wer | ≤0.166655 | ≤0.17498775 | 0.164900083 | PASS strict |
| settled_wer | ≤0.140442 | ≤0.14746410 | 0.167557500 | FAIL beyond 5% |
| recall | ≥0.929636 | ≥0.88315420 | 0.899647500 | Within 5% exception only |
| time_speaker_attribution | ≥0.876970 | ≥0.83312150 | 0.854412833 | Within 5% exception only |
| diarization_error_rate | ≤0.161430 | ≤0.16950150 | 0.184594583 | FAIL beyond 5% |
| matched_speaker_accuracy | ≥0.911512 | ≥0.86593640 | 0.880342667 | Within 5% exception only |
| reference_speech_der | ≤0.134804 | ≤0.14154420 | 0.156622667 | FAIL beyond 5% |
| final_wer | ≤0.095074 | ≤0.09982770 | 0.092333083 | PASS strict |

Immediate/final WER pass strictly; settled WER and both diarization-error measures fail beyond tolerance. Matching accuracy, time attribution and recall fall within the approved relative exception only. Quality therefore remains failed even with that exception. Successfully scored final surfaces and remaining speaker errors refute an explanation consisting solely of terminal-pass measurement failure; they do not alone localize an identity algorithm defect.

## F5 — terminal/session diagnostics

All **12 quality replays succeeded** and retain terminal-diagnostics.json; none contains terminal_finalization_failed. All 12 corresponding meetings were completed with final runtime state. No settle-timeout counts occurred in the scored second layer. The deployed quality attempt failed transport before retaining a session trace.

Supplemental read-only Account API capture retained 26 live meetings: **23 completed/final**, **3 interrupted/not_started**. The completed set is exactly 12 quality sessions, four 600-second capacity sessions, and seven 30-second overload sessions. The capacity failure is not four terminal failures. These supplemental records are not substitutes for successful capacity accounting. Session/status/event evidence: `/tmp/moss-round9-stage/result/supplemental-pre_admission-sessions.json` — MacStudio-local (not in repo).

| Session | Retained ending | Diagnostic |
|---|---|---|
| `dNMAiqxt_bxmZAb9ta70XwSy` | interrupted; runtime aborted; finalization not_started | `acceptance load failure`; accepted=472000, accounted=80160; `session_aborted` seq=114, monotonic_ns=2790637487350202; code=aborted, kind=transport_pacing |
| `bWL7KVDyW2VnjwXNippasI0e` | interrupted; runtime failed; finalization not_started | `helper_lease_expired`; accepted=88000, accounted=80160; `session_aborted` seq=26, monotonic_ns=2789879332961836; code=aborted, kind=transport_pacing |
| `lukJw-6miWw49at7CmkkjmqH` | interrupted; runtime failed; finalization not_started | `helper_lease_expired`; accepted=96000, accounted=80000; `session_aborted` seq=23, monotonic_ns=2789885781938736; code=aborted, kind=transport_pacing |

For these interrupted sessions the retained event has outcome=null, reason=null, refusal=null, window_failure=null; the snapshot carries the reason shown above. `dNMAiqxt_bxmZAb9ta70XwSy` is the overload cleanup abort after 29.5 seconds accepted. The two helper-lease expiries happen before a finalizer starts. The read-only revoked-cookie probe returned HTTPError as expected; no credential was retained.

Deployed service journal additionally retains helper_lease_expired for sessions `pBO-CMTTPwjyqPnxM1Invh9-` and `mOwVXnBg5OflKveaLB_qJ3IG`, lanes=none. Full per-session terminal events for those are not retained across the crash; outcome/refusal/window details and Stop ordering cannot be recovered from that journal alone. No claim of zero failures is made for missing evidence.

## F6 — restored host and follow-on work

Phase-1 web **709777** and live web **709885** both active/running. Batch and live runtime views **open**; entrants, active_jobs, queued_jobs, active_live_sessions all **0**. vLLM before/after files are identical: **PID 169937**, **NRestarts=0**, **ExecMainStartTimestampMonotonic=1208158572226**. Views: `/tmp/moss-round9-stage/result/views-after.json` — MacStudio-local (not in repo), services: `/tmp/moss-round9-stage/result/phase1-after.txt` — MacStudio-local (not in repo), vLLM before: `/tmp/moss-round9-stage/result/vllm-before.txt` — MacStudio-local (not in repo), after: `/tmp/moss-round9-stage/result/vllm-after.txt` — MacStudio-local (not in repo), terminal result: `/tmp/moss-round9-stage/result/result.json` — MacStudio-local (not in repo), journal: `/tmp/moss-round9-stage/result/journal.jsonl` — MacStudio-local (not in repo).

Optional launcher wiring pushed as **ee52440d17bb439f8865cb425715e6472c801112**, after pull --rebase, private/auto-mvp-0911 only. MOSS_LIVE_DRAFT_LANE_SECONDS appends the CLI option only when nonempty. Test `test_account_launcher_optional_draft_lane_preserves_existing_argv` covers unset, empty, and 1.0, comparing NUL-delimited argv bytes. **13 deployment/launcher tests passed**. Installed identity validates interpreter plus argv[1:4], so appending the option preserves that prefix. A new wheel/manifest remains necessary; no launcher was changed in this candidate.

Staged env now includes `MOSS_LIVE_DRAFT_LANE_SECONDS=1.0`, mode0600, relay retained. Round9 active env had no draft option; the lane was off throughout this run. Next candidate's four/eight-session gates must establish its headroom. No new candidate built or new run started.

Existing row-10 analysis was handed off in docs-only commit **e786a6e23c5f70b3de9b6ef5883036894d20b4e0**, after pull --rebase, for agent1.2. Investigation stopped; no recognition implementation.

Full retained evaluator errors:

```
deployed:G0:installed_candidate_identity:failed
deployed:G10:account_product_regression:failed
deployed:G10:transcript_pane_fidelity:failed
deployed:G3:crash_recovery:failed
deployed:G3:meeting_modes_history_restart:failed
deployed:G4:eight_session_overload:failed
deployed:G4:four_session_capacity:failed
deployed:G4:quality_corpus:failed
deployed:G4:quality_corpus:quality macro is absent; inspect retained collection failure
deployed:G5:audio_durability_download:failed
deployed:G6:operator_control:failed
deployed:G9:browser_final_summary:failed
pre_admission:G0:installed_candidate_identity:failed
pre_admission:G10:account_product_regression:failed
pre_admission:G10:transcript_pane_fidelity:failed
pre_admission:G3:meeting_modes_history_restart:failed
pre_admission:G4:eight_session_overload:failed
pre_admission:G4:four_session_capacity:failed
pre_admission:G4:quality_corpus:failed
pre_admission:G4:quality_corpus:reported diarization_error_rate=0.184594583333 exceeds maximum 0.16143
pre_admission:G4:quality_corpus:reported matched_speaker_accuracy=0.880342666667 is below minimum 0.911512
pre_admission:G4:quality_corpus:reported recall=0.8996475 is below minimum 0.929636
pre_admission:G4:quality_corpus:reported reference_speech_der=0.156622666667 exceeds maximum 0.134804
pre_admission:G4:quality_corpus:reported settled_wer=0.1675575 exceeds maximum 0.140442
pre_admission:G4:quality_corpus:reported time_speaker_attribution=0.854412833333 is below minimum 0.87697
pre_admission:G5:audio_durability_download:failed
pre_admission:G6:operator_control:failed
pre_admission:G9:browser_final_summary:failed
```

Evidence: verdict: `/tmp/moss-round9-stage/result/verdict.json` — MacStudio-local (not in repo), gate table: `/tmp/moss-round9-stage/result/gate-table.json` — MacStudio-local (not in repo), deployed observations: `/tmp/moss-round9-stage/result/raw/deployed-observations.json` — MacStudio-local (not in repo), pre_admission observations: `/tmp/moss-round9-stage/result/raw/pre_admission-observations.json` — MacStudio-local (not in repo).
