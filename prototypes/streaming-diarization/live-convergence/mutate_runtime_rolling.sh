#!/usr/bin/env bash
# Mutation sweep for the SHIPPED runtime wiring of the rolling witness (plan §10.5 step 4).
#
# Each mutation breaks one property the wiring claims, in a production file, and must be caught
# -- by the two-arm runtime verifier on real trio audio, by a named T2 test, or by both. Where
# only the test catches it, that is recorded as a finding rather than papered over: an unhurried
# meeting cannot reach a hazard that only appears when the base runs ahead of the witness.
# Both production files are restored from backups on exit, including on failure, and a control
# run after the sweep proves it. Every run replays the grid's decode cache: ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_runtime_rolling.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
COORD="$REPO/moss_transcribe_diarize/app/live_coordinator.py"
RUNTIME="$REPO/moss_transcribe_diarize/app/live_service_runtime.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_runtime_rolling.py"
TESTS="$REPO/tests/test_live_rolling_wiring.py"
COORD_BACKUP="$(mktemp)"
RUNTIME_BACKUP="$(mktemp)"
cp "$COORD" "$COORD_BACKUP"
cp "$RUNTIME" "$RUNTIME_BACKUP"
restore() { cp "$COORD_BACKUP" "$COORD"; cp "$RUNTIME_BACKUP" "$RUNTIME"; }
trap 'restore; rm -f "$COORD_BACKUP" "$RUNTIME_BACKUP"' EXIT
mkdir -p "$OUT"

patch() {  # patch <file> <old> <new>
  MUT_PATH="$1" "$REPO/.venv/bin/python" - "$2" "$3" <<'PY'
import os, sys
from pathlib import Path
path = Path(os.environ["MUT_PATH"])
text = path.read_text()
old, new = sys.argv[1], sys.argv[2]
assert old in text, "anchor not found"
path.write_text(text.replace(old, new, 1))
PY
}

check() {  # check <name>
  local name="$1"
  PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" "$VERIFY" \
    --output "$OUT/$name.json" > "$OUT/$name-verify.txt" 2>&1
  local verify=$?
  PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" -m pytest $TESTS -q \
    > "$OUT/$name-pytest.txt" 2>&1
  local tests=$?
  echo "$name: verify exit=$verify  pytest exit=$tests  $(tail -1 "$OUT/$name-pytest.txt")" \
    | tee -a "$OUT/summary.txt"
  grep -E '^(FAIL|PASS|Traceback|AssertionError)' "$OUT/$name-verify.txt" \
    | head -4 | sed 's/^/    /' | tee -a "$OUT/summary.txt"
  restore
}

: > "$OUT/summary.txt"
echo "== control: unmutated modules ==" | tee -a "$OUT/summary.txt"
check control

# M1 -- a base commit no longer reaches the converger, so no window is ever ownable. This is
# the whole of step 4 removed. Guard: the verifier (0 windows, base arm WER) and the T2 tests.
echo "== M1: base commits are not observed ==" | tee -a "$OUT/summary.txt"
patch "$COORD" '        self._observe_base_and_queue()
        measurement = _canonical_decode_measurement' '        measurement = _canonical_decode_measurement'
check m1-base-commit-not-observed

# M2 -- the converger is not re-observed after an applied revision, so the frontier it sees
# stops one window short and rolling ends after the first window. This is the carry-forward
# iteration 12 recorded. Guard: the verifier (1 of 6 windows) and the T2 release test.
echo "== M2: no observe_base after an applied revision ==" | tee -a "$OUT/summary.txt"
patch "$COORD" '        self._observe_base_and_queue()
        snapshot = self.session.snapshot()
        accounting = converger.accounting()' '        snapshot = self.session.snapshot()
        accounting = converger.accounting()'
check m2-no-observe-after-revision

# M3 -- the next window is planned before this one is released, so the arbiter refuses it as
# "already running" and the window is lost. Guard: T2 ONLY. The hazard needs the base to be
# ahead of the witness by a whole window, which unhurried real-time trio audio never is.
echo "== M3: the next window is planned before the release ==" | tee -a "$OUT/summary.txt"
patch "$COORD" '        self.release_refinement(item)
        proposal = converger.complete' '        proposal = converger.complete'
check m3-plan-before-release

# M4 -- the coalesce key carries only the converger epoch, so two epoch-0 sessions sharing an
# arbiter replace each other's witnesses. Guard: T2 ONLY -- the runtime builds one arbiter per
# session, so a single-session corpus cannot reach it. Latent, and named.
echo "== M4: the coalesce key drops the session ==" | tee -a "$OUT/summary.txt"
patch "$COORD" 'coalesce_key=f"{self.session_key}:{request.coalesce_key}"' 'coalesce_key=request.coalesce_key'
check m4-coalesce-key-drops-session

# M5 -- stop no longer waits for a witness, so the last correction of every meeting is thrown
# away. Guard: the verifier (5 of 6 windows) and the T2 stop test.
echo "== M5: stop does not wait for the witness ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" '            or queues.live_refinement
            or queues.live_refinement_running' '            or False'
check m5-stop-does-not-wait

echo "== restored; control run ==" | tee -a "$OUT/summary.txt"
check control-restored
