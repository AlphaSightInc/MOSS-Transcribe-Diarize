# WP29 — tape exhaustion

Question: can a longer-than-tape meeting finish truthfully without losing committed words?
Primitives: committed transcript, bounded retained PCM, terminal refinement, durable audio,
and lifecycle ownership. Each has a distinct lifetime; none substitutes for another.
Invariants: unchanged bounds/policies/protocol; failed tape cannot fail capture; unavailable
refinement keeps words; partial audio states its actual duration; Stop owns completion.
Unknown: repeated-session native memory until the two-session measurement completes.
Falsifier: any lost committed lane segment, generic finalizer defect, false complete audio,
armed terminal lease, nonempty publication queue, or unreadable durable result.
Tool decision: real HTTP/SQLite/MP3 + stub ASR isolates lifecycle from provider variability;
real public speech and ONNX RSS probe distinguish Python tape release from native residency.

## Prototype verdict before production changes

Supported fix. Nine sessions across eight scenarios, 90 seconds each, 60-second tape.
Both exhausted (Stop, accepted Stop then departure, silent microphone, two concurrent):
5/5 refinement `failed`, missing keyword-only `gaps`; all saved `completed` with words intact.
One exhausted lane (2/2): `final`, failed-lane words intact, INCORRECT zero gap accounting.
Mixed tape only (1/1): both lanes refine, audio remains independently partial.
Departure before Stop (1/1): `interrupted`, no refinement; correct lifecycle preserved.
All 9: 60.000000-second partial MP3; saved/live words equal; lease disarmed; queue empty;
all three tapes released. No notice describes unavailable refinement in the saved meeting.
Silent PCM is NOT compressed: all lane tapes grow equally even with a silent microphone.
Thus single-tape cases use explicitly isolated capacity overrides, not a false silence premise.
No production cap changes proposed.

Unit falsifiers before fix: 4 failed, 1 passed. Both-exhausted and all-zero lack `gaps`;
each one-lane failure reports zero gaps. Evidence: unit-red.txt and prototype.json.
Automated state dumps replace interactive TUI; the probe is absorbed into this regression bench.

Failed setup attempts retained: prototype-stop.txt disabled the rolling planner and exercised
`no_terminal_plan`, not the defect. prototype.txt then waited for HTTP Stop before manually
running the terminal scheduler, correctly receiving `stop_in_progress`. Corrected probe keeps
the planner and runs the held terminal work while the Stop request waits. Neither is a product bug.

## Implemented result

`fixed.json`: 9/9 preserve the expected durable outcome, words, audio duration and cleanup.
Five both-lane exhaustion sessions now report `unavailable`, with two actual lane gaps;
two single-lane sessions report `final`, one actual lane gap and preserve that lane's words;
mixed-only finalizes both lanes; pre-Stop departure remains interrupted. All nine reopen
with the exact saved document and notice, all MP3s are partial and exactly 60 seconds.
Seven completed sessions with unavailable refinement carry only this fixed notice:
"Final transcript refinement was unavailable for some audio. Previously committed words were kept."
Existing history renders that notice and "Download partial audio"; no frontend production
change or generated asset change is needed. Refusal accounting reports lane gap count,
not a fabricated whole-meeting gap count; both lanes missing the same interval count twice.

First focused patched suite: 56 passed, 2 failed. Both failures were missing notices for
single-lane exhaustion: publication is queued on `text_revision_applied` before the terminal
accounting event is appended. The notice now reads the settled runtime event stream under
its lock. This is covered by the HTTP tests; not hidden by testing a synthetic payload only.

Memory probe setup: the first attempt used WP22's tracemalloc instrumentation. Stopped after
90 audio seconds because tracing is unnecessary for the requested cheap current-RSS check;
retained its partial logs as `repeat-rss-traced-incomplete.*`. The replacement keeps production
VAD, ONNX identity, lane/rolling/terminal paths, both original public clips, the same runtime
and encoder for both meetings, and Python owner counts; removes allocation tracing only.
No caches of model outputs; no GPU; all PCM and synthetic content stay in ignored `.wp29/`.
