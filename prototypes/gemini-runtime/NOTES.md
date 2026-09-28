# Gemini runtime seam probe (pane P63)

## Contract before implementation

- **Structural question:** Can one session-local stream of mixed 16 kHz PCM and engine updates be published through the existing `LiveSession` snapshot authority without changing the HTTP/UI contract?
- **Minimum primitives:** retained audio position (absolute samples), engine update (preview, committed/revised, terminal), stable meeting speaker ID, session publication state. The position binds words to the tape; the update carries the only new provider output; the speaker ID is the UI-visible identity key; publication state owns lifecycle and revisions. Remove any one and either time, identity, or lifecycle becomes ambiguous.
- **Invariants:** input frames are retained before provider work; committed rows have absolute ordered sample bounds and canonical speaker IDs; a revision changes an existing visible row rather than duplicating it; Stop settles to `final` or a visible failure; sessions cannot share engine state; the existing snapshot/event schema stays intact.
- **Assumptions / unknowns:** `LiveSession` may require sequential frozen prefixes and reject rolling rewrites. Exact engine word source, window policy, speaker continuity, live latency, quality, and spend are unmeasured pending the bake-off. Voiceprint extraction from committed Gemini intervals may need a separate measured design.
- **Falsifier:** a scripted preview, commit, relabel, and terminal revision cannot be represented by existing `LiveSession` calls and consumed by the unchanged poller shape; or Stop cannot expose a failed finalization without hanging.
- **Tool decision:** inspect `LiveSession` and the current runtime/publication path to find the smallest seam. Run a one-command throwaway state probe against `LiveSession`; its acceptance/refusal counts decide whether to reuse it. Then use offline TDD through the runtime's public methods. Run focused existing tests only if they can detect an actual HTTP/runtime contract break.

## Hypothesis

`LiveSession` remains the snapshot authority. A thin per-session adapter converts engine updates to its publication calls; all capture, storage, and route handling stays at the existing runtime boundary.

## Verdict (one-command probe)

`PYTHONDONTWRITEBYTECODE=1 $RT.venv/bin/python prototypes/gemini-runtime/probe_session_seam.py` printed full `LiveSession` state after each action: prepared S00 base commit 1/1 accepted; first diarized rolling update 1/1 accepted; later correction to the same rolling interval 0/1 accepted (`not_at_frontier`). Thus unmodified `LiveSession` cannot show later Gemini identity repair. Choose the narrow new operation that replaces labels and segment boundaries over an already-owned rolling interval while preserving its exact concatenated text. Keep `LiveSession` as state and snapshot authority; no separate session document. The operation must reject changed words and intervals it does not own. A separate narrow speaker registration call is needed because the old identity preparer is tied to a MOSS decode.

The probe is throwaway; remove its script after the verdict is in the design doc.

## Counter contract (lead requirement)

- **Structural question:** Can a harness distinguish provider calls, retries, failures, timing repair, audio sent, and cost for each meeting without reading transcript or audio content?
- **Minimum primitives:** session ID as owner; cumulative counters by call kind and error/retry code; clamped/dropped timing counts; sent audio seconds; USD cost. These are the facts that alter quality, spend, or failure interpretation; no transcript, speaker label, audio, API key, or provider request body belongs here.
- **Invariants:** additive nonnegative deltas; sessions isolated; readout is a copy; every provider call records the audio duration and cost once; error/retry code names are stable metadata. A cached call records no audio sent and no cost.
- **Assumptions / unknowns:** actual Gemini usage metadata and anomaly denominators arrive from the phase-2 adapter. The fake can prove accounting and isolation, not provider truth.
- **Falsifier:** two fake sessions with different usage/error events cannot produce separate content-free totals and per-kind/per-code counts.
- **Tool decision:** a one-command in-memory aggregation probe prints both meeting states and rejects negative deltas; then an offline runtime test verifies the same behavior through the public diagnostics method. This changes the engine factory interface by one reporting callback.
- **Verdict:** the probe printed isolated states for 2/2 sessions: rolling calls 2 vs terminal calls 1; only the first session had a 429 error/retry and 1 clamped / 2 dropped words; audio and cost remained 10 s / $0.03 vs 20 s / $0.02. The production-path fake test passed with copied readouts and a content-bearing code rejected. The throwaway script was removed.
