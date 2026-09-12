> Historical report, copied from `/tmp/moss-round8-stage/result/report.md` (MacStudio-local source, not in repo). Only reference annotations changed; results and original decisions are preserved. This is not current host status. Uncopied artifacts remain local.

# Round 8 — restored; external qualification unmeasured

**Candidate:** `91b37bb66e51bdaacb3c06282387a6591908eda5`. **Tree:** `440b6593591a32f1213a5392292d5c8afd48e23a`. Pushed to private/auto-mvp-0911 after pull --rebase.

**Attempt:** `/home/devcontainers/.local/state/moss-transcribe-diarize/cutover-attempts/restored-20260911T231308Z`. `terminal=restored`, `admitted=false`, `g7=UNCLAIMED`. Error: `same-SHA three-wave qualification failed`.

## F1 — build provenance and Stop fix

The wheel was built from the clean isolated clone `/tmp/moss-prompt-fix`, not the shared `MOSS-Transcribe-Diarize-wt-auto-mvp-0911` worktree. Source copy excluded .git, .venv, node_modules, build, dist, evidence; build_candidate.json was written before uv build. Embedded wheel SHA/tree/lock/fixture identity matched the source. A git bundle shipped the pushed commit into fresh `/tmp/moss-round8-source` on the host; its HEAD and clean status were checked before staging. The isolated build clone existed from the prior task; it was not newly created specifically for this build. Future builds will use a fresh clone of the exact pushed SHA, per the subsequent instruction.

The normal product Stop calls CaptureClient.stop(5); its HTTP deadline is the remaining portion after local frame-queue draining. Acceptance now supplies 5.0 seconds for its already-delivered audio: lifecycle Stop formerly had no body; capacity formerly passed an absolute monotonic timestamp; completion/summary formerly used 60.0 seconds. The foreign-owner Stop probe also now includes the explicit deadline. Replay already forwards an explicit deadline and its quality caller passes 5.0. Browser-driven checks use the product client. The browser reset path still calls stop(0), and runtime semantics were not changed.

Tests: `test_acceptance_replay_stop_payload_has_positive_browser_deadline`, `test_every_direct_acceptance_stop_has_explicit_browser_deadline`, `test_capacity_stop_uses_duration_not_monotonic_timestamp`. Focused validation: 38 passed, 9 subtests passed.

All three candidate_manifest pointers were repointed; cutover and acceptance profiles mode 0600. Provider source_revision updated; all other provider settings compared unchanged. QUALITY_BOUNDS, identity policy, runtime Stop semantics unchanged.

## F2 — exact blocking failures

`candidate_became_dirty` prevented both external collectors from being launched. The qualification frontend build modified only tracked `moss_transcribe_diarize/app/frontend_assets/app.js.map`; five entries in its `sources` array changed from `../../../../MOSS-Transcribe-Diarize/frontend/node_modules/...` to `../../../frontend/node_modules/...`. Other source-map fields were equal. This is a committed developer-path-dependent source map regenerated in the fresh qualification clone, not uncommitted shared-worktree code in the wheel. The staged candidate checkout and fresh host scratch clone remain clean. Qualification also has its expected untracked evidence/phase2 directory, which the dirty check excludes. See source status: `/tmp/moss-round8-stage/result/source-status.txt` — MacStudio-local (not in repo).

Four Python tests failed with the same retained error:

`BrowserType.launch: Executable doesn't exist at /home/devcontainers/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell`

- `tests.phase2.test_canonical_preview::test_decoded_preview_visible_before_identity_and_retired[commit]`
- `tests.phase2.test_multi_file_url_meetings::test_mixed_serial_items_are_independent_and_owner_bound`
- `tests.phase2.test_workspace_demo_geometry::test_header_and_pane_dimensions_survive_demo_changes[viewport0]`
- `tests.phase2.test_workspace_demo_geometry::test_header_and_pane_dimensions_survive_demo_changes[viewport1]`

The other failed deterministic command, `final-summary-real-cors`, retained:

```text
Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for get_by_role("button", name="Retry summary", exact=True) to be visible
```

No external predicate executed, so there are no per-predicate measured failure messages. Every external predicate below is UNMEASURED, blocked by candidate_became_dirty. Do not count these as passing or as measured failures.

## F3 — per-layer counts

| Layer | Required / collected | Executed | Passed | Failed | Unmeasured |
|---|---:|---:|---:|---:|---:|
| Deterministic commands | 18 | 18 | 16 | 2 | 0 |
| deployed predicates | 19 | 0 | 0 | 0 | 19 |
| pre_admission predicates | 17 | 0 | 0 | 0 | 17 |

Python console: **1282 passed, 4 failed, 2 skipped, 37 subtests passed**. The retained JUnit denominator includes those subtests: **1325 collected, 1323 executed, 1319 passed, 4 failed, 2 skipped**. Frontend: **182/182 passed**. Typecheck/build commands passed, but the successful build dirtied the tracked map.

### deployed: all unmeasured

- G0: `installed_candidate_identity`, `zero_work_end`
- G1: `cross_owner_matrix`, `sentinel_absence`, `same_account_convergence`
- G2: `browser_workspace_identity`, `revocation_lifecycle`
- G3: `meeting_modes_history_restart`, `crash_recovery`
- G4: `four_session_capacity`, `eight_session_overload`, `quality_corpus`
- G5: `audio_durability_download`
- G6: `operator_control`
- G10: `account_product_regression`, `transcript_pane_fidelity`
- G8: `voiceprint_production_rule`, `voiceprint_workspace_behavior`
- G9: `browser_final_summary`
### pre_admission: all unmeasured

- G0: `installed_candidate_identity`, `zero_work_end`
- G1: `cross_owner_matrix`, `sentinel_absence`
- G2: `browser_workspace_identity`, `revocation_lifecycle`
- G3: `meeting_modes_history_restart`
- G4: `four_session_capacity`, `eight_session_overload`, `quality_corpus`
- G5: `audio_durability_download`
- G6: `operator_control`
- G10: `account_product_regression`, `transcript_pane_fidelity`
- G8: `voiceprint_production_rule`, `voiceprint_workspace_behavior`
- G9: `browser_final_summary`

Retained evaluator errors:

```text
candidate_became_dirty
cross_layer_identity_unmeasured
deployed_collector_report_missing
deployed_evidence_unreadable:FileNotFoundError
deployed_unmeasured
pre_admission_collector_report_missing
pre_admission_evidence_unreadable:FileNotFoundError
pre_admission_unmeasured
pytest_failures
pytest_required_file_not_all_passed:tests/phase2/test_multi_file_url_meetings.py
```

## F4 — eight quality macros and authorized tolerance

No quality replay ran. Both layers have zero scored sessions/windows; every macro is unavailable. No tolerance pass or speaker-identity conclusion can be made. The 5% column is the authorized relative exception threshold; it was not written into the evaluator or bounds.

| Metric | Strict bound | 5% relative exception threshold | Deployed | pre_admission |
|---|---:|---:|---|---|
| immediate_wer | <= 0.166655 | <= 0.17498775 | UNMEASURED | UNMEASURED |
| settled_wer | <= 0.140442 | <= 0.14746410 | UNMEASURED | UNMEASURED |
| recall | >= 0.929636 | >= 0.88315420 | UNMEASURED | UNMEASURED |
| time_speaker_attribution | >= 0.876970 | >= 0.83312150 | UNMEASURED | UNMEASURED |
| diarization_error_rate | <= 0.161430 | <= 0.16950150 | UNMEASURED | UNMEASURED |
| matched_speaker_accuracy | >= 0.911512 | >= 0.86593640 | UNMEASURED | UNMEASURED |
| reference_speech_der | <= 0.134804 | <= 0.14154420 | UNMEASURED | UNMEASURED |
| final_wer | <= 0.095074 | <= 0.09982770 | UNMEASURED | UNMEASURED |

No terminal-session diagnostics exist for this round: the external collectors never created quality/capacity sessions. No terminal failure count of zero is claimed as evidence of correct finalization.

## F5 — restored host and custody

Phase-1 services active/running: web PID **681383**, live web PID **681467**. Both batch/live views open; entrants, active_jobs, queued_jobs, active_live_sessions all **0**.

vLLM before/after files identical: **MainPID=169937**, **NRestarts=0**, **ActiveEnterTimestampMonotonic=1208158572270**. No admission or preadmission terminal; G7 unclaimed. No runtime/host remediation or additional qualification run attempted.

Before the actual run, one CLI invocation (`restored-20260911T231212Z.log`) omitted the required `run` subcommand and exited at argument parsing. It created no attempt journal, performed no cutover and launched no qualification. Corrected invocation used the fresh attempt reported above.

Evidence: result: `/tmp/moss-round8-stage/result/result.json` — MacStudio-local (not in repo), journal: `/tmp/moss-round8-stage/result/journal.jsonl` — MacStudio-local (not in repo), verdict: `/tmp/moss-round8-stage/result/verdict.json` — MacStudio-local (not in repo), gate table: `/tmp/moss-round8-stage/result/gate-table.json` — MacStudio-local (not in repo), Python output: `/tmp/moss-round8-stage/result/raw/python.stdout` — MacStudio-local (not in repo), summary probe stderr: `/tmp/moss-round8-stage/result/raw/final-summary-real-cors.stderr` — MacStudio-local (not in repo), restored views: `/tmp/moss-round8-stage/result/views-after.json` — MacStudio-local (not in repo), vLLM before: `/tmp/moss-round8-stage/result/vllm-before.txt` — MacStudio-local (not in repo), vLLM after: `/tmp/moss-round8-stage/result/vllm-after.txt` — MacStudio-local (not in repo).
