# Long silent-lane probe

Question: can a silent microphone lane hold the public rolling frontier after 750 s while the system lane keeps decoding? Minimum primitives: accepted audio, each lane's rolling frontier, their minimum, and per-lane worker progress. Invariant: silence advances its lane's coverage without provider calls; public rows do not stop when system decoding continues. Unknown: whether WP4's stall depends on its branch or provider timing. Falsifier: the 2600 s fake replay reproduces a public frontier at 750 s despite both workers completing.

Tool decision: one accelerated replay through actual lane and hybrid engines, with a 1 ms fake diarizer and silent mic, isolates scheduling/frontier behavior at $0. The result decides whether a core lane fix is supported here or whether to route WP4 branch-specific evidence to lead.

Run: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/long-silent-lane/probe.py`

Verdict on WP1 branch: accepted 2610 s; 174 system diarizer calls and zero mic calls; both lane frontiers, public frontier, and last labelled row reached 2610 s; 261 public rolling publications. The 750 s stall did not reproduce. A WP4-specific branch or live provider error remains possible; no core frontier algorithm change is justified by this probe.
