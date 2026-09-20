# VERIFY — R4-8 surfaces

Run from this clone with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`.

1. `git merge-base HEAD 89f833acd4c654dd702664a17ed19783a2999c95` prints
   `89f833acd4c654dd702664a17ed19783a2999c95`; `git branch --show-current` prints
   `round4/surfaces`.
2. Compile the four Python files under `prototypes/surfaces/` and run
   `sh -n prototypes/surfaces/run-summaries.sh`; expect success.
3. Run `prototypes/surfaces/run_hidden_cases.py 3,15 --headed`. In this Background
   session expect exit 77 and `BLOCKED-ON-SESSION`, with no browser launch.
4. Run `./prototypes/surfaces/run-summaries.sh`; expect case 13 provider POSTs 0 and
   verifier exits `0, 1, 77`.
5. Scan new/owned paths for the two secret patterns from the pane brief; expect zero.
   The repository-wide command has seven pre-existing `<key>` placeholders at base.
6. Confirm ports 18442, 18443, and 18733 have no owned listeners.

Falsify this handoff on any unexpected exit, secret match in new paths, off-host request,
leftover process, or a claim that hidden/m4mbp/microphone/playback was measured here.
