#!/usr/bin/env bash
# Is each M2 exit gate actually reading the artifact it claims to read?
#
#   mutate_m2_exit.sh <fresh-root> <out-dir>
#
# Works on a COPY of the measurement passes -- the originals are never touched. One mutation
# per gate, applied to the copy, verifier re-run, target file restored. A gate that does not
# flip when its own evidence is corrupted is not measuring anything.
#
# M4 is a SENSITIVITY probe rather than a caught mutation, and says so: the measurement already
# misses that gate, so a mutation cannot "catch" it by breaking it further. The probe instead
# moves the artifact in the direction that would make the gate pass, which shows the number is
# read from the clock rather than asserted.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="$REPO/.venv/bin/python"
SRC="${1:?usage: mutate_m2_exit.sh <fresh-root> <out-dir>}"
OUT="${2:?usage: mutate_m2_exit.sh <fresh-root> <out-dir>}"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_m2_exit.py"
ROOT="$OUT/root"

mkdir -p "$OUT"
rm -rf "$ROOT"
cp -R "$SRC" "$ROOT"

run() {  # run <label>
  local label="$1"
  PYTHONDONTWRITEBYTECODE=1 "$PY" "$VERIFY" --fresh-root "$ROOT" --output "$OUT/$label.json" \
    >"$OUT/$label.console.txt" 2>&1
  local rc=$?
  local flipped
  flipped=$(PYTHONDONTWRITEBYTECODE=1 "$PY" - "$OUT/control.json" "$OUT/$label.json" <<'PY'
import json, sys
control = json.load(open(sys.argv[1]))["gates"]
mutant = json.load(open(sys.argv[2]))["gates"]
rows = [
    f"{name}:{control[name]['pass']}->{mutant[name]['pass']}"
    for name in control
    if not name.startswith("_") and control[name]["pass"] != mutant[name]["pass"]
]
print(",".join(rows) if rows else "-")
PY
)
  echo "$label exit=$rc flipped=$flipped" | tee -a "$OUT/mutations.txt"
}

patch() {  # patch <python-snippet-file>
  PYTHONDONTWRITEBYTECODE=1 "$PY" "$1" "$ROOT"
}

snippet() {  # snippet <name> <<'PY' ... PY
  cat >"$OUT/$1.py"
}

echo "== control ==" | tee "$OUT/mutations.txt"
PYTHONDONTWRITEBYTECODE=1 "$PY" "$VERIFY" --fresh-root "$ROOT" --output "$OUT/control.json" \
  >"$OUT/control.console.txt" 2>&1
echo "control exit=$? (the measurement itself; some gates may legitimately fail)" | tee -a "$OUT/mutations.txt"

backup() { cp "$1" "$1.bak"; }
restore() { mv "$1.bak" "$1"; }

# ---------------------------------------------------------------- M1  G-M2-1 trio WER
TARGET="$ROOT/trio-A/results.json"
backup "$TARGET"
snippet m1 <<'PY'
import json, sys
path = sys.argv[1] + "/trio-A/results.json"
data = json.load(open(path))
for case in data["cases"]:
    if case["case_id"] == "lex_bill_ackman":
        case["arms"]["live"]["scores"]["tbsa"]["wer"] = 0.40
json.dump(data, open(path, "w"), indent=2)
PY
patch "$OUT/m1.py"
run m1_trio_wer_inflated
restore "$TARGET"

# ---------------------------------------------------------------- M2  G-M2-2 per case
backup "$ROOT/trio-A/results.json"
backup "$ROOT/trio-B/results.json"
snippet m2 <<'PY'
import json, sys
# Both passes: the gate scores the MEAN of the two, so a single mutated pass is still an
# improvement on average and would prove nothing.
for run in ("A", "B"):
    path = f"{sys.argv[1]}/trio-{run}/results.json"
    data = json.load(open(path))
    for case in data["cases"]:
        if case["case_id"] == "lex_javier_milei":
            # exactly the baseline: an unchanged case must not read as an improvement
            case["arms"]["live"]["scores"]["tbsa"]["wer"] = 0.144
    json.dump(data, open(path, "w"), indent=2)
PY
patch "$OUT/m2.py"
run m2_case_equal_to_baseline
restore "$ROOT/trio-A/results.json"
restore "$ROOT/trio-B/results.json"

# ---------------------------------------------------------------- M3  G-M2-3 recall
TARGET="$ROOT/trio-A/lex_keyu_jin/live-hypothesis.jsonl"
backup "$TARGET"
snippet m3 <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1]) / "trio-A/lex_keyu_jin/live-hypothesis.jsonl"
rows = [line for line in path.read_text().splitlines() if line.strip()]
path.write_text("\n".join(rows[: len(rows) // 2]) + "\n")
PY
patch "$OUT/m3.py"
run m3_half_the_words_never_published
restore "$TARGET"

# ---------------------------------------------------------------- M4  G-M2-4 correction clock
#  SENSITIVITY probe: shift every rolling completion 5 s earlier on the runtime clock.
for case in lex_bill_ackman lex_javier_milei lex_keyu_jin; do
  for run in A B; do backup "$ROOT/trio-$run/$case/live/run-001/trace.jsonl"; done
done
snippet m4 <<'PY'
import json, sys
from pathlib import Path
# Every session the pooled distribution is drawn from: p95 over 160 latencies barely moves if
# only one session's 24 are shifted, so a one-file probe would report nothing either way.
for run in ("A", "B"):
    for case in ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin"):
        path = Path(sys.argv[1]) / f"trio-{run}/{case}/live/run-001/trace.jsonl"
        out = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            event = entry.get("event") or {}
            if entry.get("kind") == "service_event" and event.get("kind") == "rolling_decode_completed":
                event["payload"]["runtime_monotonic_ns"] -= 5_000_000_000
            out.append(json.dumps(entry, ensure_ascii=False))
        path.write_text("\n".join(out) + "\n")
PY
patch "$OUT/m4.py"
run m4_correction_clock_shifted_5s_earlier
for case in lex_bill_ackman lex_javier_milei lex_keyu_jin; do
  for run in A B; do restore "$ROOT/trio-$run/$case/live/run-001/trace.jsonl"; done
done

# ---------------------------------------------------------------- M5  G-M2-5 queue depth
TARGET="$ROOT/trio-B/lex_bill_ackman/live/run-001/trace.jsonl"
backup "$TARGET"
snippet m5 <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]) / "trio-B/lex_bill_ackman/live/run-001/trace.jsonl"
out, duplicated = [], False
for line in path.read_text().splitlines():
    if not line.strip():
        continue
    entry = json.loads(line)
    event = entry.get("event") or {}
    out.append(json.dumps(entry, ensure_ascii=False))
    if (
        not duplicated
        and entry.get("kind") == "service_event"
        and event.get("kind") == "rolling_decode_queued"
        and event["payload"].get("admitted")
    ):
        # a second admitted window in flight for the same session: depth 2
        out.append(json.dumps(entry, ensure_ascii=False))
        duplicated = True
path.write_text("\n".join(out) + "\n")
PY
patch "$OUT/m5.py"
run m5_two_windows_in_flight
restore "$TARGET"

# ---------------------------------------------------------------- M6  G-M2-6 five-minute WER
TARGET="$ROOT/keyu5m-A/results.json"
backup "$TARGET"
snippet m6 <<'PY'
import json, sys
path = sys.argv[1] + "/keyu5m-A/results.json"
data = json.load(open(path))
data["results"]["live"]["scores"]["tbsa"]["wer"] = 0.20
json.dump(data, open(path, "w"), indent=2)
PY
patch "$OUT/m6.py"
run m6_five_minute_wer_inflated
restore "$TARGET"

# ---------------------------------------------------------------- M7  G-M2-7 accounting
TARGET="$ROOT/keyu5m-B/live/run-001/summary.json"
backup "$TARGET"
snippet m7 <<'PY'
import json, sys
path = sys.argv[1] + "/keyu5m-B/live/run-001/summary.json"
data = json.load(open(path))
data["accounted_samples"] = int(data["accounted_samples"]) - 16000
json.dump(data, open(path, "w"), indent=2)
PY
patch "$OUT/m7.py"
run m7_one_second_unaccounted
restore "$TARGET"

# ---------------------------------------------------------------- M8  G-M2-8 file mode
TARGET="$ROOT/trio-B/lex_keyu_jin/file-hypothesis.jsonl"
backup "$TARGET"
snippet m8 <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1]) / "trio-B/lex_keyu_jin/file-hypothesis.jsonl"
text = path.read_text()
path.write_text(text.replace("\n", "\n", 1) + '{"start": 59.0, "end": 59.5, "speaker": "S01", "text": "extra"}\n')
PY
patch "$OUT/m8.py"
run m8_file_arm_gained_a_row
restore "$TARGET"

echo "== done ==" | tee -a "$OUT/mutations.txt"
PYTHONDONTWRITEBYTECODE=1 "$PY" "$VERIFY" --fresh-root "$ROOT" --output "$OUT/control-after.json" \
  >"$OUT/control-after.console.txt" 2>&1
PYTHONDONTWRITEBYTECODE=1 "$PY" - "$OUT/control.json" "$OUT/control-after.json" <<'PY' | tee -a "$OUT/mutations.txt"
import json, sys
before = json.load(open(sys.argv[1]))["gates"]
after = json.load(open(sys.argv[2]))["gates"]
same = all(
    before[name]["pass"] == after[name]["pass"] for name in before if not name.startswith("_")
)
print("control restored identically:", same)
PY
