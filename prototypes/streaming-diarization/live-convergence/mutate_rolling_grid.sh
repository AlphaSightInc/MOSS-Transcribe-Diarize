#!/usr/bin/env bash
# Mutation sweep for compare_rolling_grid.py (plan §10.2-§10.4).
#
# Each mutation breaks one property the grid claims to hold, on a throwaway COPY of the script,
# and must be caught by the guard that claims it -- and by no other. Every mutation replays the
# decode cache the real run wrote, so the sweep issues ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_rolling_grid.sh <cache-dir> <out-dir>
set -u

CACHE="${1:?cache dir from the real run}"
OUT="${2:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="$REPO/prototypes/streaming-diarization/live-convergence/compare_rolling_grid.py"
# Mutants live BESIDE the original, not in /tmp: the script resolves the repo root from its own
# path (`parents[3]`), so a copy at any other depth cannot import the bench at all -- the failure
# would look like a caught mutation while proving nothing. Removed on exit.
WORK="$(dirname "$SRC")"
PREFIX="_mutant_$$"
trap 'rm -f "$WORK/$PREFIX"*.py' EXIT
mkdir -p "$OUT"

run() {  # run <name> <script> <extra args...>
  local name="$1"; shift
  local script="$1"; shift
  PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" "$script" \
    --cache-dir "$CACHE" --output "$OUT/$name.json" "$@" \
    > "$OUT/$name.txt" 2>&1
  echo $?
}

patch() {  # patch <name> <python-snippet-applied-to-source>
  local name="$1"; shift
  cp "$SRC" "$WORK/$PREFIX-$name.py"
  MUT_PATH="$WORK/$PREFIX-$name.py" "$REPO/.venv/bin/python" - "$@" <<'PY'
import os, sys
from pathlib import Path
path = Path(os.environ["MUT_PATH"])
text = path.read_text()
old, new = sys.argv[1], sys.argv[2]
assert old in text, f"anchor not found for {path.name}"
path.write_text(text.replace(old, new, 1))
PY
}

echo "== control: unmutated script, cached replay ==" | tee "$OUT/summary.txt"
CODE=$(run control "$SRC" --runs 1)
echo "control exit=$CODE  selected=$(grep -o 'SELECTED.*' "$OUT/control.txt")" | tee -a "$OUT/summary.txt"

# M1 -- the reconciler reads reference truth. Guard: the _TruthBlind tripwire.
patch m1-truth-blind \
  '    covered_lo = windows[0]["range"][0]' \
  '    bench.load_reference("lex_bill_ackman")
    covered_lo = windows[0]["range"][0]'
CODE=$(run m1-truth-blind "$WORK/$PREFIX-m1-truth-blind.py" --runs 1 --cases lex_bill_ackman --windows 10/5)
echo "M1 truth-blind exit=$CODE  $(grep -c ReferenceReadInsideReconciler "$OUT/m1-truth-blind.txt") tripwire hits" | tee -a "$OUT/summary.txt"

# M2 -- the per-case comparator drifts away from the PRD's printed value. Guard: the
# round-trip assertion in load_baseline_scores.
patch m2-comparator-drift \
  '"lex_javier_milei": 0.1440,' \
  '"lex_javier_milei": 0.1450,'
CODE=$(run m2-comparator-drift "$WORK/$PREFIX-m2-comparator-drift.py" --runs 1 --cases lex_javier_milei --windows 10/5)
echo "M2 comparator drift exit=$CODE  $(grep -c comparator_drift "$OUT/m2-comparator-drift.txt") drift hits" | tee -a "$OUT/summary.txt"

# M3 -- ownership regions computed by the literal a2 formula instead of the midpoint of the
# overlap. Guard: the RegionsDoNotTile invariant, because 15/10's clamped last window then owns
# [47.5, 52.5] twice and would republish those words. (The join-duplicate screen does NOT catch
# this: it compares the committed TAIL with the fresh HEAD, and this defect duplicates words in
# the middle of the previous window's take. It was the first guard tried, and it stayed silent --
# which is why the invariant exists.)
patch m3-a2-region-formula \
  '        region_lo = 0.0 if index == 0 else (ranges[index][0] + ranges[index - 1][1]) / 2
        region_hi = (
            duration
            if index == len(ranges) - 1
            else (ranges[index + 1][0] + ranges[index][1]) / 2
        )' \
  '        region_lo = lo if index == 0 else lo + (window - stride) / 2
        region_hi = hi if index == len(ranges) - 1 else lo + (window + stride) / 2'
CODE=$(run m3-a2-region-formula "$WORK/$PREFIX-m3-a2-region-formula.py" --runs 1 --windows 15/10 --stitches char)
echo "M3 a2 region formula exit=$CODE  $(grep -c RegionsDoNotTile "$OUT/m3-a2-region-formula.txt") tiling-invariant hits" | tee -a "$OUT/summary.txt"
echo "   control 15/10 char arm row: $(grep -E '^ *15/10:char ' "$OUT/control.txt")" | tee -a "$OUT/summary.txt"

# M4 -- selection ranks on quality instead of cost. Guard: none -- this is the mutation that
# proves plan §10.4's rule is what picks the arm, by showing a different arm is picked when the
# rule changes.
patch m4-select-by-wer \
  '                arms[name]["added_decode_audio_seconds_per_audio_second"],
                arms[name]["joins_per_case"],
                arms[name]["wer"]["mean"],' \
  '                arms[name]["wer"]["mean"],
                arms[name]["joins_per_case"],
                arms[name]["added_decode_audio_seconds_per_audio_second"],'
CODE=$(run m4-select-by-wer "$WORK/$PREFIX-m4-select-by-wer.py" --runs 1)
echo "M4 select-by-WER exit=$CODE  $(grep -o 'SELECTED.*' "$OUT/m4-select-by-wer.txt")" | tee -a "$OUT/summary.txt"

# M5 -- the provisional base loses half its spans, so the bench no longer reproduces the
# published live means. Guard: P1, which must invalidate the whole grid rather than report a
# verdict against a broken baseline.
patch m5-broken-base \
  '    for span in spans:
        start, end = span["start_sample"], span["end_sample"]
        decoded = decoder.decode(' \
  '    for span in spans[::2]:
        start, end = span["start_sample"], span["end_sample"]
        decoded = decoder.decode('
CODE=$(run m5-broken-base "$WORK/$PREFIX-m5-broken-base.py" --runs 1)
echo "M5 broken base exit=$CODE  $(grep -A1 'base control' "$OUT/m5-broken-base.txt" | tail -1)" | tee -a "$OUT/summary.txt"
echo "   $(grep -o 'SELECTED.*' "$OUT/m5-broken-base.txt")" | tee -a "$OUT/summary.txt"

echo "mutants were written beside the original as $PREFIX-*.py and removed on exit" | tee -a "$OUT/summary.txt"
