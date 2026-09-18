# WP12 LOGIC measurement prototype

Question: where does per-lane Stop time go, how does it scale, and why does the
microphone gain a second identity in WP1's half-system/half-mic 48 s fixture?
Primitives: source tape; decoder window; lane-owned voice reference; publication.
Invariants: complete terminal contract, lane isolation, unchanged identity policy,
unchanged frame/lifecycle/readiness/quality contracts, at most two decoder calls.
Unknown: decoder versus queue versus embedding cost; actual acoustic continuity.
Falsifiers: lost committed words, missing/foreign voice reference, changed final
contract; measured acoustic rejection falsifies a bookkeeping-only repair.

One command from worktree root:
`WP12_ARM=lane bash prototypes/streaming-diarization/wp12-stop-identity/experiment.sh 24 parity`
Use `mono` for the `37979e53` archive inside `.wp12`, and `48 alternation` for the
WP1 identity reproduction. 180 s inputs repeat each public 60 s clip three times.
All frames are paced, heartbeat precedes every pair, Stop deadline is 30 s. State
prints each frame; text/audio/credentials stay out of retained evidence. Real API,
real decoder and pinned production encoder; SQLite version-pin bypass is inherited
from the local bench. Global request ledger refuses beyond 300 unless authorized.
Each batch owns/tears down port 18112 tunnel and port 17872 server.

H1 serial whole-meeting decodes dominate; H2 pending canonical/rolling work dominates;
H3 lost lane album evidence causes births; H4 real embeddings reject the old voice.
Timestamps and per-span score/assignment/album traces distinguish these hypotheses.

After absorption, `lane`, `parallel` and `fixed` all use current production code.
`serial` loads the untouched b31683a6 archive in `.wp12/base-b316`; `mono` loads
37979e53 from `.wp12`. Recorded historical `lane` results predate the absorption.
No more live runs are authorized beyond the retained 300-call ledger. Offline:
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/streaming-diarization/wp12-stop-identity/audit.py`
Full local suites: `bash prototypes/streaming-diarization/wp12-stop-identity/check-python.sh`
and `bash prototypes/streaming-diarization/wp12-stop-identity/check-frontend.sh`.
The concurrency prototype was absorbed/deleted; these scripts are the standing
bench's measurement and fault-control tools, not alternate product implementations.
