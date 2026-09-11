# Job 2: fresh identity replay remains unmeasured

Candidate inspected: `9fa8ee85`. No fresh provider requests or host operations.
`identity-results.json` was created before discovery and updated with the blocker;
all six cases retain null speaker metrics and speaker counts. No replay was run.

Question: does fresh production identity assignment split the monologue into multiple
speakers? Required inputs are corpus audio and fresh provider output; the unchanged
identity policy assigns speakers, and reference labels only score the result. More
than one output speaker on `mono_javier_intro_50s` would reproduce the bench symptom.
The answer remains unknown.

Local availability checks establish the boundary:

- `lsof -nP -iTCP -sTCP:LISTEN`: no listener on 18000. The 8000 listener is nginx.
  `/opt/homebrew/etc/nginx/lmstudio-cluster-dynamic.conf` routes it to `model_a`,
  whose only configured backend is `127.0.0.1:1 down`. No usable local MOSS
  decoder endpoint was established; no inference request was made.
- The pinned WeSpeaker ONNX and local provider manifest exist. Fresh embeddings
  alone cannot replace the missing canonical transcription inputs.
- The six-case `evidence/live-policy-sweep-20260825/moss/shadow-cache/pass-A.json`
  has 61 ten-second and 56 fifteen-second decodes. These are rolling windows, not
  the complete short canonical decode stream needed by the live runtime.
- `proto_real_replay.py` builds spans from reference speaker labels. Using that
  bench unchanged would feed the expected answer into the input. Archived
  canonical speaker timelines likewise cannot establish fresh identity behavior.

Missing: fresh live-runtime output and strict settled/final captures for all six
cases, their four speaker metrics, and Javier's observed speaker count. Round 6
is already running under the host owner's control; its retained per-case evidence
can answer the deployed question when supplied locally. An independent fresh
replay still needs a usable decoder. No extra qualification run was started.

Only this note and the incremental result ledger changed. `QUALITY_BOUNDS`,
`_validate_quality`, and identity policy remain untouched. Validation checks JSON
shape, preserves nulls for every unmeasured metric, and checks diff scope; no
production-code or test changes require another full suite run.
