# Gemini Live runtime seam — P63 phase 1

**Decision:** Keep the existing capture, Account meeting, HTTP, and browser layers. A
session-local Gemini engine consumes the mixed 16 kHz mono stream and publishes through
`LiveSession`, which remains the authority for samples, speaker IDs, revisions, and
finalization. The provider adapter is **not installed yet**; CLI selection fails before
startup until the bake-off picks its words and identity policy.

## Structural contract

**Question.** Where can provider output enter without changing who owns audio, the
meeting, or the displayed transcript?

**Minimum primitives.** (1) The accepted sample clock binds every word to retained
audio. (2) A per-meeting engine turns accepted audio into preview, base, rolling, and
terminal updates. (3) A stable meeting speaker ID lets the existing browser and
voiceprint bank refer to the same person. (4) `LiveSession` publishes one current
surface and lifecycle. None can be removed: without the clock words float, without
updates no provider result crosses the seam, without IDs relabels cannot be named,
and without publication state the UI cannot know what is current.

**Invariants.** Frames are accepted before the engine sees them. All update positions
are absolute sample indices of that mixed recording. Speaker IDs append in first-seen
order and never change meaning. A relabel preserves the exact concatenated published
text, including spacing. The committed sample prefix advances in order, and the
rolling frontier advances in order. A closed meeting has `final`, `failed`, or
`unavailable` finalization. Each meeting has its own engine and tape. The API route
paths and frontend display rules remain unchanged.

**Unknowns.** Real Gemini word timing, visible-word delay, diarization error rate,
window continuity, the number and geometry of later speaker repairs, and cost are
`UNMEASURED` here. Pane 6.1 and the bake-off decide them. The fake proves software
shape only. The WeSpeaker observation producer and real Google engine remain phase 2.
The shared Gemini parser at `bc567bb2` clamps invalid word offsets and reports
`timing_anomalies={clamped,dropped}`; P63 made zero Gemini calls, so per-call
anomaly rates are **UNMEASURED**. The phase-2 adapter must carry those counts into
its call receipts and report rates with call denominators.

**Falsifier and result.** A throwaway one-command `LiveSession` probe published an
S00 base span (1/1), published a diarized rolling row (1/1), then asked to relabel
that same interval. The latter was refused 1/1 as `not_at_frontier`. See
`prototypes/gemini-runtime/NOTES.md`. This falsified reuse of *unmodified*
`LiveSession`. The narrow `revise_rolling_interval` operation preserves words while
allowing one speaker row to split into two. Offline tests now show that change reaches
the browser parser. A measured live identity repair that requires changing words
would falsify this narrow operation and needs a separately authorized word revision.

**Tool choice.** The state probe tested the actual `LiveSession` rules, so its refusal
changed the seam decision. The deterministic fake exercises runtime publication with
zero API spend. The frontend poller test checks the actual parser, because a valid
Python dataclass alone cannot prove a browser can read the JSON. No real Gemini run
was needed to answer this software question.

## Seam and ownership

| Existing layer | Keep or replace | Code seam |
| --- | --- | --- |
| Account auth, meeting, SQLite, durable capture/MP3, v2 lane ingress and mixer, capture health | Keep | `phase2.py:2028`, `phase2_live.py:139`, `live_transport.py:420,467,603,624,642` |
| Live runtime selection | Choose once at composition root | `phase2_web_cli.py:24,103`; `--live-engine` defaults to `moss` |
| Session samples, canonical IDs, preview, rolling and terminal surface | Reuse `LiveSession`; add narrow speaker registration and rolling identity repair | `live_session.py:331,451,496,753,805,1039` plus `register_canonical_speakers` and `revise_rolling_interval` |
| MOSS VAD, 2.5 s endpointing, decode, causal WeSpeaker identity, rolling MOSS decode | Replace only on Gemini branch | `live_service_runtime.py:564-698`; Gemini implementation in `gemini_live_runtime.py` |
| Complete mixed tape | Reuse; full terminal read stays local until the chosen provider adapter sends public audio | `live_tape.py:120,352`; `gemini_live_runtime.py` |
| Browser snapshot/event consumer, speaker naming, exports, summary | Keep | `mossPoller.ts:654-717`, `phase2_live.py:1312-1339` |

`GeminiLiveRuntime` subclasses `LiveServiceRuntime` because Account capacity checks
use `isinstance` (`phase2_live.py:224`) and `active_live_session_count` reads
`_lock`, `_sessions`, and `state.session` (`live_service_runtime.py:2128`). It returns
the existing `LiveServiceSnapshot`, `LiveServiceEvent`, frame ack, and descriptor wire
types. The fake engine is injected per session; no provider import or key is used in
phase 1. A missing real engine makes `--live-engine gemini` fail fast at startup.
The refusal happens before the MOSS file runner is constructed, so this phase-1 CLI
cannot load the self-hosted model or GPU on a Gemini selection. Phase 2 must load
the provider key from `.env.local` or `MOSS_GEMINI_API_KEY` inside the composition
root, without logging it.

## Engine interface for the bake-off winner

`engine_factory(session_id, publish_update, report_usage) -> GeminiEngine`. The factory must create
one engine per meeting. `push_audio(start_sample, pcm16)` must enqueue the accepted
16 kHz mono samples promptly, without blocking frame ingress. It publishes any of:

| Update | Required fields | Publication meaning |
| --- | --- | --- |
| `GeminiPreview` | `end_sample`, unlabelled segments | Current fast-word suffix, beginning at `committed_samples` |
| `GeminiBase` | `through_sample`, unlabelled segments | Advance the ordered committed sample prefix, including silent empty spans |
| `GeminiRolling` | owned `[start_sample,end_sample)`, diarized segments | Append diarized rows from the current rolling frontier |
| `GeminiRelabel` | an already owned interval, replacement diarized segments | Repair speaker assignment or split/merge speaker turns, preserving exact text |

Each `GeminiSegment` has absolute `start_sample`, `end_sample`, `text`, optional
canonical `speaker` (`speaker-0001` onward), and optional `source_lane`. The engine
owns the mapping from a Gemini window-local `spk:N` to these meeting IDs; the
runtime never guesses it. `finish(tape)` awaits all live work and returns terminal
segments over the full retained recording. The provider adapter must use public
audio only, split final requests at ≤30 minutes, bound provider waits/retries, and
report 429/GoAway/unreachable as exceptions. Those choices are phase 2, after the
bake-off verdict. The engine must not read or write Account state.

`report_usage(...)` records **one actual provider request attempt** with `kind`,
optional `error_code` and `retry_code`, `clamped_words`, `dropped_words`,
`audio_seconds_sent`, and `cost_usd`. A cache hit reports no provider call.
`runtime.engine_diagnostics(session_id)` returns copied per-meeting totals:
`calls_by_kind`, `errors_by_code`, `retries_by_code`, `timing_anomalies`, audio
seconds, and USD. It is a harness/operator readout outside the frontend payload.
Only stable metadata codes are admitted; no transcript, voice vector, audio, key,
or provider body enters it (`CONTEXT.md:53-56`). The fake verifies two-session
isolation; real usage accuracy remains `UNMEASURED` until phase 2.
An engine may report a connection/setup call during construction; it must defer
transcript updates until after `create` returns and the first audio is accepted.

## Engine update to screen

| Engine update | Session call | Snapshot/event | Browser effect |
| --- | --- | --- | --- |
| Preview | `begin_provisional` then `publish_provisional` | `session.provisional`, `provisional_published` | Unlabelled S00 preview |
| Base words / silence | `freeze_until` then `submit_unlabeled_canonical` / `submit_empty_canonical` | `committed`, base `effective_transcript`, `canonical_published` | Fast unlabelled rows; silence advances accounting |
| Diarized rolling rows | `register_canonical_speakers`, `apply_text_revision(source="rolling")` | `identity_snapshot.canonical_speakers`, rolling `effective_transcript`, `text_revision_applied` | Confirmed S01/S02 rows |
| Later speaker correction | `revise_rolling_interval` | same effective rows with new IDs, version bumps, `label_revision_applied` | Existing rows relabel or split on next poll |
| Terminal rows | `apply_text_revision(source="terminal")` | full final surface, `finalization_status=final`, `terminal_finalization_completed` | Stop transcript replaced by final pass |
| Provider terminal failure | `note_finalization("failed")` | closed + failed, `terminal_finalization_failed` | Existing completed-meeting warning; committed words retained |
| Missing full tape | `note_finalization("unavailable")` | closed + unavailable, `terminal_finalization_unavailable` | Existing unavailable warning |

The poller requires `effective_transcript[].source_lane` to be omitted for mixed
mono, not serialized as `null` (`mossPoller.ts:700-705`). The Gemini snapshot
serializer omits it only when absent; system/microphone lane values stay intact.
The frontend itself is unchanged.

## Stop, voiceprints, and failures

**Stop.** The runtime advances any uncommitted tail as an empty base span solely to
settle the accepted/accounted sample invariant, closes the session, then marks
finalization `running`. The complete mixed tape goes to the engine's `finish` call;
a terminal revision owns `[0, committed_samples)` and replaces live rows atomically.
The tape is released afterward. The Account layer already waits through `running`
and persists the final document through `_transcript_document`
(`phase2_live.py:616-635,1312-1339`). Empty base spans do not assert that speech was
absent; the final pass must cover every accepted sample. If it fails, the existing
warning reports that final refinement failed and retains published live words.

**Voiceprints.** Gemini owns who-spoke-when. WeSpeaker still needs to embed audio
from Gemini-attributed intervals and publish `LiveSpeakerJournalObservation` with
`speaker_label` equal to the canonical meeting ID, 256-dimensional centroid,
sample seconds, provisional flag, encoder ID and state SHA (`live_provider_bundle.py:134,776-841`).
The Account naming flow reads `_identity_observations` and
`_identity_match_observations` under the runtime publication lock
(`phase2_live.py:550,586-587`). The phase-1 runtime returns empty observations and
advertises no compatible embedder; **cross-meeting auto-naming is not implemented
or qualified in this skeleton**. Phase 2 must create those observations from
diarized audio *before* terminal settlement; a final-only observation arrives too
late for the current Account live naming path. It must pin the existing WeSpeaker
encoder identity so stored voiceprints remain compatible.

**Failures.** A live engine/update error fences that meeting, produces a visible
terminal failure, marks finalization failed, releases the scratch tape, and leaves
other meetings active. A final pass error leaves the
meeting closed and sets `finalization_status=failed`; marking it interrupted would
send the Account layer down the wrong audio settlement path
(`phase2_live.py:1341-1353`). An absent/degraded tape sets `unavailable`. Provider
timeouts and rate-limit retry bounds are the real adapter's responsibility and
remain unmeasured; the fake proves raised-error handling, not 429 timing or recovery.

**R1 — fast-word delay versus retention.** `LiveSession` holds uncommitted frame
metadata until `GeminiBase` advances the prefix. The lead observed Live text arriving
at pauses as late as 45 s under automatic voice activity detection. A production
adapter that waits that long for base commits may hit
`descriptor.bounds.max_retained_samples` and refuse subsequent audio. The bake-off
must measure the chosen fast-word cadence against that bound and select a base
accounting policy before live qualification. Advancing empty base spans preserves
accounting but makes `publish_provisional` unable to preview words from before the
new committed prefix, so that trade-off must be measured, not hidden.

## Phase-1 evidence and next decision

- Backend fake: 9/9 focused tests for preview, base/rolling rows, relabel, terminal,
  two sessions, abort, live/terminal failure, degraded tape release, and CLI fail-fast.
- Frontend: 34/34 `mossPoller.test.ts` tests, including the Gemini snapshot shape and
  live speaker correction.
- Provider calls and spend: **0 / $0**. Quality, latency, and cost bars: **UNMEASURED**.
- Timing anomalies: **0 provider calls; clamped/call and dropped/call UNMEASURED**.

**D1:** After the bake-off selects the words source and continuity method, implement
its adapter against the engine interface above, add WeSpeaker observations, then run
real public-audio integration and existing Account/transport gates. If the measured
registry frequently changes words inside already revised intervals, revisit the
word-revision authority explicitly; do not silently route that through a label repair.
