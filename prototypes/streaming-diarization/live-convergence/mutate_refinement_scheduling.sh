#!/usr/bin/env bash
# Mutation sweep for the SHIPPED live_refinement queue (plan §6 M5, §10.5 step 3).
#
# Each mutation breaks one property the scheduler claims, in the production file itself, and must
# be caught -- by the three-session verifier, by a named T1 test, or by both. Where only the T1
# test catches it, that is recorded as a finding rather than papered over: the converger is a
# well-behaved producer (one window in flight, one key per session), so the corpus simply cannot
# reach the coalesce and suppress branches. `live_arbiter.py` is restored from a backup on exit,
# including on failure, and a control run after the sweep proves it was. Every run replays the
# grid's decode cache, so the sweep issues ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_refinement_scheduling.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="$REPO/moss_transcribe_diarize/app/live_arbiter.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_refinement_scheduling.py"
TESTS="$REPO/tests/test_live_arbiter_refinement.py $REPO/tests/test_live_vad.py"
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
  PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" -m pytest $TESTS -q \
    > "$OUT/$name-pytest.txt" 2>&1
  local tests=$?
  echo "$name: verify exit=$verify  pytest exit=$tests  $(tail -1 "$OUT/$name-pytest.txt")" \
    | tee -a "$OUT/summary.txt"
  grep -E '^(FAIL|PASS|Traceback|AssertionError)' "$OUT/$name-verify.txt" \
    | head -4 | sed 's/^/    /' | tee -a "$OUT/summary.txt"
  cp "$BACKUP" "$SRC"
}

CANONICAL_BLOCK='        if self._live_canonical:
            item = self._live_canonical.popleft()
            self._live_canonical_weight -= item.weight
            return item
'
REFINEMENT_BLOCK='        if self._live_refinement:
            _, item = self._live_refinement.popitem(last=False)
            self._running_refinements[item.key] = item.id
            return item
'
PROVISIONAL_BLOCK='        if self._live_provisional:
            _, item = self._live_provisional.popitem(last=False)
            return item
'

: > "$OUT/summary.txt"
echo "== control: unmutated module ==" | tee -a "$OUT/summary.txt"
check control

# M1 -- the rolling witness outranks the 2.5 s span a listener is waiting on, which is exactly
# what plan §10.6 forbids. Guard: G2 (witnesses dispatched while canonical work waits) and the
# T1 priority tests.
echo "== M1: refinement outranks canonical ==" | tee -a "$OUT/summary.txt"
patch "$CANONICAL_BLOCK$REFINEMENT_BLOCK" "$REFINEMENT_BLOCK$CANONICAL_BLOCK"
check m1-refinement-outranks-canonical

# M2 -- the witness sits below provisional work, which is regenerated every frame, so it is
# starved. Guard: T1 ONLY. The verifier submits no provisional work (the base path in this
# driver is canonical spans), so the corpus is blind to this branch -- recorded, not hidden.
echo "== M2: refinement ranks below provisional ==" | tee -a "$OUT/summary.txt"
patch "$REFINEMENT_BLOCK$PROVISIONAL_BLOCK" "$PROVISIONAL_BLOCK$REFINEMENT_BLOCK"
check m2-refinement-below-provisional

# M3 -- dispatching stops marking the witness running, so nothing protects a running MOSS
# request and every release matches nothing. Guard: G3 (unreleased releases) and the T1
# running/release tests.
echo "== M3: dispatch does not mark the witness running ==" | tee -a "$OUT/summary.txt"
patch '            self._running_refinements[item.key] = item.id' '            pass'
check m3-dispatch-does-not-mark-running

# M4 -- a newer witness is admitted over a running one, i.e. a MOSS request already burning GPU
# is abandoned. Guard: T1 ONLY. The converger never submits a second witness while one is in
# flight, so the corpus cannot reach this branch -- recorded, not hidden.
echo "== M4: a newer witness cancels a running one ==" | tee -a "$OUT/summary.txt"
patch '        if coalesce_key in self._running_refinements:' '        if False:'
check m4-newer-witness-cancels-running

# M5 -- release reports success without clearing the mark, so the session is blocked forever
# after its first window. Guard: G4/G5 (five of six windows never dispatched, suppressed > 0)
# and the T1 release tests.
echo "== M5: release never clears the running mark ==" | tee -a "$OUT/summary.txt"
patch '        del self._running_refinements[key]
        return True' '        return True'
check m5-release-never-clears

echo "== restored; control run ==" | tee -a "$OUT/summary.txt"
check control-restored
