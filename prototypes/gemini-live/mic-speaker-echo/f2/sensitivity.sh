#!/usr/bin/env bash
# Every ablation and one-step sensitivity around the final parameter set, $0 (about 25 minutes).
#   f2/sensitivity.sh <python>      then: <python> f2/summary.py
PY="$1"; F="$(cd "$(dirname "$0")" && pwd)"
run() { PYTHONDONTWRITEBYTECODE=1 "$PY" "$F/variant.py" "$1" "$2" > /dev/null || echo "FAILED $1"; echo "done $1"; }
run final '{}'
# ablations: one element removed
run noA '{"rescue_level": false}'
run noB '{"rescue_anchor": false}'
run noC '{"local_text_phrase_only": false}'
run noStretch '{"min_frames": 1}'
run noWeight '{"min_weight": 0}'
run noCoverage '{"coverage": 0}'
run fixed15dB '{"reference": "fixed_-15dB"}'
# one step either side of each parameter
run vad1 '{"vad_mode": 1}'
run vad2 '{"vad_mode": 2}'
run T20 '{"min_frames": 20}'
run T30 '{"min_frames": 30}'
run T50 '{"min_frames": 50}'
run W10 '{"min_weight": 10}'
run W20 '{"min_weight": 20}'
run cov50 '{"coverage": 0.5}'
run cov100 '{"coverage": 1.0}'
run margin3 '{"margin_db": 3}'
run margin12 '{"margin_db": 12}'
run q30 '{"quantile": 0.3}'
run q70 '{"quantile": 0.7}'
run gap0 '{"gap_frames": 0}'
run gap10 '{"gap_frames": 10}'
# stress: the text guard cannot match any Chinese token (the provider answered the two lanes in different scripts)
run stressToday '{"stress_text_guard_blind_to_cjk": true, "rescue_level": false, "rescue_anchor": false, "local_text_phrase_only": false}'
run stressFinal '{"stress_text_guard_blind_to_cjk": true}'
run stressNoCoverage '{"stress_text_guard_blind_to_cjk": true, "coverage": 0}'
