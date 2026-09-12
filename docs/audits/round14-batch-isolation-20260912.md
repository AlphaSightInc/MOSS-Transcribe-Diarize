# Round 14 batch failure isolation — 2026-09-12

**The host cause remains unestablished. A demonstrated observation defect is fixed;
no product or evaluator behavior is changed, and the failed host gate is not claimed
repaired.** Candidate `057a547c` retained isolation=true in deployed, false in
pre-admission, with zero history mismatches and restart failures in both.

## F1 — evidence does not contain the deciding per-item states

Sources: `/tmp/moss-round14-stage/result/report.md`, `evidence.tar` and
`supplemental-pre_admission-sessions.json` — **MacStudio-local (not in repo)**.
The archive's two `*--G3--meeting_modes_history_restart.json` observations were
extracted to a separate scratch directory, recorded by
`/tmp/moss-round14-isolation-root` — **MacStudio-local (not in repo)**.

Both observations contain modes, aggregate counts and the isolation boolean, but
neither contains per-item terminal states. The campaign's artifact inventory has
no batch-state companion. The supplemental pre-admission collection contains 41
live-session records, not the File/URL batch states. The collector computes the
terminal-state map in memory and discards it. Its returned input-boundary count
was the literal 1, not the observed count.

Thus the user's proposed per-item evidence is not present in these retained G3
records. No transcript, audio, cookie, URL, title or upstream body is copied here.

## F2 — hypotheses and boundaries

| Hypothesis | Finding |
|---|---|
| A successful-intent batch item failed/interrupted | Still possible; missing per-item states prevent identification or attribution. |
| The deliberately failing URL completed | Its observed terminal state is missing. However acquisition exceptions call `_mark_failed` and return before transcription, so speechless terminal-window success does not swallow an acquisition failure. No producer regression demonstrated. |
| Input-boundary rejection count was 0 or 2 | Ruled out on the unmodified browser path: `submit_file_url_batch` requires five accepted and exactly one rejected submission with HTTP 400/422, or raises. Round 14 retained no collector exception. |
| Separate pre-admission audio abort contaminated “others” | Ruled out structurally and by regression: isolation reads only the six IDs returned by this batch (two files, two successful-intent URLs, one failure URL, one detached file), not all owner history. An unrelated interrupted meeting remains outside that map. |

The `ACCEPTED_FAILURE_URL` is unchanged. `app/phase2_file.py::_acquire_and_run`
awaits acquisition before invoking `_run`; `app/phase2_url.py::_acquire_http`
converts transport errors into acquisition rejection. Layer asymmetry alone does
not distinguish an ordinary item failure from the intentional item's unexpected
success. The evaluator's all-other-items-completed expectation is correct.

## F3 — narrowly scoped repair and tests

`phase2_acceptance_external.py::meeting_modes_history_restart` now retains:

- `accepted_failure_meeting_id`: the opaque ID of the intentional failure;
- `terminal_states`: six batch IDs mapped to terminal statuses, including the
  detached file; no titles, transcript or errors;
- `submissions.input_boundary_rejection`: actual observed count;
- `submissions.accepted_failure`: actual accepted failure count.

The isolation expression, terminal waits, restart and evaluator requirements are
unchanged. No retries, substitutions or ignored failures were added.

The existing browser-free producer test now includes an unrelated interrupted
meeting in owner history and covers the intentional item completing, a peer failing,
a peer interrupted, and zero/two input-boundary rejections. The latter two injected
shapes test count retention at the producer seam; the real browser rejects them
before this point. All remain failures. The normal batch with unrelated interrupted
history passes; Stop 409 still raises. Tests assert that content-bearing fixture
fields do not appear in the returned observation.

Before the repair: **6 failed, 1 passed** (missing retained fields).
After: **188 passed** in `tests/phase2/test_wave1_qualification.py`.
Full Python suite, supported browser discovery disabled: **1,585 passed + 37
subtests, 25 optional skips, zero failures**. The production XML reducer confirms
**all 24 required files, zero required failures/skips/missing cases** (1,647 XML
cases; 1,622 executed/passed). Logs: `/tmp/moss-round14-isolation-python.log` and
`/tmp/moss-round14-isolation-python.xml` — **MacStudio-local (not in repo)**.
Frontend files were unchanged; no frontend rebuild was performed.

A future failure can now identify which operand failed without inspecting content.
Without the original batch states, changing the producer or declaring the host
failure fixed would be speculative. No host operations, policy/bound changes, or
frontend changes were performed.
