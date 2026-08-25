#!/usr/bin/env bash
# Mutation sweep for the SHIPPED complete mixed tape (plan E4 step 1, precondition P-M4-B).
#
# Each mutation breaks one property the tape claims -- fidelity, completeness, the gap
# manifest, the retention bound, the release, or the meeting's independence from all of it --
# in a production file, and must be caught by the corpus verifier on real trio audio, by a
# named T1/T2 test, or by both. Where only one catches it, that is recorded rather than
# papered over: sixty seconds of unhurried speech cannot reach a capacity bound, and a test
# that never runs the runtime cannot see a coordinator that forgot to tape.
# Every production file is restored on exit, including on failure, and a control run after the
# sweep proves it. Every run replays the grid's decode cache: ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_terminal_tape.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
TAPE="$REPO/moss_transcribe_diarize/app/live_tape.py"
COORD="$REPO/moss_transcribe_diarize/app/live_coordinator.py"
RUNTIME="$REPO/moss_transcribe_diarize/app/live_service_runtime.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_terminal_tape.py"
TESTS="$REPO/tests/test_live_terminal_tape.py"
TAPE_BACKUP="$(mktemp)"
COORD_BACKUP="$(mktemp)"
RUNTIME_BACKUP="$(mktemp)"
cp "$TAPE" "$TAPE_BACKUP"
cp "$COORD" "$COORD_BACKUP"
cp "$RUNTIME" "$RUNTIME_BACKUP"
restore() { cp "$TAPE_BACKUP" "$TAPE"; cp "$COORD_BACKUP" "$COORD"; cp "$RUNTIME_BACKUP" "$RUNTIME"; }
trap 'restore; rm -f "$TAPE_BACKUP" "$COORD_BACKUP" "$RUNTIME_BACKUP"' EXIT
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

# M1 -- the tape drops the meeting's first frame. The digest and the sample count both move,
# and the gap manifest names the hole rather than letting two counts be subtracted to zero.
echo "== M1: the first frame is not taped ==" | tee -a "$OUT/summary.txt"
patch "$COORD" \
  '        if self.tape is not None:
            # Never checked' \
  '        if self.tape is not None and ack.start_sample > 0:
            # Never checked'
check m1-first-frame-not-taped

# M2 -- the tape reports its own count as the extent it was asked about, so a short tape
# looks complete. This is the defect the gap manifest exists to make impossible.
echo "== M2: the tape grades its own extent ==" | tee -a "$OUT/summary.txt"
patch "$COORD" \
  'return self.tape.accounting(through_sample=self.session.snapshot().accepted_samples)' \
  'return self.tape.accounting(through_sample=self.tape.sample_count)'
check m2-tape-grades-itself

# M3 -- the declared capacity is ignored, so an unbounded meeting is retained unbounded.
# ADR-0003 D5's whole point: a bound nobody enforces is a bound nobody has.
echo "== M3: the declared capacity is not enforced ==" | tee -a "$OUT/summary.txt"
patch "$TAPE" \
  '            if len(self._buffer) + len(pcm) > self.capacity_bytes:' \
  '            if False:'
check m3-capacity-not-enforced

# M4 -- the tape is never released, so a meeting's audio outlives the meeting (D3).
echo "== M4: the tape survives the session ==" | tee -a "$OUT/summary.txt"
patch "$RUNTIME" \
  '        accounting = state.coordinator.release_tape()
        if accounting is None:
            return' \
  '        accounting = state.coordinator.tape_accounting()
        if accounting is None:
            return'
check m4-tape-survives-the-session

# M5 -- a hole is filled with silence instead of refused. The bytes still tile, the counts
# still add up, and a terminal pass would decode audio the meeting never contained.
echo "== M5: a hole is zero-filled instead of refused ==" | tee -a "$OUT/summary.txt"
patch "$TAPE" \
  '            if start_sample != self._sample_count:' \
  '            if start_sample > self._sample_count:
                self._buffer.extend(b"\x00" * ((start_sample - self._sample_count) * PCM16_BYTES_PER_SAMPLE))
                self._digest.update(b"\x00" * ((start_sample - self._sample_count) * PCM16_BYTES_PER_SAMPLE))
                self._covered = _merge(self._covered, self._sample_count, start_sample)
                self._sample_count = start_sample
            if start_sample != self._sample_count:'
check m5-hole-zero-filled

# M6 -- a frame the tape cannot take raises instead of degrading, so storage pressure ends
# the meeting. ADR-0003 D5 forbids exactly this.
echo "== M6: tape pressure raises at a frame ==" | tee -a "$OUT/summary.txt"
patch "$TAPE" \
  '                self._refused_samples += samples
                return self._degrade(
                    TAPE_CAPACITY_EXHAUSTED,' \
  '                self._refused_samples += samples
                raise RuntimeError("tape capacity exhausted")
                return self._degrade(
                    TAPE_CAPACITY_EXHAUSTED,'
check m6-pressure-raises-at-a-frame

echo "== control: restored modules ==" | tee -a "$OUT/summary.txt"
check control-restored

echo "sweep complete: $OUT/summary.txt"
