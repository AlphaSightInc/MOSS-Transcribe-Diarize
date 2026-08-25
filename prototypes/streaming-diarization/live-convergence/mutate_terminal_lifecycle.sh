#!/usr/bin/env bash
# Mutation sweep for the SHIPPED terminal lifecycle (plan §12.3, D-M4-3).
#
# Each mutation breaks one promise the lifecycle makes to a reader who is still polling after
# Stop -- that the stop request does not decode, that the audio outlives the meeting by
# exactly one listener, that every ending has a word, that a deployment which kept nothing
# says so, that a published surface is never un-finalized, and that rolling ending early does
# not cancel the meeting's last listener -- and must be caught by the corpus verifier on real
# trio audio, by a named T2 test, or by both. Where only one catches it, that is recorded
# rather than papered over: sixty seconds of healthy corpus audio never takes a witness-defect
# branch, and a scripted runtime cannot produce a file arm's score.
#
# Three production files are mutated (`live_service_runtime.py`, `live_session.py`,
# `live_coordinator.py`); all three are restored on exit, including on failure, and a control
# run after the sweep proves it. Every run replays recorded decodes: ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_terminal_lifecycle.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
RUNTIME="$REPO/moss_transcribe_diarize/app/live_service_runtime.py"
COORD="$REPO/moss_transcribe_diarize/app/live_coordinator.py"
SESSION="$REPO/moss_transcribe_diarize/app/live_session.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_terminal_lifecycle.py"
TESTS="$REPO/tests/test_live_terminal_lifecycle.py"
RUNTIME_BACKUP="$(mktemp)"
COORD_BACKUP="$(mktemp)"
SESSION_BACKUP="$(mktemp)"
cp "$RUNTIME" "$RUNTIME_BACKUP"
cp "$COORD" "$COORD_BACKUP"
cp "$SESSION" "$SESSION_BACKUP"
restore() {
  cp "$RUNTIME_BACKUP" "$RUNTIME"
  cp "$COORD_BACKUP" "$COORD"
  cp "$SESSION_BACKUP" "$SESSION"
}
trap 'restore; rm -f "$RUNTIME_BACKUP" "$COORD_BACKUP" "$SESSION_BACKUP"' EXIT
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
    --cases lex_bill_ackman --output "$OUT/$name.json" > "$OUT/$name-verify.txt" 2>&1
  local verify=$?
  PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" -m pytest $TESTS -q \
    > "$OUT/$name-pytest.txt" 2>&1
  local tests=$?
  echo "$name: verify exit=$verify  pytest exit=$tests  $(tail -1 "$OUT/$name-pytest.txt")" \
    | tee -a "$OUT/summary.txt"
  grep -E '^(FAIL|PASS|Traceback|AssertionError|  - L)' "$OUT/$name-verify.txt" \
    | head -5 | sed 's/^/    /' | tee -a "$OUT/summary.txt"
  restore
}

: > "$OUT/summary.txt"
echo "== control: unmutated modules ==" | tee -a "$OUT/summary.txt"
check control

# M1 -- the meeting's audio is released where it used to be, at the end of `stop`, so the
# pass that was just scheduled reads a released tape. This is the ordering E4 moved, and the
# reason it had to move: the tape and its last reader are one lifetime, not two.
echo "== M1: the tape is released before its reader runs ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" \
  '            if not self._begin_terminal_locked(state):
                self._release_tape_locked(state)' \
  '            self._begin_terminal_locked(state)
            self._release_tape_locked(state)'
check m1-release-before-terminal

# M2 -- the stop request runs the terminal decode itself. Plan §12.3's last paragraph exists
# because that is minutes of work on a request a client is holding open.
echo "== M2: the stop request decodes the whole meeting ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" \
  '        self._terminal_scheduler.submit(lambda: self._run_terminal(state, plan, tape))' \
  '        self._run_terminal(state, plan, tape)'
check m2-stop-decodes-inline

# M3 -- a pass that published nothing leaves the status where it was, so a meeting whose
# terminal decode failed reads `running` forever and a polling reader never stops.
echo "== M3: a failed pass leaves the status running ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" \
  '            status = state.session.note_finalization(payload["finalization_status"])' \
  '            status = state.session.snapshot().finalization_status'
check m3-failed-pass-stays-running

# M4 -- a deployment that named a finalizer and kept no tape says nothing at all, so
# "nobody tried" and "there was nothing to try on" become the same reading.
echo "== M4: a meeting with no tape is silently not finalized ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" \
  '            reason = "no_retained_tape" if tape is None else "no_terminal_plan"' \
  '            return False
            reason = "no_retained_tape" if tape is None else "no_terminal_plan"'
check m4-silent-when-unavailable

# M5 -- the status stops being monotonic, so a straggler pass over a released tape turns a
# surface a reader was already shown back into `unavailable`.
echo "== M5: a finalized surface can be un-finalized ==" | tee -a "$OUT/summary.txt"
patch "$SESSION" \
  '        if self._finalization_status in {"final", status}:
            return self._finalization_status' \
  '        if self._finalization_status == status:
            return self._finalization_status'
check m5-status-not-monotonic

# M6 -- rolling ending early cancels the terminal pass: `stop_rolling` answers only its first
# caller, so a witness defect mid-meeting leaves the meeting with no plan and no last listener.
echo "== M6: a witness that died mid-meeting cancels terminal ==" | tee -a "$OUT/summary.txt"
patch "$COORD" \
  '        converger = self.converger
        if converger is None:
            return None
        return converger.stop(self.session.snapshot().accepted_samples)' \
  '        converger = self.converger
        if converger is None:
            return None
        if converger.accounting().status is RollingStatus.STOPPED:
            return None
        return converger.stop(self.session.snapshot().accepted_samples)'
check m6-rolling-death-cancels-terminal

echo "== control: restored modules ==" | tee -a "$OUT/summary.txt"
check control-restored
