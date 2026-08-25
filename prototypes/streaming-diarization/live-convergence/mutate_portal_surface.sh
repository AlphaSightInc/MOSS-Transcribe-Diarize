#!/usr/bin/env bash
# Mutation sweep for the SHIPPED portal surface render (plan §10.5 step 6).
#
# Each mutation breaks one property the reader's screen claims, in the production portal, and
# must be caught -- by the corpus verifier on real trio audio, by a named T2 test, or by both.
# Where only the test catches it, that is recorded as a finding rather than papered over: sixty
# seconds of unhurried speech does not put every surface a browser can be handed on the screen.
# The production file is restored from a backup on exit, including on failure, and a control run
# after the sweep proves it. Every run replays the grid's decode cache: ZERO MOSS requests.
#
#   prototypes/streaming-diarization/live-convergence/mutate_portal_surface.sh <out-dir>
set -u

OUT="${1:?output dir}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PORTAL="$REPO/moss_transcribe_diarize/app/live_portal.py"
VERIFY="$REPO/prototypes/streaming-diarization/live-convergence/verify_portal_surface.py"
TESTS="$REPO/tests/test_live_portal.py"
PORTAL_BACKUP="$(mktemp)"
cp "$PORTAL" "$PORTAL_BACKUP"
restore() { cp "$PORTAL_BACKUP" "$PORTAL"; }
trap 'restore; rm -f "$PORTAL_BACKUP"' EXIT
mkdir -p "$OUT"

patch() {  # patch <old> <new>
  MUT_PATH="$PORTAL" "$REPO/.venv/bin/python" - "$1" "$2" <<'PY'
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
echo "== control: unmutated portal ==" | tee -a "$OUT/summary.txt"
check control

# M1 -- the page renders the committed spans again, which is exactly what it did before this
# step: every span's own words under its own span-relative clock, and no rolling revision on
# the screen at all. Guard: the verifier (G1/G2 -- the arm leaves the screen) and T2.
echo "== M1: render the committed spans instead of the surface ==" | tee -a "$OUT/summary.txt"
patch '        for (const segment of session.effective_transcript || []) {' '        for (const item of session.committed || []) {
          const legacy = item.revised_transcript || item.transcript;
          if (legacy) {
            rows.push(legacy);
          }
        }
        for (const segment of []) {'
check m1-render-committed-spans

# M2 -- the surface is APPENDED to instead of replaced, the one defect this step exists to
# prevent: every poll re-prints the whole meeting under the meeting so far. Guard: the verifier
# (G3, at the very first poll) and T2.
echo "== M2: append the surface instead of replacing it ==" | tee -a "$OUT/summary.txt"
patch '        setText(nodes.transcript, rows.join("\\n\\n"));
      }

      function renderSnapshot(payload) {' '        setText(
          nodes.transcript,
          [nodes.transcript.textContent, rows.join("\\n\\n")].filter(Boolean).join("\\n\\n"),
        );
      }

      function renderSnapshot(payload) {'
check m2-append-instead-of-replace

# M3 -- the canonical identity is printed instead of the token the meeting is written in, so a
# reader's transcript stops agreeing with every export of it. Guard: the verifier (G3 and G5).
echo "== M3: print the canonical identity, not the Sxx token ==" | tee -a "$OUT/summary.txt"
patch '        const index = (canonicalSpeakers || []).indexOf(canonicalSpeaker);
        if (index < 0) {
          return unattributedSpeaker;
        }
        return `S${String(index + 1).padStart(2, "0")}`;' '        return canonicalSpeaker;'
check m3-print-canonical-identity

# M4 -- speech nobody was attributed is shown as the first speaker instead of the honest
# unattributed token: the page inventing an answer the server refused to give. Guard: the
# verifier (G3) and T2.
echo "== M4: unattributed speech is rendered as a speaker ==" | tee -a "$OUT/summary.txt"
patch '        if (canonicalSpeaker === undefined || canonicalSpeaker === null) {
          return unattributedSpeaker;
        }' '        if (canonicalSpeaker === undefined || canonicalSpeaker === null) {
          return "S01";
        }'
check m4-unattributed-rendered-as-speaker

# M5 -- the span still being spoken is dropped, so the live tail disappears and the reader
# watches a transcript that stops one span short of the meeting. Guard: T2 ONLY -- this
# instrument's base path commits every span it freezes and never publishes a provisional
# suffix, so sixty seconds of real audio cannot see it.
echo "== M5: the provisional tail is dropped ==" | tee -a "$OUT/summary.txt"
patch '        if (session.provisional && session.provisional.transcript) {
          rows.push(session.provisional.transcript);
        }' '        if (false) {
          rows.push(session.provisional.transcript);
        }'
check m5-provisional-tail-dropped

# M6 -- the seconds are computed from a rate the page assumed instead of the one the service
# declared, which is the failure mode the descriptor check exists for: every timestamp on the
# screen is plausible and wrong. Guard: the verifier (G3).
echo "== M6: assume a sample rate instead of reading it ==" | tee -a "$OUT/summary.txt"
patch '        renderTranscript(snapshot, sampleRate);' '        renderTranscript(snapshot, 8000);'
check m6-assume-a-sample-rate

echo "== restored; control run ==" | tee -a "$OUT/summary.txt"
check control-restored
