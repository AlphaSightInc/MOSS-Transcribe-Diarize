#!/usr/bin/env bash
# Mutation sweep for the SHIPPED terminal finalizer (plan E4 steps 4-6, plan §6 M6).
#
# Each mutation breaks one property the adapter claims -- that it reads the whole meeting,
# that it publishes the decoder's own partition, that it owns `[0, meeting_end)`, that its
# words stay inside the meeting, and that a failure names a type rather than the meeting's
# words -- and must be caught by the corpus verifier on real trio audio, by a named T1/T2
# test, or by both. Where only one catches it, that is recorded rather than papered over:
# a stub runner cannot reproduce a real album's sixteen births, and a corpus run cannot see
# a failure path a healthy meeting never takes.
# The production file is restored on exit, including on failure, and a control run after the
# sweep proves it. Every run replays recorded decodes: ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_terminal_finalizer.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
CONV="$REPO/moss_transcribe_diarize/app/live_transcript_convergence.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_terminal_finalizer.py"
TESTS="$REPO/tests/test_live_terminal_finalizer.py"
CONV_BACKUP="$(mktemp)"
cp "$CONV" "$CONV_BACKUP"
restore() { cp "$CONV_BACKUP" "$CONV"; }
trap 'restore; rm -f "$CONV_BACKUP"' EXIT
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
echo "== control: unmutated module ==" | tee -a "$OUT/summary.txt"
check control

# M1 -- the terminal pass names its speakers one segment at a time, like a rolling window.
# This is the arm the verifier measures and rejects (ADR-0005 D8); with the mapping gone,
# NEITHER arm preserves the terminal partition and the selection has nothing to ship.
echo "== M1: naming falls back to the per-segment projection ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '    matrix = [[-overlap[(local, canonical)] for canonical in speakers] for local in locals_]' \
  '    return {}
    matrix = [[-overlap[(local, canonical)] for canonical in speakers] for local in locals_]'
check m1-per-segment-naming

# M2 -- the assignment stops being one-to-one: every local speaker takes its own best
# canonical match, so two terminal speakers may collapse onto one person.
echo "== M2: the mapping allows two speakers to become one ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '    rows, columns = linear_sum_assignment(matrix)
    return {
        locals_[row]: speakers[column]
        for row, column in zip(rows, columns, strict=True)
        if overlap[(locals_[row], speakers[column])] > 0
    }' \
  '    return {
        local: max(speakers, key=lambda canonical: overlap[(local, canonical)])
        for local in locals_
        if max(overlap[(local, canonical)] for canonical in speakers) > 0
    }'
check m2-many-to-one-mapping

# M3 -- the terminal proposal starts where rolling authority reached instead of at sample 0,
# so it extends the surface rather than replacing it. The session refuses it by name.
echo "== M3: terminal extends the surface instead of replacing it ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '                source="terminal",
                start_sample=0,' \
  '                source="terminal",
                start_sample=plan.rolling_through_sample,'
check m3-terminal-does-not-replace

# M4 -- the words are placed on the clock without the grammar reader's clamp, so a decoder
# that closes its last segment a tick past the audio publishes outside the meeting.
echo "== M4: timestamps are not clamped into the meeting ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '            for item in span_segments(str(getattr(result, "text", "") or ""), sample_count=end_sample)' \
  '            for item in parse_transcript(str(getattr(result, "text", "") or ""))'
patch "$CONV" \
  'from .live_span_bounds import span_segments' \
  'from moss_transcribe_diarize.transcript_parser import parse_transcript
from .live_span_bounds import span_segments'
check m4-unclamped-timestamps

# M5 -- a tape that refuses `[0, meeting_end)` is asked for whatever it happens to hold, so a
# short or holed tape finalizes a meeting that is not the meeting.
echo "== M5: a refused tape is retried for whatever it holds ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '        except CompleteMixedTapeUnavailable as exc:
            return self._refused(plan, TerminalOutcome.TAPE_UNAVAILABLE, str(exc), gaps=gaps)' \
  '        except CompleteMixedTapeUnavailable as exc:
            try:
                pcm = tape.read(start_sample=0)
            except CompleteMixedTapeUnavailable:
                return self._refused(plan, TerminalOutcome.TAPE_UNAVAILABLE, str(exc), gaps=gaps)'
check m5-refused-tape-retried

# M6 -- the decode failure carries the runner's message instead of its type, so a rejected
# answer's words reach telemetry (plan §7.4: counts, samples, timings and names only).
echo "== M6: a failure reports the words it rejected ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '                    exc.__class__.__name__,
                    gaps=gaps,' \
  '                    str(exc),
                    gaps=gaps,'
check m6-failure-carries-words

echo "== control: restored modules ==" | tee -a "$OUT/summary.txt"
check control-restored
