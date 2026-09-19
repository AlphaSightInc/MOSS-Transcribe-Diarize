# Round2 measurement falsifier

Question: can a missing, merged or unknown participant look correctly recognized in qualification?
Minimum primitives: independently named source intervals, actual output intervals, unknown label and global matching. Unknown is no identity evidence. No new thresholds.
Run: `PYTHONPATH=. .venv/bin/python prototypes/streaming-diarization/round2-measurement/probe.py`. No decoder calls.
Result: exact DER0; missing half0.5; merged people0.5; all unknown1.0. Missing-participant witness fails all three negative controls. Full state printed. PASS.
Candidate helper exercised before wiring to file qualification. Absorbed helper into tools/qualify/speaker_quality.py, controls into regression tests. Existing library scorer reused. Per-participant presence is necessary, not sufficient for quality acceptance. Coarse reference timing caveat retained.
