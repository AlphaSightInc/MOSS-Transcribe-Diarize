# Row 10 — recognition waits behind the first decoder call

Read-only diagnosis. Original session `0n3T5oKMSXbAHB7KlnyLdKp8`; browser recognition 10.844687 seconds. Read the existing local session events through GET only; no new session, inference, database reset, or host investigation. Source inspected in isolated clone at 0b3e6a2b; matching code also checked against branch 2b5eb340. The E2E audit records local server b76b5b5c, not a single pinned release for the entire campaign.

## F1 — Earliest recognition, and the three distinct policies

1. Endpoint freezes a span after sufficient silence or at the hard cap. The actual first span was 0–40,000 samples (2.5 seconds), reason `hard_cap`. [Endpoint logic](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_endpoint.py#L146).
2. Canonical decoding finishes, its speaker intervals are embedded, and the identity preparer assigns a session speaker. Births require at least 1.0 second of usable per-speaker evidence. Short/absent/ambiguous evidence can defer an identity beyond the first span. [Serial decode then identity](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_coordinator.py#L523), [embedding](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_provider_bundle.py#L618), [birth floor](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_provider_bundle.py#L668), [assignment](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_identity.py#L123).
3. The committed causal unit becomes a matching observation, explicitly marked non-provisional. It does not wait for a subsequent album reconciliation. [Projection](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_provider_bundle.py#L729).
4. Private-bank matching requires >=1.0 second, a finite compatible vector, a non-provisional observation, and cosine similarity >=0.46. Thus an already-enrolled presenter CAN match on the first qualifying committed span, even if that span has only 1–2 seconds of usable speech. This is not a guaranteed one-second wall-clock name. [Rule](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/phase2_voiceprint_match.py#L35).

The album admits individual exemplars at >=2.0 seconds; shorter valid evidence can be held provisionally, not simply accumulated until a timer expires. That enrollment gate is separate from live recognition. [Album](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_identity_album.py#L110).

The retrospective sweep runs every 60 seconds of meeting audio, invoked before preparation of the next span at/after its boundary; a final sweep also runs at Stop. It rematches past session identity evidence, not the private voice bank. [Cadence](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_identity_sweep.py#L83), [invocation](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_provider_bundle.py#L610). Neither 2.0 nor 60.0 explains this 10.845-second result.

## F2 — Original-session timing

| Stage | Measured |
|---|---:|
| First frozen span | 0–2.5 s audio |
| First canonical queue wait | 0.000173667 s |
| First runner call | 7.068335625 s |
| First total canonical processing | 7.438577042 s |
| Processing outside runner call, by subtraction | 0.370241417 s |
| Second runner call | 0.147940375 s |
| Second span queue wait, behind first | 4.934775167 s |
| Browser Start-to-visible-name | 10.844687167 s |

[Content-free original event projection](row10-recognition-events-20260912.json). First span was `submitted=true`, `identity_status=prepared`, `identity_reason=null`.

The runner timer encloses media conversion, HTTP transport/upstream waiting and response parsing; it does NOT isolate GPU inference. [Timer](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_adapters.py#L317), [runner stages](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/vllm_runner.py#L84), [HTTP call](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/vllm_runner.py#L180). Cold start, connection behavior, and provider contention remain alternatives. No claim that 7.068 seconds was purely GPU execution. The retained events do not timestamp the first successful bank match or DOM label, so exact attribution of the remaining wall time is unavailable.

## F3 — Observation to visible label

Each committed span emits `canonical_processed`; its callback captures immutable causal evidence while the snapshot is pinned, schedules the Account publication worker, and preserves event order. [Runtime](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/live_service_runtime.py#L1546), [capture](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/phase2_live.py#L557).

The worker first handles pending manual enrollment, then matches causal observations for active live publications (album observations only for completed terminal publication). It reads the owner's bank under a lock, preserves bank revision/authority/manual-name rules, persists links and transcript, then publishes the snapshot and notifies readers. There is no periodic matching timer. [Selection](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/phase2_live.py#L619), [matching](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/phase2_speaker_identity.py#L562), [durable publication](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/phase2_live.py#L647). Pending-enrollment observation returns immediately when no intent exists; it does not wait for album admission. [Early return](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/moss_transcribe_diarize/app/phase2_speaker_identity.py#L119).

Browser snapshot/events requests run in parallel; rendering waits for both. Active polling schedules the next request 250 ms after completion, so network/response/render time adds to that interval. [Poller](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/frontend/src/api/mossPoller.ts#L187), [interval](https://github.com/aiSight-us/MOSS-Transcribe-Diarize/blob/0b3e6a2ba72132b90b06758c2f79affece0589c0/frontend/src/api/mossPoller.ts#L12).

## D1 — Smallest proposed next change

Keep all identity values and rules untouched: 1.0-second birth and match minima, 2.0-second album admission, 0.46 voice-bank threshold, existing session matching thresholds/margins, 60-second retrospective sweep, and authority/manual-name precedence. Endpoint geometry also remains unchanged in this scope.

The fixable boundary is execution before the eligible observation: media conversion, HTTP/provider waiting, then ordinary publication scheduling and I/O. This trace locates the dominant delay inside the runner, but does not yet distinguish those causes. Propose only content-free elapsed timings at media conversion and HTTP completion in the shared runner as the smallest justified change. If a subsequent controlled comparison demonstrates first-request initialization, move a bounded warm-up into readiness before capture admission; do not assume warm-up fixes contention. No identity-policy change or speculative scheduling rewrite is warranted by this evidence.

No implementation, new inference, database reset, or host changes for this investigation.

Ownership transferred to agent 1.2 by the operator; this is the existing read-only analysis, not an implementation or a completed latency fix.
