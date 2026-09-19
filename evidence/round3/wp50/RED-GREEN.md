# WP50 evidence

## Gate and design

- Prototype gate: DONE; round-2 `prototypes/publication/NOTES.md` F1 supported one finish-seam outcome projection.
- Structural question: keep terminal outcome truth identical in Live, saved Meeting, and a fresh-app reopen.
- Minimum primitives: settled runtime snapshot, final terminal accounting event, existing durable notice, authoritative store `needs_review`.
- Invariants: healthy speech and digital silence stay clean; words/audio persist; no second store or lifecycle service.
- Falsifier: any failed/truncated/unavailable/interrupted outcome reopens clean, or any healthy/silence outcome gains review.
- Decoder: 0/0 remote requests; no tunnel opened.

## Unpatched RED at `a7a738cf9f9ff246f64c52c112e0bf597ba58241`

Command:

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv>/python -m pytest -q -p no:cacheprovider tests/phase2/test_terminal_outcome_projection.py -k 'not healthy and not digital_silence'`

Result: **7 failed, 2 deselected** in 3.86 s (wall 4.44 s). The seven intentional failures were system-lane failure, microphone-lane failure, total decode failure, unavailable refinement, tape gaps, truncation, and interrupted. Partial/total/truncation saved clean; unavailable/gaps/interrupted lacked Live `needs_review`.

The earlier narrow RED command over the three lane/decode cases produced **3 failed, 2 deselected** in 7.20 s. This explicitly proves a patch limited to `reason.startswith("lane_terminal_failed:")` is insufficient: the total-decode arm also failed on the unfixed base.

## Patched GREEN

- `tests/phase2/test_terminal_outcome_projection.py`: **9 passed** in 5.10 s.
- Focused WP50 command covering the new test plus existing finalization boundary, runtime lifecycle, and tape exhaustion suites: **33 passed** in 29.65 s.
- Healthy denominators: healthy speech 1/1 clean; digital silence 1/1 clean.
- Review denominators: 7/7 controlled failure outcomes visible Live, saved, and after fresh-app reopen.
- Lane oracle: first signed PCM sample in each lane WAV; never decoder call order.
- Failed attempt retained: `max_tape_bytes=0` was rejected by the existing positive-bound invariant; unavailable refinement is instead injected by removing the retained mixed tape after ordinary capture, before real HTTP Stop.

## Full-suite correction

- The first full-suite command accidentally used the source checkout's Python 3.10 venv, not the brief's auto-MVP Python 3.12 venv; its 1,940 passed / 39 failed / 76 errors result is invalid as a gate.
- That run still exposed an unnecessary second database snapshot in terminal settlement. Replaced it with the store's existing pure `_meeting_needs_review` predicate, preserving the durable rule without adding deadline work.
- The 50 ms terminal-projection test deadline flaked under combined load and measured no product requirement; widened to 500 ms. Production deadline policy is unchanged.
- Every file named by the invalid failure summary passed under the mandated venv: **295 tests + 19 subtests**.
