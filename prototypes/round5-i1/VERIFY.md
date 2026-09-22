# Fresh verification — D31 production L1 harness gate

Verify the current `round5/impl-l1` HEAD from a new clone; do not use a provider, tunnel, GPU,
or a shared MOSS listener. This is harness-only verification.

```sh
git clone --no-local /private/tmp/moss-round5-i1 /private/tmp/moss-round5-i1-verify
cd /private/tmp/moss-round5-i1-verify
git checkout round5/impl-l1
git fetch /Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate round5/integration
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
- D31 controls: 20 passed. A delayed settled snapshot at 5.001 s is `TIMEOUT`;
  first-cover latency precedes settled tail latency; paused pre/post tail reasons
  are both `end_silence`; and no-silence is pre `none` / post `stop_flush`.
  An otherwise healthy pre surface with absent post-Stop events fails closed.
  Missing scorer attribution telemetry fails closed. The fetched `fd825ee7`
  scorer accepts named surfaces and rejects all-anonymous ones. Retention preserves
  both tail reasons, both latencies, and surface identity numbers/bools.
- Full backend: 2,328 passed / 5 skipped / 2 xfailed / 0 failed; bundle: 22 passed.
- Decoder requests: 0. Frontend was intentionally untouched.

Falsify if a product path changes, any D31 or identity control fails, the
pre-Stop facts are not retained, or either required suite has a failure.
