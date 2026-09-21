# PRD - MOSS round 4, ralph run B: implement the verdict-approved seams

## Goal

> Turn the two SUPPORTED, fresh-verified round-4 prototypes into product behaviour without changing any recognition
> constant: (1) File/URL batch work survives an application restart under the ownership of its existing Meeting, and
> (2) a speaker's own short terminal span after a silence hole is no longer published as `S00` when the terminal
> decoder's partition already ties it to an established person. If decision D27 is recorded as YES in
> `context.md`, also (3) correct the acceptance-corpus reference/cut defects the overlap diagnosis proved, changing only
> the edits that diagnosis classified (d).

## Acceptance bar

The loop is complete only when every point below holds, with evidence (commands run, artifacts inspected, before/after
deltas) recorded in progress.txt:

- **A3 batch ownership.** The ten prototype cases in `prototypes/batch-startup/` (C1 resume after 40 windows with
  exactly 61 remaining delegate calls and 101/101 unique saved segments, one publication, exact reopen; C2 mid-window
  crash redone once, no duplicate segment; C3 cancel during restart → durable `cancelled`, no further calls; C4
  duplicate startup → exactly one owner proceeds; C5 wrong owner / source hash / contract → refused, honest
  `interrupted`; C6 damaged prefix → refused, received data preserved; C7 URL resume from the retained local copy,
  honest failure without it; C8 account-scoped recovery applies the same claim; C9 legacy non-resumable File row still
  finishes `interrupted`; C10 an active **live** row is still finished `interrupted` and `_assert_no_active_meetings`
  is unchanged) pass as **product** tests against the real `lifespan` — not against the prototype composition. The two
  `xfail(strict=True)` violating controls from branch `round4/batch` flip to plain passes (remove the xfail marker; the
  test body is unchanged). `phase2.py:751-763` is byte-identical to base. Production File passes a real checkpoint
  directory under the Meeting-keyed durable root (not `checkpoint_dir=None`).
- **Gap remedy — a conditional partition rule, with BOTH branches asserted.** The remedy operates on the terminal
  decoder's local-speaker partition: retain each terminal-local label through convergence, aggregate the eligible
  acoustic evidence **once per unmapped local partition**, match once, and project the result **only inside that
  partition**. No temporal neighbour, no floor change, no cross-partition projection; `ALBUM_MIN_MATCH_SCORE`,
  `ALBUM_MIN_MATCH_MARGIN`, `ALBUM_ADMISSION_SECONDS`, `ALBUM_BIRTH_MIN_SECONDS` and `min_segment_samples` byte-identical
  to base. Two controls are **both required** (the historical S17 row is `UNMEASURED` either way — see below):
  1. **Shared partition** — a short span sharing a terminal partition with eligible Adam evidence (reproduced score
     0.909091) resolves to the established canonical identity, while the different-voice Keyu control (0.017033) stays
     unknown and is never absorbed.
  2. **Isolated partition** — a historical-style isolated short span (no eligible evidence in its own partition) **stays
     `S00`** and is reported as such. That is the correct, safe abstention; a test that forces it to resolve is a defect.
  The `round4/gap` strict control flips to a plain pass only because branch 1 now holds.
  **Never claim this repairs the historical S17 failure.** The retained S17 material carries no raw terminal-local
  labels, so whether `seg_0012` was isolated is **unknown**; the S17 identity row stays **UNMEASURED** until R4-10 reruns
  it while retaining the raw terminal label stream. Do not write "gap closed" anywhere in this run's evidence.
- **Fixture correction (D27 = YES).** Covers **all** affected arms, not only overlap: pane 3.4's follow-on
  (`evidence/round4/overlap/attribution-alternation.md`, `33d3916b`) attributes all 19 retained final edits
  (a=12, d=7) and shows corrected scores alternation system 5/102 = 4.90 %, alternation mic 5/53 = 9.43 %, overlap mic
  5/53 = 9.43 % — all under their bars. The **pre-terminal** arms (system 16/106, mic 11/53) are UNMEASURED because the
  edited word rows were not retained; they must be re-run against the corrected reference in the measurement pass, not
  asserted here. The falsifier below applies per arm. `tests/e2e/verify_demo_lanes.py` scores the overlap
  acceptance arm against a reference that matches the audio actually cut (29.0 s, or the cut moved to 29.25 s so "the
  book" is included — pick one, record why), and the ladder rows against a 24 s reference; the corpus reference row for
  `interview_bill_ackman_60s` is corrected exactly as `evidence/round4/overlap/reference-correction-proposal.json` and
  the second opinion `evidence/round4/overlap-review/second-opinion.md` agree (`market is`, `You're`, `divine`, leading
  overhang removed). Falsifier test: replaying the retained overlap publication against the corrected reference yields
  exactly the three class-(a) additions (`you`, `know`, repeated `to`) and nothing else — the decoder's real errors stay
  visible. If `context.md` records D27 = NO or blank, this item is a non-candidate and the ledger row stays a FAIL.
- **Strict-control accounting.** Exactly the **six** controls this run owns convert from `xfail(strict=True)` to
  ordinary passes by *removing only the marker* (batch 2, gap 1, fixture 3 — enumerated by name in `context.md`); the
  **two Jamie controls remain xfailed** (R4-4 is FALSIFIED; nothing here may make them pass). Final expectation:
  backend ≥ **2,136 passed / 0 failed / 5 skipped / 2 xfailed**.
- Full backend suite `python -m pytest -q -p no:cacheprovider tests` and frontend `npm --prefix frontend test -- --run`
  ≥ 312/312 on the final tree; `npm --prefix frontend run typecheck` clean; if any frontend source changed,
  `npm --prefix frontend run build` followed by an empty `git status` (asset parity).
- `docs/verify/round4-run-b/VERIFY.md`: what to run, expected counts, what would falsify — self-contained.

## Constraints

Non-negotiable, in addition to the rules in prompt.md:

- Python `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`,
  always `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`, cwd = this repo; frontend via the symlinked `frontend/node_modules`.
- **This run is offline: 0 decoder requests, no tunnel, no proxy, no GPU, no network** (lead ruling under D28). Every
  claim comes from retained outputs, the CPU ONNX embedder, the local HF model, and the real app under test. The single
  decoder-backed confirmation of the gap remedy belongs to R4-10, where it must retain the raw terminal label stream.
  Never run `tools/qualify/run.py --long`; never let `capacity_2x1800: REQUIRED-NOT-RUN` disappear from a summary.
- Never change `QUALITY_BOUNDS`, any gate bar, identity constants, the live frame protocol, sentinels, poll delays,
  `LIVE_MEETING_LIMIT`, or `phase2.py:751-763`. No duration floor. No new hand-tuned constant.
- Deepen existing modules (`FileMeetingTasks`, the Meeting, the terminal identity path). No second job framework, no
  checkpoint framework, no feature flag, no compatibility wrapper. `windowed_transcription.py:197-255` checkpoint
  validation is sufficient as is.
- Live capture keeps D13: no live resume across a restart, ever.
- Never read, copy or print `~/.config/moss/openrouter.env` or any `OPENROUTER_API_KEY`. Never write under
  `tools/qualify/out/`, `playwright-report/`, `test-results/` into git.
- Never `git push`; never merge or rebase; commit only on branch `round4/ralph-b`. Historical `evidence/` is read-only.
- Do not modify `tools/qualify/` (owned by run A's merge) except to consume its preflight when adding a bundle row.

## Budget and stop

- The launcher argument sets the iteration budget; one logical change per iteration.
- Stop early only via the completion contract: acceptance bar met with evidence, or every remaining item blocked on
  input the loop cannot obtain, recorded in progress.txt.
- A blocker ends the iteration, not the loop: record it, commit anything useful, and let the next iteration attack it or
  route around it.
