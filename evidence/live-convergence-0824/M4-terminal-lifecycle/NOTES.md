# M4 step 3c — the terminal lifecycle: a meeting keeps its reader while its last listener runs

Campaign: live-mode convergence 0824, iteration 26. Branch `ralph/live-convergence-0824`.
Plan §12.3 (terminal behavior) + §7.3 (`finalization_status`) + §7.4 (the three
`terminal_finalization_*` events); decision **D-M4-3**, asynchronous finalization with the
existing snapshot polling model.

## The claim

**Production now gives a meeting its last listener, and takes nothing away to do it.** On the
trio, through the real runtime with a replayed decode: the stop request returns `running` with
the meeting's final accounting and *zero* terminal decodes issued; the surface a reader polls
during that interval is the rolling one it already had; when the pass lands the surface becomes
the paired file arm's, to `1e-12` on five axes; and the audio is released after the terminal
evidence is written, never before.

| arm | case | at stop | after the pass | WER at stop → after | file arm |
|---|---|---|---|---|---|
| healthy | `lex_bill_ackman` | `running` | `final` | `.198864` → `.159091` | `.159091` |
| healthy | `lex_javier_milei` | `running` | `final` | `.096000` → `.088000` | `.088000` |
| healthy | `lex_keyu_jin` | `running` | `final` | `.100719` → `.064748` | `.064748` |
| decode_failure | all three | `running` | `failed` | unchanged | — |
| no_tape | all three | `unavailable` | `unavailable` | unchanged | — |

The healthy numbers are iteration 25's `mapped` arm exactly. That is the point: **the lifecycle
costs the surface nothing.** What is new here is everything around the number — who runs the
pass, what a reader sees while it runs, and what a meeting is told when it fails.

## What this measurement is, and what it is not

It is **not** `G-M4-1`/`G-M4-2`: those are scored at the M4 exit on a fresh deployed pass with a
real decoder. This is the same arithmetic with the decoder held fixed — base decodes replayed
from the §10.2 grid's cache, the terminal decode replayed from the M2-exit pass's own
`file-hypothesis.jsonl` and re-rendered by production's `render_segments`. Zero MOSS requests,
no GPU, no service.

It **is** the runtime reading of `G-M4-6` (async lifecycle), `G-M4-7` (a failure preserves and
exports the rolling surface), `G-M4-9` (exactly one replacement), `G-M4-10` (release after
terminal evidence) and `G-M4-13` (no event carries transcript text), taken where those gates
actually live: in `LiveServiceRuntime.stop`.

**The deployed service is NOT yet on this build.** It still runs the M2 build with no tape
capacity declared, so every deployed meeting reads `not_started` — the pre-E4 posture. The
manifest's `bounds_config.max_tape_bytes` declaration and the restart belong to the next step.

## Gates (fixed before the run; nine, three arms × three cases)

| gate | reads | result |
|---|---|---|
| L1 `[G-M4-6a]` | the stop request does not decode: `closed`, `accepted == accounted`, zero terminal requests, `running`, one pass scheduled | PASS ×9 |
| L2 `[G-M4-6b]` | readable and rolling for the whole interval; a `since_version` poller is served it; the version moved | PASS ×9 |
| L3 `[G-M4-9a]` | one replacement: `final`, all-`terminal`, `canonical_through == accepted`, exactly one more revision, committed chain unmoved | PASS ×3 |
| L4 `[G-M4-1/2 cond.]` | the published surface **is** the file arm's on WER / DER / coverage / text-speaker accuracy / content recall, to `1e-12` | PASS ×3 |
| L5 `[G-M4-10]` | `session_tape_released` after the terminal evidence; zero retained bytes; corpus digest; peak ≤ declared capacity | PASS ×9 |
| L6 `[G-M4-7]` | a failure preserves the rolling surface (identical, non-empty, same scores) with a named non-final status | PASS ×6 |
| L7 `[G-M4-9b]` | a second pass cannot un-finalize: surface unmoved, status still `final` | PASS ×3 |
| L8 `[G-M4-13]` | every string in every terminal / revision / tape payload is a name read out of the production sources, an exception type or a digest — and no published word | PASS ×9 |
| L9 | zero fresh MOSS requests | PASS |

## Six mutations, six catches

`mutate_terminal_lifecycle.sh` breaks one promise at a time in `live_service_runtime.py`,
`live_session.py` or `live_coordinator.py`; all three files are restored on exit and a control
run after the sweep proves it.

| mutation | caught by |
|---|---|
| M1 the tape is released before its reader runs | verify FAIL (15) + 7 tests |
| M2 the stop request decodes the whole meeting | verify FAIL (8) + 3 tests |
| M3 a failed pass leaves the status `running` | verify FAIL (1) + 1 test |
| M4 a meeting with no tape is silently not finalized | verify FAIL (4) + 2 tests |
| M5 a finalized surface can be un-finalized | verify FAIL (1) + 1 test |
| M6 a witness that died mid-meeting cancels terminal | **1 test only** |

M6 is test-only and that is the finding, not an omission: sixty seconds of healthy corpus audio
never takes the witness-defect branch, so no corpus run can see it. It is also the reason
`RollingTranscriptConverger.stop` became idempotent — see below.

## Three findings

**F1 — rolling and the meeting do not end at the same moment.** A refinement defect calls
`stop_rolling()` *mid-meeting* (`live_service_runtime._process_refinement_item`). Before this
change the coordinator answered a second `stop_rolling` with `None`, so a meeting whose witness
died would have reached its stop with no `TerminalDecodePlan` — and silently no terminal pass, on
exactly the meetings that need one most. `stop` is now idempotent about *rolling's* ending
(status, frontier and window counts frozen at the first call) while the extent stays the
caller's, because that is the meeting's fact and not the witness's. M6 is the tripwire.

**F2 — `unavailable` needs a reason beside it.** "Nobody tried" and "there was nothing to try
on" are different facts about a meeting and both used to read `not_started`. A deployment that
names a finalizer and keeps no tape now says `unavailable` with `reason: no_retained_tape`;
one with no rolling witness says `no_terminal_plan`. The status word is taken from
`TerminalOutcome.finalization_status` so the vocabulary keeps one author; only the reason is the
runtime's.

**F3 — the terminal producer writes the revision events too.** `text_revision_applied` /
`text_revision_refused` are the seam's events, not the rolling producer's, so the terminal pass
writes them with `source: "terminal"`. A reader counting revisions never has to know which
listener proposed one — and L8 checks the leak gate over both producers rather than one.

## Reproduce

```bash
# the lifecycle on the trio (no GPU, no service, zero MOSS requests)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_terminal_lifecycle.py \
  --output /tmp/m4-lifecycle.json
# its six mutations, restored from backups on exit
prototypes/streaming-diarization/live-convergence/mutate_terminal_lifecycle.sh /tmp/lifecycle-mut
# the T2 tests
.venv/bin/python -m pytest tests/test_live_terminal_lifecycle.py -q
# do the six instruments that share the driver still reproduce their artifacts?
.venv/bin/python evidence/live-convergence-0824/M4-terminal-lifecycle/inertness.py
```

## Files

| file | what it is |
|---|---|
| `verify.json`, `console.txt` | the nine gates on three arms × three cases |
| `mutations.txt`, `mutations/` | the six-mutation sweep, control before and after |
| `pytest-targeted.txt` | 85 passed — lifecycle, finalizer, rolling wiring, revision, converger |
| `pytest-full.txt` | 1133 passed, 2 skipped, 396 subtests (1121 before this iteration) |
| `inertness.txt`, `inertness.py` | all six driver-sharing instruments reproduce their checked-in artifacts and still pass their own gates |
| `file-mode-{head,worktree}.json` | file-mode decoder A/B vs a HEAD worktree — both `ad381d8b…7707f2` |
| `sha256.txt` | digests of everything above |

Production code this step shipped:
`live_service_runtime.py` (the lifecycle, the two schedulers, the three §7.4 events, the
release ordering), `live_session.py` (`note_finalization`), `live_coordinator.py`
(`stop_rolling` always answers), `live_transcript_convergence.py`
(`RollingTranscriptConverger.stop` idempotent about rolling's ending).
