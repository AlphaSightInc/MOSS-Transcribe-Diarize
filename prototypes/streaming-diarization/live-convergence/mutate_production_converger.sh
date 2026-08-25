#!/usr/bin/env bash
# Mutation sweep for the SHIPPED rolling converger (plan §6 M2, §10.5 step 1).
#
# Each mutation breaks one property the module claims, in the production file itself, and must
# be caught -- by the verifier's gate against the grid's recorded column, by a named T1 test, or
# by both. The module is restored from a backup on exit, including on failure, and a control run
# after the sweep proves it was. Every run replays the grid's decode cache, so the sweep issues
# ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_production_converger.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="$REPO/moss_transcribe_diarize/app/live_transcript_convergence.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_production_converger.py"
TESTS="$REPO/tests/test_live_transcript_convergence.py"
BACKUP="$(mktemp)"
cp "$SRC" "$BACKUP"
trap 'cp "$BACKUP" "$SRC"; rm -f "$BACKUP"' EXIT
mkdir -p "$OUT"

patch() {  # patch <old> <new>
  MUT_PATH="$SRC" "$REPO/.venv/bin/python" - "$@" <<'PY'
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
  PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" -m pytest "$TESTS" -q \
    > "$OUT/$name-pytest.txt" 2>&1
  local tests=$?
  echo "$name: verify exit=$verify  pytest exit=$tests  $(tail -1 "$OUT/$name-pytest.txt")" \
    | tee -a "$OUT/summary.txt"
  grep -E '^(FAIL|PASS|Traceback|AssertionError|.*CacheMiss)' "$OUT/$name-verify.txt" \
    | head -4 | sed 's/^/    /' | tee -a "$OUT/summary.txt"
  cp "$BACKUP" "$SRC"
}

: > "$OUT/summary.txt"
echo "== control: unmutated module ==" | tee -a "$OUT/summary.txt"
check control

# M1 -- an overlapping geometry ships without the stitcher no grid ever selected. Guard: the
# UnmeasuredRollingGeometry refusal (T1), and after removing it, the D4 frontier check the
# session applies -- window 1 starts 5 s behind the frontier window 0 already moved.
echo "== M1: overlapping stride, guard removed ==" | tee -a "$OUT/summary.txt"
patch 'ROLLING_STRIDE_SECONDS = 10.0' 'ROLLING_STRIDE_SECONDS = 5.0'
patch '        if self.stride_samples != self.window_samples:' '        if False:'
check m1-overlap-no-stitcher

# M2 -- the decode budget stops being derived from the window it decodes. Guard: the grid's
# decode cache is keyed by token cap, so the replay can no longer find the decode the selected
# arm was measured with, and the runner that would answer instead raises.
echo "== M2: token cap not derived from the window ==" | tee -a "$OUT/summary.txt"
patch 'token_cap=canonical_decode_token_cap(sample_count=self.geometry.window_samples),' \
      'token_cap=2048,'
check m2-token-cap

# M3 -- the window grid never advances, so the converger re-owns the audio it already revised.
# Guard: the frontier condition stops planning after one window (G4), and the WER falls back to
# one window of rolling over a provisional-free surface (G1/G2).
echo "== M3: window index never advances ==" | tee -a "$OUT/summary.txt"
patch '        self._next_window_index += 1
        self._windows_planned += 1' '        self._windows_planned += 1'
check m3-frozen-window-index

# M4 -- retained audio is never released, so the ring grows past the plan §6 M2 bound and the
# eviction it forces stops rolling convergence. Guard: G4's rolling status and G5's bound.
echo "== M4: retention never released ==" | tee -a "$OUT/summary.txt"
patch '        if drop > 0:
            del self._buffer[:drop]
            self._buffer_start_sample = keep_from' '        if False:
            del self._buffer[:drop]
            self._buffer_start_sample = keep_from'
check m4-retention-never-released

# M5 -- a window that published nothing advances the frontier over an interval with no words in
# it. Guard: the T1 stall test. The verifier cannot catch this one and says so: zero of the 54
# window decodes at this geometry published nothing, which is exactly why the behaviour needs a
# test rather than a corpus.
echo "== M5: an empty window proposes anyway ==" | tee -a "$OUT/summary.txt"
patch '        if not segments:
            self._windows_failed += 1
            self._status = RollingStatus.WINDOW_FAILED
            return None' '        if not segments:
            self._windows_failed += 1'
check m5-empty-window-proposes

echo "== restored; control run ==" | tee -a "$OUT/summary.txt"
check control-restored
