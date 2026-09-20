# R4-3 fresh-context verification

Run from `/private/tmp/moss-round4-20260920/gap` with no prior task context.

```sh
git rev-parse HEAD
git branch --show-current
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_r4_gap_terminal_identity.py
jq -e '.decoder_requests == 0 and (.causal_spans|length) == 26 and (.saved_spans|length) == 15 and (.saved_spans|map(select(.observed_canonical == null))|length) == 1 and .hypotheses.a_evidence_or_admission_floor.state.samples == 4320 and .hypotheses.a_evidence_or_admission_floor.state.min_segment_samples == 8000 and .hypotheses.e_terminal_mapping.state.projected_canonical == null and .remedy_controls.healthy_control.decision == "match" and .remedy_controls.falsifier_control.decision == "abstain"' evidence/round4/gap/diagnosis.json
```

Expected: HEAD starts from `89f833ac` plus only the final pane commit if already committed;
branch `round4/gap`; tests `1 passed, 1 xfailed`; `jq` prints `true`.

Falsify the handoff if any command fails, the xfail unexpectedly passes, decoder requests are
nonzero, the unresolved population is not exactly 1/15, or the different-voice control matches.
