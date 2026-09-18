# Effective MOSS product contract — 2026-09-18 refresh

**One browser-private product; one complete launch.** Correct speech, speaker identity,
reliable summaries and durable saved results remain required. Performance-only misses may
be explicitly deferred; they must still be measured and reported. This draft reconciles
requirements; it neither closes tracker issues nor claims integration or launch acceptance.

## Authority and structural contract

Sources: `CONTEXT.md`; ADR-0010–0014; `docs/phase2-afk-charter.md`;
`docs/production-plan-20260910.md`; `docs/handoffs/auto-mvp-0911-handback.md`;
WP8 brief and execution plan dated 2026-09-17. External review root **R** is
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/moss-mvp-review/`.
Read `R/final-review.md` §§5–6 and `R/evidence/independent-review/ledger-audit.md`.
Tracker population is exactly `R/evidence/github-issues.json`: **31 issues, 16 open,
15 closed**. This is a supplied dated snapshot, not a fresh GitHub claim.
WP8 supplied the original 31-ticket inventory; no GitHub refresh or writes here.
Current code pin: `c609d7f3e03091becda8aa8588655447a51ea434`. Branch evidence and
merge order: [WP1–WP22 campaign ledger](handoffs/mvpfix-campaign-20260918.md).
WP8 itself was not merged; WP23 imports and refreshes this document from `fcb247c2`.

- **Q1 — Question:** what observable behavior must survive from capture through saved
  history, independent of which work package or historical ticket implemented it?
- **Q2 — Minimum primitives:** browser credential (access continuity), workspace
  (ownership), meeting (durable work), source lane (capture origin), speaker ID
  (identity), artifact (saved result), evidence (acceptance witness). Each answers a
  different question; a label cannot replace identity, nor a passing test replace a saved result.
- **Q3 — Invariants:** foreign workspace gets 404/no mutation; provider keys remain in
  browser; lanes never reconcile identities; Stop waits for required durability;
  late work cannot revive interrupted work; missing evidence is not success.
- **Q4 — Unknowns:** final-candidate lane acceptance/capacity (earlier quality failures measured), physical echo, semantic summary
  quality, production trust/renewal, operator visual approval, and D2/D3/D5 below.
- **Q5 — Falsifier:** accepted speech disappears; a word belongs to the wrong speaker;
  lane identity merges; saved/exported content differs; foreign access succeeds;
  invalid summaries persist; a green gate lacks its required observations.
- **Q6 — Tools:** source/diff review establishes authority and regression scope;
  WP4 content oracles test words/exports; WP5 browser actions test journeys;
  WP6 measures contention; physical G7 establishes actual capture. A failed witness
  retains the failure and blocks that claim, rather than spawning new policy.

User decisions in WP8 supersede older contradictory prose:
**headphones AND speakers with acoustic echo cancellation (AEC) are required**;
`system` and `microphone` are independent speaker namespaces, even for the same voice;
Gemini **2.5 Flash Lite** is the external summary provider with a browser-owned key;
the configured keyless relay remains a fallback. This does not authorize silently
sending an external-provider failure to another provider. Existing explicit selection,
discovery and bounded configured-relay retry behavior remains the implementation contract.

ADR-0013:5,7,11 replaces human Google identity and separate wave releases. It preserves
ownership, lifecycle, audio, quality and four-session capacity. ADR-0011:34–69 amends
its earlier no-proxy wording only for configured keyless models. The old absolute
no-proxy sentences in ADR-0013:9 and production plan D5 need that limited amendment;
arbitrary external URLs/credentials must never pass through MOSS.
ADR-0014:36–58 keeps QUALITY_BOUNDS and names each admitted relative exception.
The new performance-deferral ruling does not erase a capacity test or grant blanket acceptance.

## Supported journeys and acceptance instruments

Paths below are candidate-relative unless a WP source worktree is named. Evidence
pins and branch limitations are in the campaign ledger. Run acceptance on one final
candidate before closure. WP8's F1/F2 export defects are repaired by WP11, backed by
`tests/phase2/test_export_oracle.py` (50/50 at WP11); F3's expected-failure loophole
is repaired by WP14's `tests/phase2/test_demo_lane_measurement.py`. The repaired
oracle now reports the actual quality failures; repair does not turn them into passes.

| Journey | Required behavior | Acceptance instrument and remaining evidence |
|---|---|---|
| J1 Workspace/bootstrap | No login; same profile/tabs converge; different profiles isolated; restart continuity; cookie loss cannot switch owner mid-mutation | `tests/phase2/test_browser_workspace.py` (bootstrap, same-origin, old-schema refusal); `test_workspace_lifecycle.py`; WP5 `prototypes/browser-stress/run.py` cases 8/14; production second-profile G7 |
| J2 Live capture | Mic + shared tab and mic + entire-screen audio; exact nine-key frames; truthful readiness; foreground/background continuity; headphones and speakers+AEC | WP3 `tests/test_live_capture_guard.py`, `frontend/src/components/ControlPanel.captureFailure.test.tsx`; WP5 cases 1–7; `phase2_g7_canary.py` and attended runbook; `docs/handoffs/attended-echo-protocol.md`. WP5 hidden-tab capture is still blocked, not passed |
| J3 Lane words and identity | Keep quiet/loud speech in either lane; different lanes can overlap; same voice across lanes has distinct IDs; silence adds no words/people | WP1 `prototypes/lane-decode-proto/`; WP4 `lane_word_oracle.py`, `tests/e2e/verify_demo_lanes.py`; WP7 `prototypes/identity-stress/`. Measure ordered word error rate (WER), omissions/additions, attribution and duplication, not only vocabulary. Existing immediate 16.6655% and final 9.5074% WER bars remain; P3 defines the additional retention population/bar. WP17/WP20: 0/2 full cases pass |
| J4 Stop/history/export | Preserve accepted text/IDs/source_lane through rolling/terminal updates, Stop, reopen, search, rename and md/txt/json/srt/vtt downloads; legacy lane-less documents remain usable | WP2 `test_lane_consumer_geometry.py`, `test_lane_consumer_store.py`, `frontend/src/lib/laneConsumers.test.ts`; WP11-corrected `tests/e2e/export_oracle.py` + `test_export_oracle.py`; WP5 cases 10/14. Compare downloaded content, not only nonempty files |
| J5 Upload/URL/batch | Each item independent and durable after tab closure; invalid media/404/timeout has a safe cause; confirmed speechless success explains empty text | `test_owner_bound_file_meeting.py`, `test_multi_file_url_meetings.py`; WP4 `test_file_failure_reasons.py`, `measure_file_boundaries.py`; WP16 real browser 16-case campaign, 50/50 saved exports, five typed failures; WP18 `test_file_truncation_notice.py`; WP19 `test_file_identity_album.py` / `test_file_album_acceptance.py`. Generic URLs remain bounded HTTP(S); no new host allow-list implied |
| J6 Audio/recovery | One owner-private 16 kHz mono 48 kbit/s MP3; complete/partial/unavailable truthful; normal terminal cleanup removes raw audio; transcript survives audio failure | `test_file_mp3_artifact.py`, `test_owner_bound_live_meeting.py`, `test_workspace_lifecycle.py`; WP5 cases 6/7/10/14; production backup/restore and restart evidence |
| J7 Names/voiceprints | IDs independent of duplicate labels; active origin may name/enroll; owner may rename saved speakers and explicitly enroll File evidence per WP9/WP19; private bank rename/delete fences old results; stopped history keeps recorded labels | `test_manual_speaker_voiceprints.py`, `test_voiceprint_matching.py`, `test_voiceprint_bank_operations.py`; standing `voice-profile-matching` bench; WP7 identity stress. WP9 `test_saved_speaker_naming.py` permits owner naming after Stop; WP17 `test_live_lane_decode.py` retains recognition observations (4/4 API routes <4 s). API-name latency is not browser-name latency |
| J8 Summaries | Final transcript only; exact five-field validation; browser keys/settings; cancellation/retry/title/isolation; no impact on speech or audio; blank settings still transcribe | `test_final_summary.py`, `test_summary_provider_paths.py`, `test_llm_relay.py`; frontend `FinalSummary.test.tsx`; `tests/e2e/verify_summaries.py`; real Flash Lite and configured fallback attempts plus source-based owner review. WP4 paid attempts = 0, blocked on key |
| J9 Operator/isolation | Content-free status/journal; interrupt/revoke durably fences late work; other workspace unaffected | `test_operator_status.py`, `test_workspace_lifecycle.py`, `test_owner_bound_live_meeting.py`; cumulative G1/G5/G6 adversarial sentinels |
| J10 Capacity/quality | Four concurrent live meetings; 600 s, two workspaces; eight-session overload probe; frozen six-case/two-pass quality; preserve failures and named exceptions | `scripts/phase2-acceptance/run.py`; WP6 `prototypes/capacity-campaign/run.py`; `test_quality_exception_band.py`; final deployed same-SHA campaign. WP6 4x600 had 2/4 final, foreign-load pauses and no overload run; WP15 unpaused 600 s completed. Neither is final-candidate capacity |
| J11 Product surface | Reference UI, 1440×900/1280×800/~400px; two Refresh controls preserved; no legacy routes; no claimed visual approval from geometry | `tests/e2e/verify_workspace.py`, WP5 case 12, existing sentinel/geometry tests; operator-reserved visual approval on served candidate |
| J12 Operations/launch | Trusted canonical HTTPS; tested DNS-01 renewal; exact installed process; preserve incompatible DB; backup/restore, post-user-data rollback and scheduled cold boot | `test_candidate_tls.py`, `test_tls_renewal.py`, `test_atomic_cutover.py`, `test_candidate_storage.py`; production process/trust/renewal and restore records. Unit controls cannot establish host readiness |

Preserve identity policy, readiness thresholds, two-Refresh sentinel, nine-key protocol,
and existing lifecycle checks. ADR-0010 historically excluded MP3 inference. Accepted WP19 adds one explicit
exception: owner-requested File voiceprint enrollment reconstructs acoustic evidence
from retained MP3 and selected canonical intervals (`docs/design-streaming-diarization.md`,
WP19 section; `tests/phase2/test_file_album_acceptance.py`). No automatic enrollment
or MP3 re-transcription follows from it. Missing saved audio reports unavailable. Per-lane transcription does not imply durable raw-lane archives.
Same-lane simultaneous speakers are not claimed by the lane split; P5 remains unresolved.

## Explicit exclusions

- **X1:** Public exposure, arbitrary adversaries, cross-workspace sharing/recovery/linking,
  login/Reset/Sign-out UI, shared mode as a supported promise pending D3.
- **X2:** Cross-lane identity reconciliation, label-based identity, raw-lane retention,
  MP3 re-transcription, automatic enrollment from a match. Explicit WP19 File
  voiceprint enrollment is the narrow accepted exception described above.
- **X3:** Multi-process/horizontal ownership, more than four supported live meetings,
  browser/OS parity beyond documented Chrome/macOS capture. Eight is an overload test.
- **X4:** Live/rolling summaries, repair inference, arbitrary server-proxied providers,
  server-held external API keys, automatic history-client summary calls.
- **X5:** Phase-1 content import, legacy `/studio`/`/live`/job authority, product backup
  manager/quota/TTL. Operator backup/restore remains required; excluding a product UI
  does not exclude durability operations.
- **X6:** Any deployment, attended G7, physical AEC, visual approval or final-candidate
  capacity claim from this documentation refresh. No authority to choose D2/D3/D5 or change thresholds.

## Per-ticket disposition (31/31)

These are proposed tracker dispositions, not state changes. `historical-closed` means
leave its historical closure intact; its carried behavior still participates in final
regressions. `superseded` applies only to the stated old mechanism. Ticket-wide closure
must preserve residual obligations listed here; no blanket retirement of mixed criteria.

**Closure file convention (planned, absent today):** `E = evidence/mvpfix/integration/`.
Each exact `E/Ixx.json` below must identify the final candidate, named journey/test,
actual commands/counts, raw evidence paths and verdict; this is a proposed evidence
location, not new tooling. Release rows also require the real driver's same-candidate
`evidence/phase2/wave-3/<UTC>-<git-short-sha>/verdict.json` and underlying predicates.
A short verdict without those underlying observations does not close anything.
Historical rows need no new tracker closure; the listed file records carried obligations.

| Ticket | Snapshot | Disposition | Residual obligation / exact closure file |
|---|---|---|---|
| [#1](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/1) | OPEN | acceptance-only | J2/J3 actual attended capture; WP4/WP7 `tests/phase2/test_attended_g7_canary.py` requires 7/8 ordered operator words and distinct tab speaker. Both source scenarios and headphone/speakers+AEC routes remain unmeasured; `E/I01.json`. |
| [#2](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/2) | CLOSED | superseded | Shared bearer retired by ADR-0012:15–19 and ADR-0013:5,11; J1/J11 route/authority absence in `E/I02.json`; not authority for open mode |
| [#3](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/3) | OPEN | acceptance-only | J10 dispatcher capacity remains unaccepted: WP6 4x600 only 2/4 finalized with contention/pauses, no eight-session probe. WP15 repairs Stop lease but supplies one 600 s run, not four. `prototypes/capacity-campaign/run.py`; `E/I03.json` on final SHA. |
| [#4](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/4) | CLOSED | historical-closed | Shell/assets/fonts/build retained; `/studio`/`/live` retention superseded ADR-0012:15–19; J11 `E/I04.json` |
| [#5](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/5) | OPEN | acceptance-only | WP3 capture cleanup/rate checks; WP10 `tests/test_live_zero_span_dispatch.py` (9 guarantees) repairs guard placement; WP14 expired-lease wording. `ControlPanel.captureFailure.test.tsx`; hidden-tab capture and physical echo still missing; `E/I05.json`. |
| [#6](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/6) | CLOSED | historical-closed | No demonstrated authority to retire all speaker-journal criteria; retain historical record, adjudicate mapping in `E/I06.json`; no Phase-1 journal import under ADR-0012:18–19 |
| [#7](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/7) | CLOSED | historical-closed | J2/J4 rendering, provisional and export behavior; exact old mechanics need authority before superseding; `E/I07.json` |
| [#8](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/8) | OPEN | acceptance-only | WP4 safe causes + WP16 zero-audio/upload admission + WP18 truncation notice. `test_file_failure_reasons.py`, `test_file_digital_silence.py`, `test_file_truncation_notice.py`, `fileUpload.test.ts`; real 16-case WP16 evidence. Preserve browser picker/progress/no-resume obligations; `E/I08.json`. |
| [#9](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/9) | OPEN | implemented-awaiting-integration-evidence | Moved from needs-fix: WP11 fixes labels/order/max-end and persists source_lane; 50/50 `test_export_oracle.py`, WP14 five formats each 6/6 turns, WP16 50/50 downloads. Final candidate export/audio binding still required; `E/I09.json`. |
| [#10](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/10) | OPEN | keep-open-needs-fix | J1–J12 parent: WP17/WP20 0/2 quality cases; pending WP12 Stop acceptance/WP22 memory; D3/D5/P3/P4 and attended/provider/capacity evidence outstanding. Index child records and actual final driver bundle in `E/I10.json`. |
| [#11](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/11) | CLOSED | superseded | Google/email/schema-v1 identity replaced ADR-0013:5,11; secure credential, restart, 401/404 ownership survive; J1 `E/I11.json` |
| [#12](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/12) | CLOSED | historical-closed | J5 file durability plus WP16 admission/silence, WP18 notice, WP19 album. `test_owner_bound_file_meeting.py`, `test_file_album_acceptance.py`; 31->3 IDs on retained 30-minute corpus, not broad accuracy. `E/I12.json`. |
| [#13](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/13) | CLOSED | historical-closed | J2–J4 lane persistence/Stop: `test_live_lane_decode.py`, `test_live_service_replay.py`, `test_owner_bound_live_meeting.py`, WP15 `test_accepted_stop_lease.py`; WP14 quality failures remain. `E/I13.json`. |
| [#14](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/14) | CLOSED | historical-closed | J5 WP16 real URL failure/browser evidence: 404/HTML/timeout reasons, 16/16 foreign-owner refusals. `test_multi_file_url_meetings.py`, `test_file_failure_reasons.py`; video MP4 unmeasured. `E/I14.json`. |
| [#15](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/15) | CLOSED | historical-closed | J1/J4 WP9 saved rename through `test_saved_speaker_naming.py` and `savedNames.test.ts`; WP14 reload/export journey. Same-profile persistence remains; no cross-profile recovery. `E/I15.json`. |
| [#16](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/16) | CLOSED | historical-closed | J6 file MP3 custody/cleanup/foreign download; `E/I16.json` |
| [#17](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/17) | CLOSED | historical-closed | J6 WP15 Stop authority handoff: `test_accepted_stop_lease.py`, 12-case matrix and 8/8 prototype; unpaused 600 s saved MP3 exact 600 s. Real 1800 s/57.6 MB tape-edge acceptance still absent. `E/I17.json`. |
| [#18](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/18) | CLOSED | historical-closed | J9 workspace revocation/fences retained; Sign-out UI superseded ADR-0013:5; `E/I18.json` |
| [#19](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/19) | CLOSED | historical-closed | J9 content-free operator status/journal with new outcome/guard fields; `E/I19.json` |
| [#20](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/20) | CLOSED | historical-closed | J9 late-result/queue interruption and transcript/audio custody; `E/I20.json` |
| [#21](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/21) | OPEN | implemented-awaiting-integration-evidence | J11 legacy source/config/deployed-route absence; browser identity under ADR-0013; `E/I21.json` |
| [#22](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/22) | OPEN | acceptance-only | J9/J10 cumulative same-SHA core bundle; separate Wave-1 release superseded ADR-0013:7,11, failed bundles retained; `E/I22.json` + driver verdict |
| [#23](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/23) | OPEN | acceptance-only | J1/J2/J12 WP13 `test_tls_preparation.py`, `test_tls_renewal.py` establish local preparation only. Historical 7861 client trust FAIL; installation/renewal/attended Chrome/restore unexecuted. `E/I23.json` + actual host/cutover records. |
| [#24](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/24) | OPEN | implemented-awaiting-integration-evidence | J7 WP9 saved naming; WP17 observation lifetime fix, four API recognition routes 3.5264–3.5283 s. `test_saved_speaker_naming.py`, `test_live_lane_decode.py`; real browser/AEC mic <=4 s acceptance still needed. `E/I24.json`. |
| [#25](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/25) | OPEN | implemented-awaiting-integration-evidence | J7 WP7 known 2/2, unknown 2/2 CPU subset; WP17 four lane recognition routes; WP19 explicit File enrollment. `test_voiceprint_matching.py`, `test_file_album_acceptance.py`; full compatible-bank/corpus and attended unknown-abstention remain. `E/I25.json`. |
| [#26](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/26) | OPEN | implemented-awaiting-integration-evidence | J7 `test_voiceprint_bank_operations.py`, WP7 deletion/re-enrollment/pending eligibility; WP9 saved labels and WP19 File enrollment do not imply automatic enrollment. Final same-candidate browser evidence remains; `E/I26.json`. |
| [#27](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/27) | OPEN | acceptance-only | J7/J10 cumulative G8 on same candidate; only separate release sequencing superseded ADR-0013:7,11; preserve failed bundle criterion; `E/I27.json` + driver verdict |
| [#28](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/28) | OPEN | acceptance-only | J8 `test_final_summary.py`, `FinalSummary.test.tsx` cover local schema/UI. `verify_summaries.py` requires real Flash Lite on 50/180 s and source review; WP4 0 paid calls, WP14 summary row skipped. Key-required functional check still blocked; `E/I28.json`. |
| [#29](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/29) | OPEN | implemented-awaiting-integration-evidence | J8 existing retry/cancel/title/privacy tests retained (`test_summary_provider_paths.py`, `test_llm_relay.py`, `FinalSummary.test.tsx`); local passes do not measure live provider or four-live coexistence. Limited configured-relay authority only; `E/I29.json`. |
| [#30](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/30) | OPEN | acceptance-only | J8/J10 same-candidate cumulative G9, labelled transcript, real provider/fallback and four-live coexistence; failed bundles retained, only separate sequencing superseded ADR-0013:7,11; `E/I30.json` + driver verdict |
| [#31](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/31) | CLOSED | historical-closed | Old-service quiesce prerequisite stays historical; rollback archive retains it while final product removes it; J12 `E/I31.json` links actual historical/cutover evidence |

## Disposition changes and closure boundary

- **F1 — #9:** needs-fix -> implemented-awaiting-integration-evidence. The independent
  export oracle now handles lane labels, ordering and merged end times; final-SHA binding remains.
- **F2 — #5/#8:** implemented-awaiting-integration-evidence -> acceptance-only for the
  scoped capture/failure repairs, backed by WP10/WP14/WP16/WP18. Hidden/physical capture
  and final-candidate acceptance remain explicit residual obligations.
- **F3 — #10/#24/#25:** retain open status. Quality misses, attended/browser recognition,
  full corpus and resource acceptance cannot be inferred from repaired local controls.

The 31 rows preserve the supplied OPEN/CLOSED snapshot. No tracker closure is requested
or performed. File identity repair is accepted locally/merged; physical voiceprint quality
and summary semantic correctness still require their own witnesses.

## Ledger corrections — proposed checklist, not applied to source ledger

`ledger-audit.md` §§4–5 is the authority for these corrections. All boxes remain open
until lead reconciles the original ledger; this worktree may not modify it.

- [ ] **L1:** Replace R05's copied G7 text with sample-rate mismatch evidence; valid 200,
  mismatch 4xx/no sequence advance. Replace R06's generic pass with stale-fixture failure
  then WP4 exact corrected latency-test result; preserve the failed attempt.
- [ ] **L2:** Replace unrelated mappings: I05-AC06 → no debug counters in product UI;
  I07-AC08 → prefix-hash transport; I01-AC10 → raw-artifact verdict; I04-AC01 → build/fonts.
- [ ] **L3:** State real G0–G10 predicates and specific tests/evidence, remove G0/G10
  identical filler; link duplicate gate/parent rows instead of independent proof claims.
- [ ] **L4:** Replace 19 vague pointers, add test nodes where meaningful; separate measured
  pass/fail/unmeasured from disposition. Remove release-proof requests from 13 EXCLUDED
  rows; exclusions need authority and scope verification, not a passing live campaign.
- [ ] **L5:** Mark I10-US02 and I10-D18 superseded per ADR-0013:7,11; resolve I10-D02
  carefully: Sign-out UI superseded, revocable workspace credentials retained.
  Reconcile I22/I23/I27/I30 headers and I22-AC05 with their partially superseded criteria.
- [ ] **L6:** Restore I10-T06 durable meetings; ADR-0013 does not supersede durability.
  Restore failed-bundle preservation in I27-AC04 and I30-AC05; only wave sequencing retired.
- [ ] **L7:** Do not blanket-replace #8; carry AC04 upload progress/no resume and AC07
  browser pickers. Map old jobs/studio mechanics to ADR-0012:15–19 explicitly.
- [ ] **L8:** Supply missing authority or retain unresolved: #6 speaker journal;
  I07-AC01/02/03/09 exact mechanics; I10-D05 TLS live reload; I10-D16 inline summary;
  I10-X06/open workspace/R11/F11. D3 is not settled by existing code.
- [ ] **L9:** Reconcile limited relay authority ADR-0011:34–69 with ADR-0013:9 and plan D5;
  record MP3 amendment ADR-0010:14–16; preserve #31 historical authority and PRD exclusions.
- [ ] **L10:** Replace broad F7/F8 fan-out with discriminating findings/evidence; classify
  all 89 non-ACTIVE rows consistently without treating 359 inventory rows as 359 experiments.

Also add omitted obligations from audit §7: J1 first tabs/cookie loss/schema refusal;
J7 duplicate names; J8 blank settings/relay discovery/timeout; J11 phone layout/sentinels;
J12 DNS issuance/renewal, exact isolated process, restore/post-user-data rollback/cold boot;
ADR-0014 named exceptions; existing network/same-tab/default-enrollment and latency
journeys. Preserve their exact existing bars. These additions are inventory work, not
permission to deploy or rebuild already tested features.

## Open decisions and failure boundaries

Decision codes here use the **2026-09-17 review**, not older plan D-numbers.

| Code | Still needed | Decision consequence |
|---|---|---|
| D2 / P3 | Predeclared per-lane retention/error bar and comparison population, informed by WP1 data | Report ordered WER/reference extent and controls now; do not invent an acceptance threshold after measurement |
| D3 | Open/shared workspace: internal convenience or supported product mode? **UNDECIDED** | If supported, requires authority amendment, mode-aware copy and isolation-vs-sharing evidence; code/env flag alone grants no product scope |
| D5 | Whether N1 cause-bearing file/URL failure is release-blocking | WP4 implements regardless; decision governs release gate, not whether unexplained failure may be counted as success |
| P2 | Physical speakers/AEC measurement and G7 scheduling | Headphones and speakers are both required; scheduling is not waiver or automated attendance |
| P4 | If speakers leakage remains unmitigable, permitted fallback | Mono fallback would change scope and risk losing quiet speech; no automatic fallback authorized |
| P5 | Confirm same-lane simultaneous-speech exclusion/limits | Independent source lanes solve cross-lane overlap only; do not infer same-lane separation quality |

Provider choice is settled as Flash Lite plus configured fallback. Numerical summary
reliability tolerance/population and semantic-read acceptance still need recording; the
older review's proposed ≥30 attempts/≥3 transcripts/≥3 source reviews is a proposal,
not a newly authorized numeric gate. Lost speech, wrong speakers, unreliable summaries
and lost durability cannot be deferred as performance. Remaining production failures
must be fixed or explicitly adjudicated; missing measurements stay unmeasured.
