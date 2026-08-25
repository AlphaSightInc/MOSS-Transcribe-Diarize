#!/usr/bin/env bash
# Mutation sweep for the SHIPPED §7.4 event serialization of the rolling witness (plan §10.5
# step 5).
#
# Each mutation breaks one property the event stream claims, in a production file, and must be
# caught -- by the corpus verifier on real trio audio, by a named T2 test, or by both. Where
# only the test catches it, that is recorded as a finding rather than papered over: a stream
# that is complete on sixty seconds of unhurried speech is not a stream that is complete.
# Both production files are restored from backups on exit, including on failure, and a control
# run after the sweep proves it. Every run replays the grid's decode cache: ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_rolling_events.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
COORD="$REPO/moss_transcribe_diarize/app/live_coordinator.py"
RUNTIME="$REPO/moss_transcribe_diarize/app/live_service_runtime.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_rolling_events.py"
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

# M1 -- a window is planned but never announced, so the stream shows completions for work no
# reader saw queued and queue delay can never be computed. Guard: the verifier (G1/G2) and T2.
echo "== M1: a planned window is not announced ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" '            self._record_rolling_queued(state, result.rolling_windows)
            # Unconditional: this frame may have queued a rolling window rather than a' '            # Unconditional: this frame may have queued a rolling window rather than a'
patch "$RUNTIME" '                    self._record_rolling_queued(state, result.rolling_windows)
                    if not result.submitted:' '                    if not result.submitted:'
check m1-window-not-announced

# M2 -- the completion is emitted only where a decode actually answered, so a window nobody was
# waiting for, or one whose pump raised, silently disappears from the accounting. Guard: T2
# ONLY -- the trio corpus applies every window it plans and never takes either branch.
echo "== M2: only a decoded window is closed ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" '                self._record_rolling_completed(state, item.id, outcome, result)' '                if result is not None:
                    self._record_rolling_completed(state, item.id, outcome, result)'
check m2-only-decoded-windows-closed

# M3 -- an admission the arbiter refused is dropped instead of reported, which is the private
# counter this step exists to replace. Guard: T2 ONLY -- a refusal from a well-behaved producer
# needs the base a whole window ahead, which unhurried real-time audio never is.
echo "== M3: a refused admission is dropped ==" | tee -a "$OUT/summary.txt"
patch "$COORD" '            if admission.item_id is None:
                self._rolling_admission_refusals += 1
            plans.append(' '            if admission.item_id is None:
                self._rolling_admission_refusals += 1
                continue
            plans.append('
check m3-refused-admission-dropped

# M4 -- a refused revision is reported as an applied one, so a surface that never changed reads
# as corrected. Guard: T2 ONLY -- the trio corpus has no refusal to misreport, which is exactly
# why the T2 test manufactures a real one.
echo "== M4: a refusal is announced as an application ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" '            "text_revision_applied" if result.applied else "text_revision_refused",' '            "text_revision_applied",'
check m4-refusal-announced-as-application

# M5 -- the completion drops §7.4's decode record (elapsed, tokens, cap, RTF), leaving a stream
# a soak cannot measure witness cost from. Guard: the verifier (G2) and T2.
echo "== M5: the completion omits the decode record ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" '            "rolling_decode_rtf": None if result is None else result.decode_rtf,' '            "rolling_decode_rtf": None,'
check m5-completion-omits-decode-record

# M6 -- salvage stops being named, so the one policy event M1 shipped is invisible again.
# Guard: T2 ONLY -- this instrument's recorded decodes never reach the salvage gate, which is
# the finding G8 reports rather than hides.
echo "== M6: a salvaged span is not named ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" '                    if result.canonical_decode_salvage == SALVAGED_DISPOSITION:' '                    if False:'
check m6-salvage-not-named

echo "== restored; control run ==" | tee -a "$OUT/summary.txt"
check control-restored
