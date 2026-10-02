"""Push reachable protocol hard cases through real routes; print full state.

This is measurement code, not a product regression suite.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from run import build_app, Clock, FakeTimer, EV, SETTINGS, hb, frame, session
from protocol import ResumeProtocol


def main():
    directory = EV / ("boundaries-" + time.strftime("%Y%m%d-%H%M%S"))
    app, cookies, engines = build_app(directory)
    clock, timer = Clock(), FakeTimer()
    candidate = ResumeProtocol(app, "S2", clock)
    results = []
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, cookies["a"])
        st = app.state
        st.live_helper_presence._monotonic_ns = clock
        st.live_helper_failures._monotonic_ns = clock
        st.live_helper_failures._timer = timer
        sid = client.post("/api/live/sessions", json={"engine_settings": SETTINGS}).json()["id"]
        base = f"/api/live/sessions/{sid}"
        old = {"X-Moss-Capture-Instance": "old"}
        client.post(base + "/heartbeat", json=hb("old"), headers=old)
        clock.now += 500000000
        for lane in ("system", "microphone"):
            client.post(base + "/frames", json=frame(lane, 0, 0), headers=old)
        async def other_signin():
            await st.phase2_store._connection.execute(
                "INSERT INTO sign_in_sessions VALUES (?, ?, ?)", ("prototype-other-signin", "sub-a", 1))
            await st.phase2_store._connection.commit()
        client.portal.call(other_signin)
        def request(new, expected="old"):
            return client.post(base + "/resume", headers={"X-Moss-Capture-Instance": new},
                json={"expected_instance_id": expected, "heartbeat": hb(new)})
        def record(action, response):
            results.append({"action": action, "status": response.status_code, "body": response.json(),
                "presence": st.live_helper_presence.snapshot(sid).to_dict(), "writer": candidate.writers[sid],
                "lease_deadline_ns": st.live_helper_failures._sessions[sid].deadline_monotonic_ns})
            return response
        session(client, "prototype-other-signin")
        record("same account different sign-in session", request("other-device"))
        session(client, cookies["b"])
        record("foreign account frame remains private", client.post(base + "/frames", json=frame("system", 1, .5), headers=old))
        session(client, cookies["a"])
        invalid = hb("invalid"); invalid["state"] = "invalid"
        record("invalid resume leaves old authority intact", client.post(base + "/resume",
            json={"expected_instance_id": "old", "heartbeat": invalid}))
        # Same origin sign-in in two tabs; atomically compare the old page id.
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(request, ("new-a", "new-b")))
        for i, response in enumerate(responses): record(f"concurrent takeover {i}", response)
        winner = candidate.writers[sid]
        record("lost response retry", request(winner))
        record("old queued acknowledged replay is fenced", client.post(base + "/frames", json=frame("system", 0, 0), headers=old))
        new = {"X-Moss-Capture-Instance": winner}
        state = candidate.state(sid)
        for lane in ("system", "microphone"):
            record("new page sequence zero cannot recover audio", client.post(base + "/frames", headers=new,
                json=frame(lane, 0, .5, 1, True)))
            record("new epoch without discontinuity", client.post(base + "/frames", headers=new,
                json=frame(lane, 1, .5, 1)))
            record("adopted sequence and discontinuity", client.post(base + "/frames", headers=new,
                json=frame(lane, 1, .5, 1, True)))
        # Expiry correctness must not depend on timely delivery of its callback.
        clock.now = st.live_helper_failures._sessions[sid].deadline_monotonic_ns
        record("at exact deadline before timer callback", request("late", winner))
        client.portal.call(timer.scheduled[-1][1].fire)
        for _ in range(100):
            meeting = client.get(f"/api/meetings/{sid}").json()
            if meeting["status"] == "interrupted": break
            time.sleep(.02)
        terminal = request("after-expiry", winner)
        results.append({"action": "terminal cannot reopen", "status": terminal.status_code,
            "body": terminal.json(), "meeting": meeting})
    (directory / "result.json").write_text(json.dumps(results, indent=2))
    (EV / "BOUNDARIES-LATEST.txt").write_text(str(directory) + "\n")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__": main()
