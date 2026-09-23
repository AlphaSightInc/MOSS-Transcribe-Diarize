# PANE-3.4 — post-Stop stale completion

## Structural question and hypothesis

Does the H1 session-2 item 59 completion represent a product race, or a rolling decode response that became stale when Stop intentionally ended rolling? Hypothesis: Stop clears rolling's in-flight identity before the decode response is recorded, so the response is expected post-Stop evidence and only the pre-Stop RTF reduction is misclassifying it.

## Minimum primitives

- A session-scoped event sequence, so each completion can be compared with that session's stop_requested.
- The admitted rolling item and its terminal completion, so accounting remains complete.
- The Stop boundary, which defines which decode completions belong in the pre-Stop projection.
- Existing outcome, failure, counter, and timing fields, so other acceptance failures remain visible.

Each is required to preserve same-session ordering, close admitted work, and keep the metric scoped to pre-Stop work.

## Invariants

- Every admitted rolling item still has exactly one completion.
- Unadmitted, duplicate, failed, unhealthy, or pre-Stop stale completions still fail.
- Only a same-session post-Stop stale counter increase of exactly one with rolling_status=stopped and outcome=no_proposal is exempt.
- Other stale counter increases, including pre-Stop increments and post-Stop increments with another status or outcome, still fail.
- Decode seconds from a completion recorded after Stop do not enter the pre-Stop RTF.
- Product behavior and acceptance bounds remain unchanged.

## Assumptions and unknowns

H1 event seq is monotonic within each session; stale_completions is cumulative across rolling completion events. A content-free six-event fixture is extracted from the retained H1 #2 overload/load-2/session-2-events.json rows at seq 11, 535, 540, 587, 588, and 590, with the opaque session ID normalized. Whether the post-Stop decode started before Stop is immaterial to this projection: the brief defines completion order as the boundary. Host behavior beyond these retained rows is unmeasured.

## Falsifier

Stop if the H1 session/item/sequence ordering does not match the trace, or if product code does not clear the in-flight request during Stop. The fix is rejected if a stale completion before Stop passes, if post-Stop admission accounting becomes incomplete, or if an unrelated overload/concurrency control regresses.

## Tool decisions

- Extract only the H1 rows and fields needed to establish session identity, sequence, status, counter delta, and timing. A mismatch would stop the change.
- Inspect the production Stop and completion paths. Clearing the in-flight request followed by stale completion accounting distinguishes expected behavior from a product race.
- Replay the H1-derived fixture through prestop_inference_projection; RED on 7f54b12f plus pre-Stop, outcome, status, and +2 counter controls define the acceptance boundary at its production seam.
- Run the required overload/concurrency tests and pinned full suite once to catch regressions; no decoder or GPU is needed for this pure reducer change.

## RTF decision

Exclude decode seconds for a completion sequenced after that session's Stop: the reported quantity is explicitly pre-Stop RTF, and the brief classifies that completion as post-Stop.

## Focused reproduction command

~~~sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python -m pytest -q -p no:cacheprovider tests/phase2/test_acceptance_stop_pending.py -k 'h1b_post_stop_stale'
~~~
