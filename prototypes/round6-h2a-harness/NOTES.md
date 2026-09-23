# H2-A harness diagnosis

Structural question: can the two required 2-session predicates run in one fixed campaign without colliding in append-only artifact storage, and are the terminal and browser failures consequences of that collision?

Minimum primitives: the production `FixedAccountCampaign` artifact writer and load producer; the committed host raw observations; focused tests at their call sites. No decoder or host access.

Invariants: preserve 2 sessions, duration and backpressure workload, `O_EXCL` artifact custody, acceptance bounds/populations, and terminal cleanup order. One campaign owns its paths. All counts retain their denominator.

Assumptions/unknowns: the second live load uses the same `load-2` and `capacity-2` names. The host's overload raw failure is `ValueError` in pre-Stop projection, so the artifact collision may be concurrent rather than the cause of the predicate FAIL. `zero_work_end` reports `Phase2ControlError` at `_control`, whose underlying socket cause is not present in sanitized raw observations. Browser workspace deterministic probe uses 1 second of silence with a stub that supplies text; host return says no completed speech, while the acceptance browser predicate passed in both layers.

Falsifiers: if a production-seam RED cannot reproduce both path collisions, do not change the writer; if unique namespace still yields a failing workload, report that separately. If control-status failure occurs without a load worker failure, terminal failure is independent. If browser fixture with silence and the stub consistently produces completed speech locally, host-specific cause remains unproved.

Tools and why: host raw receipts identify exact failed fields; source inspection maps call order; prescribed Python/pytest gives RED/GREEN on the frozen clone; a small `run.py` uses the production artifact writer and prints path state in one command. No browser/decoder service is needed for namespace testing.

Hypotheses, ranked: (1) common `load-2` and `capacity-2` names collide after `f92baf35`; unique overload namespace prevents both. (2) zero-work failure is a control-socket failure independent of the collision; a healthy control socket would return a status after cleanup. (3) host deterministic browser prototype has a silent fixture and speechless inference path; the accepted production browser input can still pass. (4) browser failure instead comes from a file-meeting terminal state error; retained response details would distinguish it.

Outcome: (1) confirmed by RED with both predicates in one `FixedAccountCampaign`; GREEN with an `overload/` artifact directory. (3) confirmed locally: the 1-second silent fixture finished with zero segments and did not call the stub; committed 2.1-second nonzero speech fixture made the subprocess control GREEN. (4) falsified locally: the meeting was `completed`, with no failure state. (2) remains unresolved: the host retained only a sanitized `Phase2ControlError` from status; there is no socket errno or server code. The overload predicate's host `ValueError` in pre-Stop inference projection also remains after the namespace fix; that failure arose before the artifact write in the same method and needs a decoder-backed host rerun.
