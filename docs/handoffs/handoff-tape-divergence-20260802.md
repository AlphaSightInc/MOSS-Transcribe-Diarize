# Handoff: diagnose live/offline speaker-identity divergence

## Launch contract

Start the next session with:

```text
/goal Read docs/handoffs/handoff-tape-divergence-20260802.md in full and execute it as the controlling brief. Conduct the authorized bounded tape experiment, prove the precise root cause of the live/offline speaker-identity divergence, and produce an implementation-ready fix proposal plus a concise briefing for the analyst in tmux pane 3.2. Do not implement the production fix. Continue through independent adversarial review, remediation of evidence gaps, stress/repeat runs where needed, cleanup, and final requirement-by-requirement reporting. Stop only at a genuine human/TCC gate or when the objective is proved.
```

## Objective

Determine the precise causal root of the clause-11 divergence, not merely its location. Produce:

- A reproducible causal proof where changing one variable removes or restores the failure.
- A ranked and falsified hypothesis record.
- An implementation-ready fix proposal naming exact files, functions, invariants, regression-test seam, acceptance gates, and rollback conditions.
- A concise ready-to-paste briefing for the analyst in `Iter-Research:3.2`.

Do not implement, merge, push, or deploy the production fix in this goal. Throwaway diagnostic harnesses and narrowly tagged temporary instrumentation are allowed only when required for causal proof and must be removed or absorbed into the standing bench before completion.

## Explicit authorization and limits

The user explicitly authorizes one controlled live-corpus session with ADR-0003 retention enabled for diagnosis.

- Retention is limited to the diagnostic window and controlled session.
- Use a positive TTL long enough for replay, an explicit byte cap, and a secure ext4 root outside the checkout and outside the batch-runs filesystem.
- Confirm no unrelated live session is active before restarting or changing the live service.
- Do not edit the control-plane repository.
- Do not change TCC directly. Stop at any human permission gate.
- Do not copy raw tape audio into the repo, evidence bundles, logs, telemetry, or the capture Mac.
- Restore host configuration after capture, stop capture cleanly, reap/delete retained audio after all on-host replay measurements, and prove cleanup.
- Preserve only derived non-audio metrics, manifests with no audio payload, hashes, commands, and verdicts.

## Current evidence to refresh, not trust blindly

At the 2026-08-01 review:

- Deployed/live evidence was at `c2e6248fcf16ce21e170e1e299c3b53c08ba2438`.
- Live clause 11 was RED: 47.66% overall, David 1.35%, Ben 76.86%, final canonicals `[speaker-0001]`, no terminal sweep repair.
- Offline committed fixture reproduced locally at 91.3463%, live accuracy 84.5367%, six live canonicals, four final canonicals, four corrections, zero residual.
- Focused fixture+tape validation passed 39 tests with one external-corpus skip.
- F4b remained OPEN with no waiver.

Refresh exact SHA, service revision, host state, corpus hashes, thresholds, device topology, TCC, and artifact existence before using these facts.

Primary existing evidence:

- `/tmp/moss-final-c2e6248-evidence/f4b-disposition.txt`
- `/tmp/moss-final-c2e6248-evidence/real-c2e6248/speaker-diagnosis.txt`
- `/tmp/moss-final-c2e6248-evidence/real-c2e6248/speaker-final.json`
- `/tmp/moss-final-c2e6248-evidence/offline-c2e6248/clause11-fixture-verdict.txt`
- `/tmp/moss-final-c2e6248-evidence/offline-c2e6248/matching-diagnosis.txt`

Controlling design and code:

- `AGENTS.md`
- `docs/adr/0002-two-tier-diarization-fingerprint-album.md`
- `docs/adr/0003-live-session-audio-retention.md`
- `docs/design-streaming-diarization.md`
- `prototypes/streaming-diarization/NOTES.md`
- `moss_transcribe_diarize/app/live_tape.py`
- `moss_transcribe_diarize/app/live_transport.py`
- `moss_transcribe_diarize/app/live_service_runtime.py`
- `moss_transcribe_diarize/app/live_identity.py`
- `moss_transcribe_diarize/app/live_identity_album.py`
- `moss_transcribe_diarize/app/live_identity_sweep.py`
- `tests/fixtures/live_identity_real_corpus/README.md`
- `tests/live_identity_accuracy.py`
- `tests/test_live_identity_real_corpus.py`
- `scripts/ralph-afk/live-identity-real-corpus.py`

## Analyst context

Resolve bare `3.2` before capture. Expected target was `Iter-Research:3.2` / `%73`, but pane IDs and content are live state.

Use `tmux-peer` read-only at the start to capture the analyst's latest completed exchange. Never send keys or treat unsent input-box text as an instruction. At completion, provide the user a short briefing ready to paste into that pane; do not write into the analyst pane yourself.

The analyst's current hypothesis is directionally useful but overclaimed: a retained-tape replay is desirable, but one truth-driven offline replay is not a decisive binary split. The offline harness derives spans from ground truth and may inject cached embeddings; it does not reproduce live endpointer boundaries, ASR speaker intervals, mixer timing, concurrency, or identity snapshot ordering.

## Diagnose protocol

Use `$diagnose`. Do not skip the feedback-loop requirement.

### Phase 1: establish two baselines

1. Reproduce the deterministic offline result from the exact committed fixture and print full state: accuracy, per-speaker recall, canonical births/final count, corrections, residual, corpus/asset/config hashes.
2. Re-score the captured live artifact from raw snapshot/reference inputs, not its prose summary. Confirm accuracy, mapping, canonicals, status counts, and sweep changes.
3. Record 3-5 ranked falsifiable hypotheses before changing live state.

Initial ranking to challenge:

- H1: microphone bleed or dual-lane mixing alters the signal sufficiently to collapse speaker embeddings.
- H2: system capture/resampling already differs materially from the clean corpus before mixing.
- H3: live endpointer/ASR-local intervals select different evidence from the truth-derived offline intervals.
- H4: live identity orchestration, snapshot versions, commit order, or concurrency prevents independent birth.
- H5: configuration, binary, corpus, or scoring drift makes the comparison non-equivalent.

### Phase 2: capture one controlled tape

Use the exact failing five-minute corpus and reproduce the original topology unless a safety gate prevents it.

- Capture system, microphone, and mixed tracks plus the gap manifest.
- Record source revision, runtime hashes, thresholds, corpus/reference hashes, playback/session timing, device topology, volume, TCC, request/event ordering, session ID, and stop state.
- Use the existing tape tee points. Do not invent another audio capture path.
- Verify tape did not degrade, byte cap was not reached, sample counts and durations are coherent, and every gap is enumerated.
- Keep the tape on the server retention root only.

### Phase 3: perform differential replays

Run all measurements from the same retained session. Align reference timing explicitly using capture timestamps or measured cross-correlation; do not assume playback began at tape sample zero.

1. Signal differential: compare clean source, system tape, microphone tape, and mixed tape using derived metrics only. Measure duration, delay, level, clipping, silence/gaps, cross-correlation, resampling drift, system-to-mic bleed, and system-to-mixed distortion.
2. Truth-segmented identity replay: re-embed actual system and mixed tape PCM with the pinned production encoder using aligned ground-truth intervals. Do not reuse the committed NPZ vectors.
3. Post-mixer live replay: feed the exact mixed tape PCM through the actual live runtime/endpointer/ASR/identity path with production configuration and capture span boundaries, ASR speaker intervals, embedding decisions, births, abstains, base snapshot versions, commits, and sweeps.
4. Repeat the post-mixer replay at least three times. If results vary, raise reproduction rate and instrument ordering before concluding.
5. Where feasible, replay the two lane tapes through v2 ingress/mixer using recorded timestamps. State clearly that the tape reconstructs timeline but may not preserve original network-arrival interleaving.

### Phase 4: causal decision matrix

- System replay RED before mixing: localize to playback, system tap, conversion, resampling, or alignment. Manipulate the suspected transform and demonstrate red-green-red.
- System GREEN, mixed RED: localize to microphone bleed/mixer behavior. Demonstrate with system-only versus system+microphone using the same retained inputs.
- Mixed truth replay GREEN, post-mixer live replay consistently RED: localize downstream to span/ASR/evidence/identity logic. Compare the first decision where outputs diverge.
- Post-mixer replay GREEN while original live run was RED: localize to v2 ingress/mixer timing, concurrent processing, or state ordering. Use event order and snapshot versions to produce a deterministic high-rate repro.
- Replays vary: treat as concurrency/nondeterminism; do not select a policy fix until the failure rate changes under one controlled ordering variable.
- Any result invalidated by gaps, drift, wrong SHA, wrong topology, or config mismatch: mark REFUSED and rerun only after correcting the precondition.

Do not call a root cause proven until one intervention makes the original failure disappear and restoring the condition makes it recur, or an equally strong differential establishes the causal edge.

## Fix-proposal standard

After proof, write a surgical proposal containing:

- Exact root cause in one sentence.
- Evidence chain and falsified alternatives.
- Exact production files/functions to change.
- Minimal behavioral change and preserved invariants.
- Correct regression-test seam reproducing the real causal pattern.
- Red-before and expected green-after commands.
- Offline 9-clip and clause-11 non-regression gates.
- Required live canary and repeat count.
- Privacy, performance, and operational risks.
- Rollback trigger and rollback method.
- Explicit statement that F4b remains OPEN until the implemented fix is deployed and live clause 11 reaches at least 90% on a valid run.

Do not propose threshold tuning unless the experiment causally proves a threshold is the failing mechanism. Do not accept a unit-only green result as live certification.

## Evidence and cleanup

Store derived diagnostic artifacts in a new clearly named non-audio evidence directory. Record exact commands and return codes. Audio remains only in the declared server tape root until replay completes.

Before completion prove:

- Original offline and captured-live baselines remain reproducible.
- The causal intervention has repeatable results.
- Temporary `[DEBUG-...]` instrumentation is removed.
- Throwaway prototypes are deleted or absorbed into `prototypes/streaming-diarization/` with `NOTES.md` updated as required by `AGENTS.md`.
- Retention configuration is disabled/restored.
- Retained raw audio is reaped/deleted.
- No raw audio exists in repo, evidence, logs, telemetry, or the capture Mac.
- Capture stopped, outbox drained, TCC/device state restored, and services healthy.

## Required final report

Report findings first:

1. Proven root cause, confidence, and causal intervention.
2. Reproduction commands and measured red/green/red results.
3. Falsified hypotheses.
4. Exact fix proposal.
5. Remaining blockers and F4b status.
6. Cleanup/privacy proof.
7. Ready-to-paste analyst briefing for `Iter-Research:3.2`.

If the precise root cause cannot be proven, do not manufacture one. State the exact blocking evidence gap, what was tried, and the smallest next authorized measurement needed.

## Suggested skills

- `$diagnose` for the controlled reproduce-hypothesize-instrument loop.
- `$prototype` only if a throwaway differential harness is required.
- `tmux-peer` for read-only analyst context and final alignment.
