# Fresh verification — D31 production L1 harness gate

Verify the current `round5/impl-l1` HEAD from a new clone; do not use a provider, tunnel, GPU,
or a shared MOSS listener. This is harness-only verification.

```sh
git clone --no-local /private/tmp/moss-round5-i1 /private/tmp/moss-round5-i1-verify
cd /private/tmp/moss-round5-i1-verify
git checkout round5/impl-l1
ln -s /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/frontend/node_modules frontend/node_modules

PY=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1

"$PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
git diff --check 58882514
test -z "$(git diff --name-only 58882514 -- moss_transcribe_diarize frontend/src)"
"$PY" -m pytest -q -p no:cacheprovider tests/phase2/test_demo_lane_measurement.py tests/test_verify_demo_lanes_d31.py
"$PY" -m pytest -q -p no:cacheprovider tests
"$PY" -m pytest -q -p no:cacheprovider tools/qualify/test_bundle.py
git status --short
```

Expected:

- Import resolves inside the verify clone; no product/frontend source diff exists.
- D31 controls: 16 passed. The healthy paused boundary has `SETTLED`,
  `end_silence`, active/no-Stop pre, a tail latency, and completed final;
  no-silence is `TIMEOUT`/`none`; `hard_cap` is rejected. Retention preserves
  all six D31 fields. An all-anonymous correct-word surface is rejected while a
  named surface is accepted.
- Full backend: 2,324 passed / 5 skipped / 2 xfailed / 0 failed; bundle: 22 passed.
- Decoder requests: 0. Frontend was intentionally untouched.

Falsify if a product path changes, any D31 or identity control fails, the
pre-Stop facts are not retained, or either required suite has a failure.
