#!/usr/bin/env bash
# Mutation sweep for the SHIPPED export switch (plan §10.5 step 7).
#
# Each mutation breaks one property the exported transcript claims, in production code, and must
# be caught -- by the corpus verifier on real trio audio, by a named T3 test, or by both. Where
# only the test catches it, that is recorded as a finding rather than papered over: the checked-in
# corpora contain no relabelled span and no unestablished identity, so real audio cannot reach
# every branch a saved snapshot can. The production files are restored from a backup on exit,
# including on failure, and a control run after the sweep proves it. Every run replays the grid's
# decode cache: ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_export_surface.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
EXPORT="$REPO/moss_transcribe_diarize/live_speaker_accuracy.py"
SURFACE="$REPO/moss_transcribe_diarize/live_surface.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_export_surface.py"
TESTS="$REPO/tests/test_live_export_surface.py $REPO/tests/test_live_speaker_accuracy.py"
EXPORT_BACKUP="$(mktemp)"
SURFACE_BACKUP="$(mktemp)"
cp "$EXPORT" "$EXPORT_BACKUP"
cp "$SURFACE" "$SURFACE_BACKUP"
restore() { cp "$EXPORT_BACKUP" "$EXPORT"; cp "$SURFACE_BACKUP" "$SURFACE"; }
trap 'restore; rm -f "$EXPORT_BACKUP" "$SURFACE_BACKUP"' EXIT
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
    --cases lex_bill_ackman,lex_javier_milei --output "$OUT/$name.json" \
    > "$OUT/$name-verify.txt" 2>&1
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
echo "== control: unmutated export ==" | tee -a "$OUT/summary.txt"
check control

# M1 -- the pre-step-7 export: re-derive the transcript from the committed spans even when the
# session published a surface, so a rolling correction the reader watched land never reaches the
# file. Guard: the verifier (G3 -- the rolling arm's numbers fall back to the base arm's, and
# G4 -- the file stops matching the screen) and T3.
echo "== M1: export the committed spans even when a surface exists ==" | tee -a "$OUT/summary.txt"
patch "$EXPORT" '    if "effective_transcript" in session:
        return _hypothesis_from_surface(' '    if False and "effective_transcript" in session:
        return _hypothesis_from_surface('
check M1

# M2 -- print the canonical identity instead of the token the meeting is written in. A reader of
# the file then sees a name no other row, event or reference uses. Guard: the verifier (G1/G4)
# and T3.
echo "== M2: export the canonical identity, not the Sxx token ==" | tee -a "$OUT/summary.txt"
patch "$EXPORT" '                    speaker=published_speaker_label(canonical_speaker, speakers),' '                    speaker=str(canonical_speaker),'
check M2

# M3 -- an identity this snapshot never established is exported as the first speaker instead of
# the honest unattributed token: a guess, published as fact. Guard: T3 (the corpora establish
# every identity their surfaces carry, so real audio cannot reach this branch).
echo "== M3: an unestablished identity is exported as the first speaker ==" | tee -a "$OUT/summary.txt"
patch "$SURFACE" '    except ValueError:
        return UNATTRIBUTED_SPEAKER' '    except ValueError:
        return display_speaker_label(tuple(canonical_speakers)[0], canonical_speakers)'
check M3

# M4 -- stop clamping to the corpus window, so a segment that runs past the reference is scored
# against audio the reference never covered. Guard: T3 (the trio sessions end inside their own
# corpus, so nothing on real audio crosses the boundary).
echo "== M4: the export no longer clamps to the corpus window ==" | tee -a "$OUT/summary.txt"
patch "$EXPORT" '        start = max(0.0, (start_sample - corpus_start_sample) / float(LIVE_SAMPLE_RATE))
        end = min(
            float(corpus_duration_sec), (end_sample - corpus_start_sample) / float(LIVE_SAMPLE_RATE)
        )' '        start = (start_sample - corpus_start_sample) / float(LIVE_SAMPLE_RATE)
        end = (end_sample - corpus_start_sample) / float(LIVE_SAMPLE_RATE)'
check M4

# M5 -- the fallback reads the text as first decoded instead of the span's published words, so a
# pre-surface snapshot whose labels a sweep corrected exports the labels the sweep replaced.
# Guard: T3 (no checked-in baseline carries a relabelled span; G5 cannot see this).
echo "== M5: the fallback ignores a sweep's correction ==" | tee -a "$OUT/summary.txt"
patch "$EXPORT" '        transcript = (
            item.get("revised_transcript")
            if item.get("revised_transcript") is not None
            else item.get("transcript")
        )' '        transcript = item.get("transcript")'
check M5

# M6 -- publish a surface segment whose words are whitespace, which puts an empty speaker turn in
# the file and, through the activity reading, an interval nobody spoke into the diarization
# score. Guard: T3 (the deployed session drops empty segments before they reach the surface).
echo "== M6: whitespace-only surface segments become rows ==" | tee -a "$OUT/summary.txt"
patch "$EXPORT" '        if not text.strip():
            continue' '        if False:
            continue'
check M6

echo "== control: restored export ==" | tee -a "$OUT/summary.txt"
check control-after
