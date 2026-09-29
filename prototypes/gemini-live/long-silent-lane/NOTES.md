# Long silent-lane probe

Question: can a silent microphone lane hold the public rolling frontier after 750 s while the system lane keeps decoding? Minimum primitives: accepted audio, each lane's rolling frontier, their minimum, and per-lane worker progress. Invariant: silence advances its lane's coverage without provider calls; public rows do not stop when system decoding continues. Unknown: whether WP4's stall depends on its branch or provider timing. Falsifier: the 2600 s fake replay reproduces a public frontier at 750 s despite both workers completing.

Tool decision: one accelerated replay through actual lane and hybrid engines, with a 1 ms fake diarizer and silent mic, isolates scheduling/frontier behavior at $0. The result decides whether a core lane fix is supported here or whether to route WP4 branch-specific evidence to lead.

Run: `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/long-silent-lane/probe.py`

Verdict: the initial raw script run resolved the shared venv's installed package, so discard its counts. With `PYTHONPATH=.` and product mic L30/S15, baseline had 174 system calls, 174 public publications, and labels through 2610 s. A call #47 blocked while capture advanced 75 s caused four degraded bases; labels still resumed through 2610 s. A raised call after that block caused five degraded bases; labels again resumed through 2610 s. The same two variants through `runtime_probe.py` and real `GeminiLiveRuntime` remained active and labelled to 2610 s on WP1 and via read-only `PYTHONPATH=<WP4 worktree>` on WP4 branch c4ed5c43. The reported 750 s stall remains unreplicated by these fake-provider mechanisms; no core frontier change is justified by this probe.

Runtime replay command: `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/long-silent-lane/runtime_probe.py`
