"""One-command offline bench; full state plus decisive checks, no product tests."""
import json
import sys
from pathlib import Path

import run
import boundaries
import browser_probe


def summarize():
    ev = run.EV
    paths = {name: Path((ev / pointer).read_text().strip()) for name, pointer in (
        ("protocol", "LATEST.txt"), ("boundaries", "BOUNDARIES-LATEST.txt"), ("browser", "BROWSER-LATEST.txt"))}
    matrix = json.loads((paths["protocol"] / "matrix.json").read_text())
    browser = json.loads((paths["browser"] / "result.json").read_text())
    boundary = json.loads((paths["boundaries"] / "result.json").read_text())
    checks = {}
    for cell in matrix:
        if cell["mode"] != "S2": continue
        name = f"gap{cell['gap_seconds']}-continue{cell['continuation_seconds']}"
        if cell["gap_seconds"] >= 120:
            checks[name] = cell["resume_status"] == 409 and cell["final_status"] == "interrupted" and cell["frames_accepted_after_resume"] == 0
            continue
        rows = cell["meeting"]["transcript"]["segments"]
        post = [r for r in rows if r["start"] >= run.N + cell["gap_seconds"]]
        pre = [r for r in rows if r["end"] <= run.N]
        checks[name] = (
            cell["final_status"] == "completed" and cell["same_engine"] and cell["engine_count"] == 1
            and cell["frames_accepted_after_resume"] == cell["continuation_seconds"] * 4
            and cell["decoded_mp3_seconds"] == run.N + cell["gap_seconds"] + cell["continuation_seconds"]
            and cell["gap_interior_max_amplitude"] == 0 and cell["archives"] == ["audio.mp3"]
            and post[0]["start"] - pre[-1]["end"] == cell["gap_seconds"]
            and {r["speaker"] for r in rows} == {"Alex"}
            and {r["speaker_entity_id"] for r in rows} == {"speaker-0001"}
            and cell["max_retained_samples"] < 960000
            and all(r["status"] == 409 for r in cell["events"] if r["action"].startswith("old ")))
    statuses = {r["action"]: r["status"] for r in boundary}
    checks["boundaries"] = (sorted(statuses[k] for k in statuses if k.startswith("concurrent takeover")) == [200, 409]
        and statuses["same account different sign-in session"] == 403
        and statuses["lost response retry"] == 200 and statuses["at exact deadline before timer callback"] == 409
        and statuses["terminal cannot reopen"] == 409)
    before, after = browser["before"]["actions"][0], browser["after"]["actions"][-1]
    checks["chrome_reload_same_settings"] = (
        browser["meeting"]["status"] == "completed" and browser["local_server_stopped"]
        and not browser["after"]["errors"] and before["saved"]["meetingId"] == browser["stored_after"]["meetingId"]
        and before["saved"]["microphoneDeviceId"] == browser["stored_after"]["microphoneDeviceId"]
        and before["saved"]["microphoneMuted"] == browser["stored_after"]["microphoneMuted"]
        and before["saved"]["sources"] == browser["stored_after"]["sources"]
        and before["audioSettings"]["echoCancellation"] == after["audioSettings"]["echoCancellation"]
        and before["saved"]["displaySurface"] == browser["stored_after"]["displaySurface"])
    checks["chrome_frames_adopted"] = all(r["status"] == 200 for r in browser["after"]["frames"])
    checks["chrome_no_gesture_microphone"] = browser["no_gesture"]["activation"] is False and browser["no_gesture"]["after"] == "running"
    summary = {"checks": checks, "evidence": {k: str(v) for k, v in paths.items()},
        "chrome_display_without_gesture": browser["display_without_gesture_no_autoselect"],
        "share_track_label_stable": before["saved"]["shareLabel"] == after["selectedShareLabel"],
        "share_selection": "same named synthetic tab chosen by Chrome automation; opaque track label is not source identity",
        "provider_calls": 0, "product_changes": 0}
    (ev / "SUMMARY.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    if not all(checks.values()): raise SystemExit("Measurement contract failed; inspect retained full states")


def main():
    run.main()
    boundaries.main()
    browser_probe.main()
    summarize()


if __name__ == "__main__":
    summarize() if "--summarize" in sys.argv else main()
