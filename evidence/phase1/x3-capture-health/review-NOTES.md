# Adversarial review of x3-capture-health — 2026-08-14

Independent review of the branch as the ralph loop left it (`1262da5`), on the head produced by
`git merge --no-edit dev` (dev `f6353eb`). Two probes, both committed and both re-run here.

## review-01 — the five PRD scenarios through the real route

`review-01-five-scenario-route-probe.py`. Deliberately self-contained: it imports nothing from
`tests/`, so the *same file* runs unchanged against `dev` and against this branch. Every row is
the body of a real authenticated `GET /api/live/sessions/{id}/snapshot` over the ASGI stack. No
scenario calls `project_live_capture_status` directly — the previous round shipped this ticket's
fusion as dead code at the route with a passing unit test, so a unit test is not accepted as
proof of wiring.

```bash
# this branch (asserts; exits non-zero on any failure)
PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/review-01-five-scenario-route-probe.py \
  --label branch-head-after-review-fix \
  --write evidence/phase1/x3-capture-health/review-01-five-scenario-route.json

# pre-branch reproduction: same file, run inside a `git archive dev` export
PYTHONPATH=. .venv/bin/python review-01-five-scenario-route-probe.py \
  --observe-only --label dev-pre-branch-reproduction
```

`review-01-dev-pre-branch-reproduction.json` is that dev run. All five scenarios answered
`recording` / "Capturing microphone and shared audio." — the PRD's claim reproduced exactly — and
the microphone-denied session answered `403` with no server string at all.
`review-01-five-scenario-route.json` is the same probe on this branch: every scenario now reports
something correct, and the healthy control still reports healthy.

Scenario 0 is a healthy control, and it is the point. An implementation that simply never emitted
the healthy line would satisfy scenarios 1–5 and prove nothing; the control is what makes those
five assertions capable of failing.

Scenario 7 is not from the PRD. It is the polling client's *next tick* —
`/snapshot?since_version=<version>`, which is exactly what `live_portal.py` sends — and it failed
on the branch as received. See the defect note below.

## review-02 — the same scenarios over a real uvicorn socket

`review-02-live-uvicorn-wire-probe.py` removes the last doubt that review-01's result is an
in-process TestClient artifact. It starts *its own* uvicorn with TLS on a private, non-loopback
address of this host and drives the routes with `httpx` over a real socket. TLS and the
non-loopback peer are forced by `LiveAccessRegistry`, which refuses a pairing exchange from a
loopback peer and refuses any non-loopback peer without TLS.

It starts nothing on, and sends nothing to, any deployed MOSS host.

```bash
PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/review-02-live-uvicorn-wire-probe.py \
  --write evidence/phase1/x3-capture-health/review-02-live-uvicorn-wire.json
```

Recorded run: `192.168.68.29:60522`, all checks passed. Scenario 5 reaches the server's own
`v2_session.lanes.system.health == "failed"` over the wire and the projection uses it.

## Defect found and fixed during review

The terminal reason was a one-shot. `_snapshot_response` derived the terminal capture facts from
the `since_version`-gated snapshot, so the *second* poll — carrying the version the first poll had
just handed it — got `unchanged: true`, no snapshot, no helper presence (teardown released it),
and answered `capture_phase: "starting"` / "Waiting for audio capture to start." for a session
that had already died. The portal polls with that cursor on every tick
(`live_portal.py`: `/snapshot?since_version=${snapshotVersion}`), so in the shipped client the
readable reason would have survived exactly one tick before being replaced by a confident wrong
answer. Fixed by reading the session as it is, then applying the caller's cursor only to the
transported snapshot. Regression:
`tests/test_live_api.py::LiveApiTest::test_terminal_capture_reason_survives_the_polling_clients_since_version_tick`,
which fails with `'starting' != 'failed'` if the fix is reverted.

## Probe re-runs

| probe | result |
| --- | --- |
| `iteration-04-observation-contract-probe.py` | reproduces its JSON; only `server_monotonic_elapsed_ns` differs (29.7 ms → 30.9 ms) |
| `iteration-06-live-route-threshold-probe.py` | reproduces its JSON; only arrival timings differ (p95 517.6 ms → 521.1 ms, stall 2067.1 ms → 2059.6 ms) |
| `iteration-09-terminal-reason-probe.py` | **crashed** on `assert capture_snapshot.status_code == 403` — rewritten, see below |
| `iteration-10-terminal-readable-probe.py` | reproduces its JSON; only `last_seen_monotonic_ns` differs |

`iteration-09` was the ticket's own before-state reproduction and it asserted the `403` the
pre-fix tree returned. Once iteration 10 landed the fix, the probe could no longer regenerate the
artifact it is cited for — an artifact whose probe cannot be re-run is the failure mode this
repo's guardrail exists to stop, and preflight cannot see it because the file is still present.
It now performs the pre-branch `release_session` call itself and records both outcomes, so the
defect and the fix are reproduced on every run and the causal claim is stronger than the original
snapshot of one status code.

## Mutation check on the branch's own gate

Eleven targeted mutations of `live_capture_status.py` / `live_transport.py` — including three
that re-create the original "dead code at the route" defect by dropping `v2_session`,
`observations` and `terminal_lane_failures` at the call site — were each caught by both
`pytest -q tests/test_live_capture_status.py tests/test_live_api.py` and review-01. No mutation
survived. The branch's assertions have teeth.

One decorative assertion was found and repaired: `_assert_unhealthy_snapshot` in
`iteration-06-live-route-threshold-probe.py` asserted `not healthy_recording_claim` *after* two
exact-equality assertions had already decided it, so it could not fail as called. It now guards
the thing that can actually fail — the expectation itself being defanged into the healthy pair.
