# R4-3 fresh-context verification result

## Current-context verification — 2026-09-20T21:32:18Z

**PASS**

Working directory: `/private/tmp/moss-round4-20260920/gap`

```sh
$ git rev-parse HEAD
2ddb208cae2e28706c7b89fa42f8e4dd290bbaa2
```

Exit: `0`. **PASS** — HEAD was the existing pane commit.

```sh
$ git branch --show-current
round4/gap
```

Exit: `0`. **PASS** — required branch.

```sh
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_r4_gap_terminal_identity.py
x.                                                                       [100%]
1 passed, 1 xfailed in 1.27s
```

Exit: `0`. **PASS** — exact counts: `1 passed`, `1 xfailed`, `0 failed`, `0 xpassed`.

```sh
$ jq -e '.decoder_requests == 0 and (.causal_spans|length) == 26 and (.saved_spans|length) == 15 and (.saved_spans|map(select(.observed_canonical == null))|length) == 1 and .hypotheses.a_evidence_or_admission_floor.state.samples == 4320 and .hypotheses.a_evidence_or_admission_floor.state.min_segment_samples == 8000 and .hypotheses.e_terminal_mapping.state.projected_canonical == null and .remedy_controls.healthy_control.decision == "match" and .remedy_controls.falsifier_control.decision == "abstain"' evidence/round4/gap/diagnosis.json
true
```

Exit: `0`. **PASS** — decoder requests `0`; causal spans `26`; saved spans `15`; unresolved `1/15`; samples `4320`; minimum `8000`; projected canonical `null`; healthy control `match`; falsifier control `abstain`.

Current-context verdict: **PASS**. All prescribed commands succeeded; expected xfail remained xfailed.

## History

### Prior current-context verification

**PASS**

Working directory: `/private/tmp/moss-round4-20260920/gap`

## Prescribed commands and exact outputs

```sh
$ git rev-parse HEAD
74d905e94b973902112be14e3a0965f7747c17a3
```

Exit: `0`

```sh
$ git branch --show-current
round4/gap
```

Exit: `0`

```sh
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_r4_gap_terminal_identity.py
x.                                                                       [100%]
1 passed, 1 xfailed in 0.34s
```

Exit: `0`. Exact test counts: `1 passed`, `1 xfailed`, `0 failed`, `0 xpassed`.

```sh
$ jq -e '.decoder_requests == 0 and (.causal_spans|length) == 26 and (.saved_spans|length) == 15 and (.saved_spans|map(select(.observed_canonical == null))|length) == 1 and .hypotheses.a_evidence_or_admission_floor.state.samples == 4320 and .hypotheses.a_evidence_or_admission_floor.state.min_segment_samples == 8000 and .hypotheses.e_terminal_mapping.state.projected_canonical == null and .remedy_controls.healthy_control.decision == "match" and .remedy_controls.falsifier_control.decision == "abstain"' evidence/round4/gap/diagnosis.json
true
```

Exit: `0`. The passing predicate verifies: decoder requests `0`; causal spans `26`; saved spans `15`; unresolved saved spans `1/15`; terminal evidence samples `4320`; minimum segment samples `8000`; projected canonical identity `null`; healthy control `match`; different-voice falsifier control `abstain`.

## HEAD ancestry confirmation

```sh
$ git rev-parse 89f833ac
89f833acd4c654dd702664a17ed19783a2999c95

$ git rev-parse HEAD^
89f833acd4c654dd702664a17ed19783a2999c95

$ git rev-list --count 89f833ac..HEAD
1
```

Each command exited `0`. HEAD is exactly one final pane commit above required base `89f833ac`.

## Verdict

All required commands succeeded. The expected xfail remained xfailed, decoder requests remained zero, the unresolved population was exactly `1/15`, and the different-voice control abstained. Handoff verified.
