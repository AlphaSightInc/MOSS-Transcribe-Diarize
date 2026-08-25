#!/usr/bin/env bash
# Mutation sweep for the SHIPPED seam resolution (candidate 8e-2; the rule selected in
# `evidence/live-convergence-0824/M4-seam-overlap/`).
#
# `resolve_terminal_overlaps` exists because file mode's midpoint stitcher can publish one
# stretch of audio twice, and a live surface refuses the whole proposal when it does. Each
# mutation below is an OTHERWISE WORKING resolution that breaks exactly one of the rule's
# claims -- it resolves nothing, it merges two people, it invents a boundary, it deletes
# words, or it runs after the names are decided -- and must be caught by the test that NAMES
# that defect. A mutant caught by every test measures the harness, not the system.
#
# The corpus verifier runs beside the tests as a control: the trio is one 150 s window, so no
# arm here may move it. Every run replays recorded decodes: ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_terminal_seam.sh <out-dir>
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
  PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" -m pytest "$TESTS" -q \
    > "$OUT/$name-pytest.txt" 2>&1
  local tests=$?
  echo "$name: pytest exit=$tests  $(tail -1 "$OUT/$name-pytest.txt")" | tee -a "$OUT/summary.txt"
  grep -oE '^(FAILED|SUBFAILED\([^)]*\)) [^ ]+' "$OUT/$name-pytest.txt" \
    | sed 's/^/    /' | tee -a "$OUT/summary.txt"
  restore
}

: > "$OUT/summary.txt"
echo "== control: unmutated module ==" | tee -a "$OUT/summary.txt"
check control
echo "== control: the corpus verifier on the trio (one window, no seam) ==" | tee -a "$OUT/summary.txt"
PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" "$VERIFY" --output "$OUT/control.json" \
  > "$OUT/control-verify.txt" 2>&1
echo "control-verify: exit=$? $(tail -1 "$OUT/control-verify.txt")" | tee -a "$OUT/summary.txt"

# M1 -- the proposal is sorted and published as decoded. This is the behaviour that cost
# `lex_adam_frank` its entire terminal surface: the session refuses `segments_out_of_order`.
echo "== M1: no resolution at all ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '        if out and start < out[-1][2]:' \
  '        if False and out and start < out[-1][2]:'
check m1-no-resolution

# M2 -- overlapping segments merge whoever spoke them, so two people become one segment
# under one name and the terminal partition is destroyed.
echo "== M2: the merge ignores who spoke ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '            if previous_speaker == speaker:' \
  '            if True or previous_speaker == speaker:'
check m2-merge-across-speakers

# M3 -- the overlap is split at its midpoint: a timestamp no decoder produced, published as
# if it had (plan §3.4, the extent trap this campaign refuses).
echo "== M3: the seam is split at an invented boundary ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '            frontier = max(start, previous_end)' \
  '            frontier = max(start, (start + previous_end) // 2)
            out[-1] = (previous_speaker, previous_start, frontier, previous_text)'
check m3-invented-boundary

# M4 -- the later decoding is discarded whole (the `drop_later` arm): admissible, and it
# deletes seven of the corpus meeting's words to get there.
echo "== M4: the later decoding is dropped instead of merged ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '            if previous_speaker == speaker:
                out[-1] = (' \
  '            if previous_speaker == speaker:
                dropped += 1
                displaced += end - start
                continue
                out[-1] = ('
check m4-drop-later

# M5 -- the resolution runs, but the names are decided from the segments as decoded, so a
# stretch counted twice votes twice for the speaker it belongs to.
echo "== M5: the names are decided before the seam is resolved ==" | tee -a "$OUT/summary.txt"
patch "$CONV" \
  '        mapping = terminal_speaker_mapping(
            resolution.segments, base_surface=base_surface, canonical_speakers=canonical_speakers
        )' \
  '        mapping = terminal_speaker_mapping(
            placed, base_surface=base_surface, canonical_speakers=canonical_speakers
        )'
check m5-names-before-resolution

echo "== control after the sweep: the module is restored ==" | tee -a "$OUT/summary.txt"
check control-after
