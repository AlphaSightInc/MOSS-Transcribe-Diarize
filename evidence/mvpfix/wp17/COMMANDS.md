# WP17 reproduction commands

All Python commands: cwd = WP17 worktree;
`export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`;
`WP17_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`.

1. Verify import: `$WP17_PY -c 'import moss_transcribe_diarize as m; print(m.__file__)'`.
2. Own tunnel: `ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -L 127.0.0.1:18117:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us`.
3. Before load: `curl -s http://127.0.0.1:18117/metrics | rg '^vllm:num_requests_(running|waiting)'`.
4. Own stack: `$WP17_PY prototypes/streaming-diarization/wp17/stack.py --state /private/tmp/wp17/state --cert runs/wp17/cert.pem --key runs/wp17/key.pem --port 17877 --vllm-base-url http://127.0.0.1:18117/v1 --max-requests REMAINING`.
   Initial cap 500; 87 calls before restart. Second cap 413; 42 further calls.
   Standalone calls 4. Third cap 467 (=600-129-4). Each stack enforces semaphore 2.
   Never reuse a cap without subtracting already-consumed calls.
5. Baseline: `$WP17_PY prototypes/streaming-diarization/wp17/quality_probe.py before`;
   `$WP17_PY prototypes/streaming-diarization/wp17/recognition_real.py before`.
6. Lane-alone: `$WP17_PY prototypes/streaming-diarization/wp17/alone.py` (4 sequential calls).
7. After repair: `$WP17_PY prototypes/streaming-diarization/wp17/recognition_real.py after`;
   `$WP17_PY prototypes/streaming-diarization/wp17/quality_probe.py after`.
8. 24/48 second paired/alone: `$WP17_PY prototypes/streaming-diarization/wp17/duration_probe.py`.
9. Offline: `$WP17_PY prototypes/streaming-diarization/wp17/rescore.py`;
   `$WP17_PY prototypes/streaming-diarization/wp17/summarize.py`.
10. Focused: `$WP17_PY -m pytest -q -p no:cacheprovider tests/test_live_lane_decode.py tests/test_live_provider_bundle.py tests/phase2/test_voiceprint_matching.py` (70 pass).
    Oracle: same command with `tests/phase2/test_demo_lane_measurement.py tests/phase2/test_lane_word_oracle.py` (20 pass).
11. Full: `TMPDIR="$PWD/runs/wp17/tmp" $WP17_PY -m pytest -q -ra -p no:cacheprovider -p evidence.mvpfix.wp17.local_scratch --basetemp=runs/wp17/pytest-full tests`.
12. Frontend: `npm --prefix frontend test -- --run`; `npm --prefix frontend run typecheck`; `npm --prefix frontend run build`.

Raw public-corpus transcripts/producer traces/audio are in ignored runs/wp17/.
Only operation diffs and quantitative metadata are committed. No private recordings
used. All services/tunnels must be stopped before fresh-context verification.
