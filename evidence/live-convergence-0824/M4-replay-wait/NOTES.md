# M4 step 3e — the measuring client waits for the surface the meeting ended on

**Iteration 28, 2026-08-25. Candidate 8c-5. Verdict: SHIPPED — nine gates pass, nine
reactions catch them, and on the deployed service the paired driver's own live arm moved
from the rolling surface to the terminal one, `WER .096000 -> .088000 == the file arm's
.088000`, with no edit to any driver.**

## The question

Iteration 27 deployed the E4 build and found (finding F1) that the instrument could not see
what it had just built. `run_service_replay` returns when `POST /stop` answers, and since
iteration 26 the stop answers **before** the terminal decode runs — plan §12.3 M2 requires
that, because on the longest audio this campaign allows the decode is minutes on a request a
browser holds open. So the pass wrote the **rolling** surface into `live-hypothesis.jsonl`,
its trace ended at `terminal_finalization_started`, and iteration 27's terminal numbers exist
only because the session was polled by hand afterwards.

All three paired drivers call that one client. Unfixed, the M4 exit would have scored five
rolling transcripts and reported that terminal convergence does not work.

## What shipped

`moss_transcribe_diarize/live_service_replay.py`:

- `_await_terminal_finalization` — after the stop response, poll the snapshot until
  `finalization_status` leaves `running`, draining the event stream on every poll, then report
  the polled snapshot and the advanced cursor. `not_started` / `final` / `failed` /
  `unavailable` are already answers (`TERMINAL_FINALIZATION_SETTLED`), so a meeting that gets
  no terminal pass is not waited on at all.
- `ServiceReplayFinalizationTimeout` (exit code 8) — a pass that outlives the deadline fails
  the run **by name**. Writing the artifacts anyway would reproduce F1 with extra steps: the
  surface in them would be the rolling one under a run that called itself complete.
- `finalization_deadline` (default 300 s, `--finalization-deadline`), named in the manifest's
  `cli` block, in the new `terminal_finalization_wait` trace record, and in the timeout
  message. The deadline is the instrument's patience, not the service's contract.
- `summary.json` gains `finalization_status` and `finalization_waited`, so a scorer reads
  which surface the artifacts beside it carry rather than assuming.

No driver was edited: the wait is in the client all three share (gate G-W9).

## Gates — `verify_replay_terminal_wait.py` (no GPU, no service, zero MOSS requests)

Runs the real client against the in-memory E4 runtime on a scripted clock, with a manual
terminal scheduler so the pass lands at a chosen poll rather than a raced one.

| gate | claim |
| --- | --- |
| G-W1 | the stop response already names which meeting this is (`running` / `not_started` / `unavailable`), and the run records it |
| G-W2 | **F1 reproduced**: the pre-wait client publishes the rolling surface and stops reading at `terminal_finalization_started` |
| G-W3 | the shipped client publishes the terminal surface instead (`final`, authority `terminal`, different words) |
| G-W4 | the four §7.4 events that made it reach the trace, after `session_closed`, in order |
| G-W5 | a deployment that runs no terminal pass is not waited on, and its run is otherwise the pre-wait client's |
| G-W6 | a pass that ends without a surface (`unavailable`) is an answer, not a wait |
| G-W7 | a pass that never answers fails the run by name rather than publishing the rolling surface as complete |
| G-W8 | the deadline is the caller's, and every artifact names the one that was spent |
| G-W9 | all three paired drivers inherit the wait unedited |

`console.txt` (all nine PASS), `gates.json`, `selftest.txt` (nine defective clients, each
caught by its own gate).

## The deployed measurement

One warm-decoder pass over `lex_javier_milei` (60 s) against the **unchanged** running
service — iteration 27's deployment, `source_revision 29681e04…`, `combined_config_hash
431efb3f…`; **no restart**, because this change is client-side only. `pass/`, `pass-console.log`,
`warmup.log`.

| arm | WER | TBSA | DER | speaker accuracy | segments |
| --- | --- | --- | --- | --- | --- |
| file | .088000 | .881244 | .151833 | .848167 | 20 |
| live, iteration 27 (rolling, F1) | .096000 | .906296 | .117333 | .882667 | 14 |
| live, this pass (terminal) | .088000 | .881244 | .151833 | .848167 | 20 |

The wait cost **2.055 s over 4 polls** against a 300 s deadline. The trace's
`terminal_finalization_wait` record reads `stop_finalization_status: running ->
finalization_status: final`, the four post-close events are all present, and the terminal
snapshot carries 20 segments at `text_revision_version 7`, every one authority `terminal`.
The file arm reproduces iteration 27's numbers exactly.

**Two things this pass says, and one it does not.** It says the instrument now reports the
terminal surface, and it says terminal *is* the file arm on every axis — text and speakers
alike. It does **not** say terminal convergence is uniformly an improvement: on this case the
speaker surface gets worse (`DER .117333 -> .151833`, `speaker accuracy .882667 -> .848167`)
because the file arm's speakers on `lex_javier_milei` are worse than the rolling live ones.
That is D-M4-2's known collision, now visible in a driver artifact instead of a hand poll;
its disposition belongs to the M4 exit, not here.

## Inertness (`inertness.txt`)

- Six shared instruments: five reproduce their checked-in artifacts field for field;
  `verify_runtime_rolling.py` still differs at exactly `deployed_configuration` — iteration
  27's declared `bounds_config.max_tape_bytes`, unchanged by this iteration.
- File-mode decoder A/B: `ad381d8bd247…`, unmoved across thirteen production changes
  (`file-mode-hash.txt`).
- `remeasure_one_case.py --selftest`: 0 failures — the drivers are still the checked-in shape.
- Iteration 5's `probe_replay_trace_shape_identity.py` now reports `trace lengths differ:
  41 vs 42`, which is this change and only this change: the added
  `terminal_finalization_wait` record on a fixture whose deployment runs no terminal pass.
  That probe compares traces positionally and cannot express an insertion; G-W5 answers the
  same question properly (record kinds, event kinds, published surface and scorer-facing
  summary fields, all equal to the pre-wait client's, and equal between two shipped runs).
- Tests: `1147 passed, 2 skipped, 396 subtests` (`pytest-full.txt`; 1141 before).

## Decisions worth not re-opening

- **The wait is the client's, not the service's.** Making `stop` synchronous was refused by
  plan §12.3 M2 and by iteration 26's mutation M2, and it is refused again here: minutes of
  decode on a request a client holds open.
- **A timeout fails the run.** The alternative — artifacts plus a note — puts the rolling
  surface under a completed-looking run and requires every future scorer to know to look.
- **No driver learned a new keyword.** The default deadline applies everywhere, which is what
  keeps `remeasure_one_case.py --selftest`'s checked-in-shape comparison meaningful.
- **Draining on every poll is not decoration.** The runtime holds events in a bounded deque;
  a client that slept through a minutes-long decode and then read from its old cursor would be
  told the stream had moved on — the same defect iteration 5 fixed for the capture interval.
