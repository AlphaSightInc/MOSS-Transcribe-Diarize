#!/usr/bin/env bash
# Mutation sweep for the SHIPPED session text authority (plan §6 M3, §10.5 step 2, ADR-0005).
#
# Each mutation breaks one property the seam claims, in the production file itself, and must be
# caught -- by the end-to-end verifier against the grid's recorded column and measured speaker
# timeline, by a named T1 test, or by both. `live_session.py` is restored from a backup on exit,
# including on failure, and a control run after the sweep proves it was. Every run replays the
# grid's decode cache, so the sweep issues ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_session_authority.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="$REPO/moss_transcribe_diarize/app/live_session.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_session_text_authority.py"
TESTS="$REPO/tests/test_live_text_revision.py $REPO/tests/test_live_session.py"
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

: > "$OUT/summary.txt"
echo "== control: unmutated module ==" | tee -a "$OUT/summary.txt"
check control

# M1 -- rolling words publish with whatever the producer sent, so an unattributed revision stays
# unattributed. Guard: G2 (every rolling segment disagrees with the timeline the arm was
# measured through) and the T1 projection tests.
echo "== M1: the label projection never runs ==" | tee -a "$OUT/summary.txt"
patch '            if segment.canonical_speaker is not None' '            if True'
check m1-no-label-projection

# M2 -- attribution stops asking who owns the most of a stretch and always takes the nearest
# committed speech. Guard: G2 and the T1 majority-overlap test.
echo "== M2: projection by proximity instead of ownership ==" | tee -a "$OUT/summary.txt"
patch '    if overlap:
        return max(sorted(overlap, key=_speaker_order), key=lambda speaker: overlap[speaker])' \
      '    if False:
        return max(sorted(overlap, key=_speaker_order), key=lambda speaker: overlap[speaker])'
check m2-projection-by-proximity

# M3 -- a base segment that straddles the frontier is published beside the revision that already
# owns its first sample, so the surface says the same words twice (D4). Guard: G3's
# base-inside-prefix count, G1's WER, and the T1 straddle test.
echo "== M3: two owners at the frontier ==" | tee -a "$OUT/summary.txt"
patch 'suffix = tuple(segment for segment in base if segment.start_sample >= frontier)' \
      'suffix = tuple(segment for segment in base if segment.end_sample > frontier)'
check m3-two-owners-at-frontier

# M4 -- a rolling revision replaces the surface instead of extending it, which is the terminal
# producer's privilege alone. Guard: G1 (only the last window survives) and the T1 test that a
# second rolling revision builds on the first.
echo "== M4: rolling replaces instead of extends ==" | tee -a "$OUT/summary.txt"
patch '            self._revision_segments = self._revision_segments + segments' \
      '            self._revision_segments = segments'
check m4-rolling-replaces

# M5 -- the word-revision version never advances, so no producer can tell whether the base it
# proposed against is still current and no reader can tell a settled transcript from a repaired
# one. Guard: G5 (applied revisions != published version) and the T1 version assertions.
echo "== M5: the text revision version never advances ==" | tee -a "$OUT/summary.txt"
patch '        self._text_revision_version += 1
        self._surface_version += 1' '        self._surface_version += 1'
check m5-version-never-advances

echo "== restored; control run ==" | tee -a "$OUT/summary.txt"
check control-restored
