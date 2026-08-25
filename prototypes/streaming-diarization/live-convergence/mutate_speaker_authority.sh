#!/usr/bin/env bash
# Show that compare_speaker_authority.py reacts before believing that "S1 == S0".
#
#   mutate_speaker_authority.sh <out-dir>
#
# A measurement whose headline is "nothing changed" is exactly the measurement that a
# wired-off arm would also produce. Four mutations, each on a COPY of the passes, the decode
# cache or the driver, each flipping the one verdict it targets:
#
#   I1  swap the witness's local speaker labels (S01<->S02) in the cached decodes
#       -> the verdict must NOT move. This is the label-invariance plan 11.1 requires: the
#          decoder's local names are arbitrary per window and the mapping is decided by the
#          embedding, so renaming them is expected to change nothing at all.
#   M1  collapse every witness segment onto ONE local speaker
#       -> S1 must change. A witness that cannot separate voices cannot name them, and if the
#          arm's output survives that, the arm is not reading the witness.
#   M2  publish every committed span as S00 in the pass's trace
#       -> the album enrols nobody, every window abstains `album_has_no_reference`, 0 relabels.
#   M3  corrupt one row of the exported live-hypothesis.jsonl
#       -> the S0 control fails and the driver exits non-zero instead of scoring anything.
#   M4  prepend one second of context audio to every witness-owned interval (driver mutation)
#       -> G-M3-0's D5 check must report violations.
#
# The control is re-run first and last; both must agree.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="$REPO/.venv/bin/python"
DRIVER="$REPO/prototypes/streaming-diarization/live-convergence/compare_speaker_authority.py"
OUT="${1:?usage: mutate_speaker_authority.sh <out-dir>}"
CASE=lex_bill_ackman
mkdir -p "$OUT"

WORK="$(mktemp -d /tmp/moss-m3-mutations-XXXXXX)"
# The S0 arm IS the M2 exit bundle; M3 does not re-check-in a second copy of it.
cp -R "$REPO/evidence/live-convergence-0824/M2-e2-exit/passes" "$WORK/passes"
cp "$REPO/evidence/live-convergence-0824/M3-s1-prototype/witness-decodes.json" "$WORK/decodes.json"
EMBED="$WORK/embed-cache.json"
[ -f /tmp/moss-speaker-authority-embed-cache-v1.json ] \
  && cp /tmp/moss-speaker-authority-embed-cache-v1.json "$EMBED"

run() {  # run <label> <driver> <decodes> <passes>
  local label="$1" driver="$2" decodes="$3" passes="$4"
  PYTHONDONTWRITEBYTECODE=1 "$PY" "$driver" \
    --passes-root "$passes" --cases "$CASE" --runs A \
    --decode-cache "$decodes" --embed-cache "$EMBED" \
    --output "$WORK/$label.json" >"$OUT/$label.log" 2>&1
  echo "$?"
}

verdict() {  # verdict <label>
  "$PY" - "$WORK/$1.json" <<'PY'
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception as exc:
    print(f"no report ({exc.__class__.__name__})")
    raise SystemExit(0)
case = next(iter(report["cases"]))
run = report["cases"][case]["runs"]["A"]
print(
    f"s0_der={run['arms']['s0']['der']:.6f} s1_der={run['arms']['s1']['der']:.6f} "
    f"relabelled={run['application']['segments_relabelled']} "
    f"abstentions={sum(1 for w in run['windows'] if w['abstention'])} "
    f"d5_violations={len(run['d5_violations'])} "
    f"control={run['bench_control']['export_reproduces_pass']}"
)
PY
}

{
  echo "== control (before) =="
  echo "exit=$(run control-before "$DRIVER" "$WORK/decodes.json" "$WORK/passes")  $(verdict control-before)"

  echo
  echo "== I1  witness local labels swapped in the decode cache (expect NO change) =="
  "$PY" - "$WORK/decodes.json" "$WORK/i1-decodes.json" <<'MUT'
import json, sys
payload = json.load(open(sys.argv[1]))
for entry in payload["entries"].values():
    entry["transcript"] = (
        entry["transcript"].replace("[S01]", "[SXX]").replace("[S02]", "[S01]").replace("[SXX]", "[S02]")
    )
json.dump(payload, open(sys.argv[2], "w"), indent=2, sort_keys=True)
MUT
  echo "exit=$(run i1 "$DRIVER" "$WORK/i1-decodes.json" "$WORK/passes")  $(verdict i1)"

  echo
  echo "== M1  every witness segment collapsed onto one local speaker =="
  "$PY" - "$WORK/decodes.json" "$WORK/m1-decodes.json" <<'MUT'
import json, sys
payload = json.load(open(sys.argv[1]))
for entry in payload["entries"].values():
    entry["transcript"] = entry["transcript"].replace("[S02]", "[S01]").replace("[S03]", "[S01]")
json.dump(payload, open(sys.argv[2], "w"), indent=2, sort_keys=True)
MUT
  echo "exit=$(run m1 "$DRIVER" "$WORK/m1-decodes.json" "$WORK/passes")  $(verdict m1)"
  echo
  echo "== M2  every committed span published as S00 (album enrols nobody) =="
  cp -R "$WORK/passes" "$WORK/m2-passes"
  "$PY" - "$WORK/m2-passes/trio-A/$CASE/live/run-001/trace.jsonl.gz" <<'PY'
import gzip, json, sys
path = sys.argv[1]
lines = []
for line in gzip.open(path, "rt", encoding="utf-8"):
    record = json.loads(line)
    session = (record.get("snapshot") or {}).get("session")
    if session and record.get("kind") != "session_created":
        for span in session.get("committed", []):
            for field in ("transcript", "revised_transcript"):
                if isinstance(span.get(field), str):
                    span[field] = span[field].replace("[S01]", "[S00]").replace("[S02]", "[S00]")
    lines.append(json.dumps(record))
with gzip.open(path, "wt", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
PY
  echo "exit=$(run m2 "$DRIVER" "$WORK/decodes.json" "$WORK/m2-passes")  $(verdict m2)"

  echo
  echo "== M3  one exported hypothesis row corrupted (S0 control) =="
  cp -R "$WORK/passes" "$WORK/m3-passes"
  "$PY" - "$WORK/m3-passes/trio-A/$CASE/live-hypothesis.jsonl" <<'PY'
import json, sys
path = sys.argv[1]
rows = [json.loads(line) for line in open(path) if line.strip()]
rows[0]["speaker"] = "S02"
open(path, "w").write("\n".join(json.dumps(row) for row in rows) + "\n")
PY
  echo "exit=$(run m3 "$DRIVER" "$WORK/decodes.json" "$WORK/m3-passes")  $(verdict m3)"

  echo
  echo "== M4  one second of context prepended to every witness-owned interval =="
  # The mutant lives beside the driver: it imports this directory's sibling modules.
  M4_DRIVER="$(dirname "$DRIVER")/_mutant_m4_driver.py"
  trap 'rm -f "$M4_DRIVER"' EXIT
  sed 's|    owned = _speaker_intervals_by_label(frozen, segments, rules\["min_segment_samples"\])|    owned = {k: [(max(0.0, lo - 1.0), hi) for lo, hi in v] for k, v in _speaker_intervals_by_label(frozen, segments, rules["min_segment_samples"]).items()}|' \
    "$DRIVER" >"$M4_DRIVER"
  cmp -s "$DRIVER" "$M4_DRIVER" && echo "MUTATION M4 DID NOT APPLY"
  echo "exit=$(run m4 "$M4_DRIVER" "$WORK/decodes.json" "$WORK/passes")  $(verdict m4)"
  rm -f "$M4_DRIVER"

  echo
  echo "== control (after) =="
  echo "exit=$(run control-after "$DRIVER" "$WORK/decodes.json" "$WORK/passes")  $(verdict control-after)"
} | tee "$OUT/mutations.txt"

echo "work tree: $WORK"
