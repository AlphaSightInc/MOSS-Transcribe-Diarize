# Row 10 — first enrolled voiceprint match: PASS under approved derived budget

## Structural contract

Question: when is a named voiceprint match first possible, and which interval actually delays its visible label? Primitives: captured PCM, frozen causal span, decoder-attributed speaker intervals, embedding, canonical identity, private-bank match, durable publication, rendered label. Each boundary has a distinct owner; raw audio cannot be assigned a canonical speaker before its identity preparation without a new association rule.

Invariants: album_admission_seconds=2.0, birth_min_seconds=1.0, causal min_match_score=0.35 and min_match_margin=0.1 remain unchanged. Bank matching's separate 1.0s/0.46 rule and provisional rejection also remain unchanged. No automatic enrollment from matches; no cross-owner names; no raw vectors in timing logs. Original local stack/database untouched.

Unknown: whether any eligible observation waits for bank matching, or the first observation itself arrives late. Falsifier for an eager-bank fix: the first committed observation already produces the saved name immediately. Tools: real row-10 Chromium run, runtime event timestamps, named snapshot arrival, production encoder timing, isolated scheduling prototype if justified. Diagnose/prototype skills continue from earlier tasks.

## Code trace — established before edits

1. Browser supplies negotiated 8000-sample (500ms) frames. `live_mixer.py::_sealed_frontier_ns` normally waits for a successor frame to seal a lane interval using timestamps. This adds roughly one frame of capture staging. Lane clock alignment and gap handling are separate correctness obligations.
2. `live_endpoint.py` freezes speech at silence endpoints or the deployed 40000-sample (2.5s) cap. `live_coordinator.py::prepare_work_item` decodes the frozen span before identity scoring; no original speaker intervals exist before that decode. Queueing/processing are timed in runtime events.
3. `WeSpeakerLiveEvidenceProvider.score` embeds the decoded speaker intervals. Birth requires 1s; 2s is the enrollment-album gate, not the bank-match gate. Album reconciliation occurs at the next preparation; a 60s meeting-time retrospective sweep repairs canonical labels, not private-bank names.
4. `match_observations` reads the original pending vector against the just-committed canonical assignment, explicitly emits `provisional=False`, and does not wait for album admission/reconciliation. Existing test `test_causal_match_observation_preserves_original_one_second_unit_without_reembedding` already proves the 1s path.
5. Runtime publication callback `_observe_raw` pins immutable causal observations; `_publish` invokes `phase2_speaker_identity.publication` and `match_voiceprint` before publishing that very snapshot. There is no bank-match interval or sweep gate. A committed first observation with >=1s eligible speech can match immediately, even with no album exemplar.
6. Bank reads/link changes/durable transcript commit precede label revision notification. Browser polls snapshots and applies the separate speaker-label revision. Current source polls every 100ms during capture; the old stack uses 250ms.

## Measurements so far

- Original stack `https://127.0.0.1:17861`, checkout b76b5b5c: row 10 repeated at **4.346s**, bank contains fixture-label-2; first canonical queued ~3.10s after create, queue wait 0.758ms, processing 547.99ms including decode 148.96ms. First observation matched; no sweep ran. Earlier retained 10.845s is not a repeatable fixed scheduling interval.
- User-authorized isolated stack `https://127.0.0.1:17863`: copied run_local_stack.py, own state/control paths under `/tmp/moss-row10-stack`, same cert and vLLM tunnel, current worktree source. Existing 17861 state untouched. New workspace enrolled fixture-label-2 from 18s capture; enrollment reports `enrolled`.
- Current source before product edits: legacy row-10 wait reports **4.338s**. Runtime first span queued at 3.1303s, queue wait 0.152ms; processed at **3.9428s**, including 432.16ms decode and 380.19ms remaining preparation. First named snapshot received at **3.953s**, about 10ms after commit. Evidence disproves delayed bank matching.
- Locator polling added about 385ms beyond the already-named snapshot in that run. Harness now timestamps the visible DOM mutation using MutationObserver rather than timing when Playwright's locator polling wakes. It retains the same Start-click/visible-name metric and threshold.
- Real encoder probe (`hash_probe.py` / `hash-results.json`): each embedding re-verifies the 79,158,228-byte asset. Hashing costs ~34ms of ~343ms total. A throwaway stat-keyed reuse reduced warm total to 307ms with identical vectors. This is too small to explain row 10; no production hash-cache change selected.

Fresh-workspace harness issue fixed: `.get(key, mapping['live'])` evaluated its fallback eagerly, raising KeyError even when enrollment_live existed. Initial short enrollment also remained pending; the measured isolated workspace uses explicit successful enrollment after 18s. A same-browser second capture hit `Invalid state`; measured repeats use fresh browser contexts with the same saved workspace cookie, matching the original row-10 protocol.

Policy versus scheduling: the four named identity thresholds are fixed. Queue, encoding I/O, bank publication and browser polling are plumbing. The 2.5s first decode boundary and successor-frame sealing dominate arrival time; changing either must preserve canonical geometry or be explicitly reported as a changed decode/capture rule, not disguised as an eager bank-match fix.

## Corrected browser measurements and verdict

| Source / first decode cap | Visible name from Start click | Verdict |
| --- | ---: | --- |
| Unmodified current product / 2.5s | 3.7007s | FAIL |
| Throwaway first-boundary prototype / 2.0s, first trial | 4.1140s | FAIL |
| Same prototype / warm repeat | 3.2926s | FAIL |

These are individual real runs, not latency percentiles. The first prototype trial spent 1.078s decoding; the baseline spent 0.160s. The shared upstream prevents attributing the entire wall-clock difference to scheduling. The repeat proves that an earlier eligible original observation can match without changing any identity threshold, but does not prove <=3s reliability.

Retained evidence: `evidence/voiceprint-first-match-20260911/`, with five labelled run directories containing row verdicts, screenshots, runtime events, and available matched snapshots. `timing.jsonl` retains the timing/label fields needed to reconstruct the boundary trace. The row JSON's original `network.jsonl` reference points to the temporary full run; the retained derivative is `timing.jsonl`. Browser cookies/storage-state files are deliberately excluded.

Validation: `.venv/bin/python -m pytest tests/phase2/test_voiceprint_latency_measurement.py tests/phase2/test_voiceprint_matching.py tests/test_live_provider_bundle.py -q` — **50 passed**. The new optional-browser test deliberately delays the reader by 800ms while inserting the label at 200ms; the reported latency remains tied to the DOM mutation. Existing production tests cover immediate one-second matching and private-bank publication. No product identity or quality-policy values changed.

**Current verdict:** the bank-trigger hypothesis is false. A second match trigger would duplicate working code. The limiting path is capture sealing → first decode → embedding. A scope clarification is pending on advancing the first decode boundary under the user's no-policy-change instruction; no geometry change is shipped in this diagnostic checkpoint. Row 10 is not closed.

## Original 10.845s trace and conversion check

The integration rebase supplied the original session's retained event projection, `docs/audits/row10-recognition-events-20260912.json`, and the read-only trace `row10-recognition-readonly-20260912.md`. The original first runner call took **7.068335625s**, within **7.438577042s** canonical processing; the second runner call took **0.147940375s**. Thus the exceptional original delay is inside the runner boundary, not a periodic voice-bank trigger. That boundary includes local media conversion, HTTP waiting, and streamed response consumption; the old trace cannot isolate them further.

A fresh Python process converting the exact first 40,000 samples of the same corpus through production `_media_to_wav_bytes` took **0.662572s**, then **0.000479s** and **0.000313s** on repeats (80,044-byte WAV each). See `evidence/voiceprint-first-match-20260911/conversion-timing.json`. Local first-use initialization is measurable, but this run does not explain the historical seven-second runner call. No speculative server warm-up, conversion bypass, or policy change was added.

Checkpoint `01cf62ea` was pushed to private/auto-mvp-0911 after rebase. The timing regression also passed after integrating the other agents' harness changes. The queued G9 acceptance-selector/relay-qualification task remains next, after the row-10 scheduling-scope decision.

## Approved resolution

The operator explicitly retained all decode boundaries and identity policies and replaced the estimated 3s target with **4.0s**: 2.5s first canonical cap + approximately 1.0s decode/identity + 0.5s frame/poll allowance. This is a regression budget, not a guarantee against provider stalls. The harness measures Start click, conservatively earlier than captured speech onset; passing this stricter clock also passes the speech-onset bound.

The retained unmodified-product 3.7007s run is **PASS** under this approved criterion. The original 10.844687s run remains **FAIL**, including its 7.068336s runner stall. The operator attributed that stall to shared-tunnel/vLLM contention; the retained runner timer independently establishes the delay but cannot separate conversion, transport, and upstream execution. Historical row JSONs preserve their original 3s verdict; `approved-verdicts.json` records re-evaluation without rewriting history.

Every future row-10 run now writes `row-10-decoder-events.json`, preserving runner timing alongside the browser verdict. The host's four-session gate continues retaining its own runtime observations; no host test or restart was performed here. No earlier-decode production change was made. The isolated prototype server was stopped; its separate database remains intact.

Verified four-session retention: `phase2_acceptance_external.py::_run_live_load` retains per-session diagnostic events; `_DIAGNOSTIC_PAYLOAD_FIELDS` already includes `canonical_decode_elapsed_sec` and `frozen_span_duration_sec`. No additional instrumentation or host operation is needed to expose a repeat stall under the gate. Full local validation with the G9 follow-up: 1,393 Python passed, 2 optional corpus skips, 37 subtests; 201 frontend passed.
