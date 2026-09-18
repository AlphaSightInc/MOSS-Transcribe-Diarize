# WP22 memory investigation — interim measured verdict

Structural question: which owners grow with meeting duration, and which retain memory
once their work is over? Primitives: pending audio (uncommitted work), bounded complete
tapes (terminal input), transcript/identity history (later correction), native encoder
workspace (replaceable inference implementation). These have different lifetimes.
Invariant: identical frame protocol, audio, transcript, identity vectors, policy values,
and lifecycle behavior. Unknown: real decoder content and 30-minute throughput until WP12.
Falsifier: Python owners plateau while RSS grows; any changed vector/transcript or substantial
inference regression rejects an allocator intervention. Current RSS is not historical peak.

## Prototype verdict before production edit

The 30-second smoke produced ~57 MB live Python allocations after terminal release but
1,554,481,152 bytes RSS. All three tapes were empty, all pending PCM slices empty.
Its deliberately simple initial stub emitted one 30-second terminal segment; that case
is retained as a stress witness, not called representative meeting content. Subsequent
meeting profiles split stub output into <=2.5-second segments, with real public speech,
production VAD/ONNX identity and production ingress/mixer/coordinator/runtime.

Native intervention: the same pinned production `_OnnxWeSpeakerEmbedder` and public
Bill Ackman audio, one option changed per arm. No production code changed for experiments.

| Case | Default RSS at end | No memory patterns | Vector equality | Total inference seconds |
|---|---:|---:|---:|---|
| 18 calls: 2.5/10/2.5/30/2.5/10 s, three repeats | 1,451,147,264 | 995,377,152 | 18/18 exact | 28.061 / 27.894 |
| 80 calls: 40 lengths 0.5..9.743 s, two repeats | 871,596,032 | 664,567,808 | 80/80 exact | 64.774 / 64.624 |

Rejected: disabling CPU arena (1,790,558,208 bytes) and per-call arena shrinkage
(1,453,654,016 bytes) did not improve the 18-call stress case. These designs are not shipped.
Accepted candidate: disable shape-specific memory-pattern caching; preserve CPU arena,
model, features, output, threading and all policy values. Measured native retention reduction,
not a claim that all process RSS returns to cold startup. Libraries/model remain loaded.
The ONNX documentation explains persistent arena allocation and the separate pattern option:
https://onnxruntime.ai/docs/get-started/with-c.html
https://github.com/microsoft/onnxruntime/blob/main/include/onnxruntime/core/session/onnxruntime_session_options_config_keys.h

Regression before fix: 1 failed (old encoder leaves memory patterns enabled), 1 passed
(720 two-lane 2.5-second spans; working buffers equal at 5/15/30 minutes; tapes empty at
release; all 1,440 transcript segments survive). Full baseline: 1,889 passed, 2 skipped,
37 subtests; frontend 244 tests / 27 files passed.

## Commands and scope

Use COMMON Python with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` and cwd this worktree.
`python prototypes/streaming-diarization/memory-longrun/memory_profile.py --output evidence/mvpfix/wp22/lanes-before.jsonl`
`python prototypes/streaming-diarization/memory-longrun/onnx_memory.py --arena no-pattern --varying --output evidence/mvpfix/wp22/varying-no-pattern.json`
Mono comparison runs the identical profile script from `.wp22/base` (`git archive 37979e53`).
Its old decoder adapter is selected explicitly; all imported production code is from that archive.
The manual scheduler eliminates decoder backlog but preserves frame size, timestamp progression,
VAD partitions, rolling and terminal lifecycles. Snapshots are every 30 audio seconds, with
tracemalloc allocation attribution every 300 audio seconds. No network/GPU. Draft off, as WP15.
Only the decoder is stubbed; HTTP, persistence and MP3 encoding are excluded from this profile.
Scratch/audio/vectors under `.wp22`; no audio or vectors committed. A probe tests before/after
Stop with the runtime still retained, so process exit cannot masquerade as release.

Failed setup attempts: `from_path` was not the manifest API; corrected to `from_manifest`.
The base archive predates `bounded_live_inference`; selected its existing RunnerBoundedWavInference.
Tracebacks retained. Automated scripted progression replaces the interactive TUI to measure
long sessions reproducibly. Bench retained rather than shipping prototype logic.

All three uncached 30-minute profiles completed; the owner table is
`evidence/mvpfix/wp22/OWNERS.md` and exact machine-readable results are in
`profile-summary.json`. RSS at 5/15/30 minutes (bytes):
- mono base: 572194816 / 626425856 / 647659520;
- lanes before: 623689728 / 662274048 / 667467776;
- lanes after: 569327616 / 617299968 / 623951872.
All accepted/committed 28,800,000 samples; all PCM/tapes released after Stop.
Before/after content matches exactly: 1,440 segments, 4,320 stub words.
After-Stop RSS remains 641,908,736 bytes with runtime/model/profiler alive;
this is native retention reduction, not a universal RSS or cold-baseline claim.
The user has now confirmed WP12 and authorized merging integration tip 1745b96f
before Part C, with 2,600 total requests and contention recorded without pausing.
Fresh verification remains pending until the merged-tree real run and full suites.

## Test-attempt adjudication

The focused two-file run reported 55 passed / 2 failed: existing draft tests import
`tests.phase2.test_owner_bound_live_meeting`, whose sibling `_browser_workspace_fixtures`
is not on pytest's path when that directory was not collected. Full baseline collects
it and passes. No fixture source was changed; focused rerun includes a Phase-2 node.

First full post-change run: 1,889 passed / 1 failed / 2 skipped / 37 subtests.
`tests/phase2/test_owner_bound_live_meeting.py::test_helper_lease_loss_interrupts_without_client_terminal_request_and_never_resumes`
sets a real 0.03-second lease, then sends six HTTP frames without heartbeat. It expired
before the sixth frame (HTTP 409; retained log explicitly names helper_lease_expired).
This test uses stub Identity, never the edited ONNX encoder; baseline suite passed it.
No lifecycle source or test timing changed. A targeted rerun and final full suite must pass.

Supplemental publication probe's first import failed because `profile.py` shadowed Python's
stdlib profile module through cProfile/torch. Renamed benchmark to `memory_profile.py`.
Original memory runs loaded it earlier under __main__; their measurement logic is unchanged.

Selected focused rerun (including Phase-2 fixture collection): 58 passed. The existing
30 ms lease test passed unchanged. HTTP/SQLite supplement completed 1,800 audio seconds
in 63.091 wall seconds, with a completed saved meeting and empty publication queue at
all sampled frame-pair checkpoints. Final public snapshot 608,173 bytes, event projection
62,013 bytes, durable transcript 690,248 bytes. This supplements, rather than replaces,
the real-encoder profile; it uses fake identity/ASR and always-speech VAD.

Final full suite before fresh verification: 1,890 passed, 2 skipped, 37 subtests (147.03 s).
Frontend: 244 tests / 27 files; typecheck and build exit 0, assets unchanged.

Exact album-entry supplement: original ownership counter counts speaker banks.
`album_counts.py` replays the same real PCM and policy, caching embeddings only for
byte-identical WAV + intervals; each unique input is computed by the pinned ONNX model.
Only entry counts and exact transcript equality are used from this supplementary run.
Its RSS/byte estimates are excluded because memoization changes ownership/allocations.
This avoids falsely calling bank counts exemplar counts.

## R1 — pre-existing terminal tape-refusal defect (outside memory fix)

The per-lane empty-results path calls `TerminalTranscriptFinalizer._refused` without
its required keyword-only `gaps`. Two exhausted lane tapes therefore yield TypeError
and generic `failed`, not the intended `tape_unavailable`. The mono base reports
`unavailable`. The runtime's finally block still releases all tapes. Reproduced with
two 2.5-second frames and one-frame tape capacity, no ONNX/model involvement; exact
error in `evidence/mvpfix/wp22/tape-refusal-defect.txt`. The same omitted argument is
present in the accepted integrated WP12 tip 1745b96f; the merge does not fix it.
No change to WP12-owned terminal mapping/lifecycle code in this memory package.
The full 30-minute per-lane bounded-tape profiles must report this failure explicitly,
not relabel it successful finalization. Part C still needs its authorized larger tape.

## Integrated WP12 gate

Merged authorized integration 1745b96f, preserving both branches' appended tests/docs.
Removed inherited stray conflict-marker lines from .gitignore; retained all ignore rules.
Before Part C: full Python 1,911 passed, 2 skipped, 37 subtests (149.16 s); frontend
249 tests / 28 files, typecheck and build pass. No generated asset change. The imported
WP12 historical failure logs contain whitespace; left upstream evidence unchanged.
WP22's production diff versus integration remains only the four encoder lines.
