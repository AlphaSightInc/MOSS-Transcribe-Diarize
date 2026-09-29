"""Q-SUM HTTP check for owner isolation, five-field output, and optional live cadence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app.phase2_summary import validate_summary


def summary_check(client: httpx.Client, meeting_id: str, *, live: bool):
    path = f"/api/meetings/{meeting_id}/summary/{'live' if live else 'server'}"
    meeting = client.get(f"/api/meetings/{meeting_id}")
    meeting.raise_for_status()
    source = meeting.json()
    body = {} if live else {"source_version": source["transcript_version"]}
    requested_at_ms = int(time.time() * 1000)
    response = client.post(path, json=body, timeout=210)
    response.raise_for_status()
    payload = response.json()
    usage = payload["usage"]
    if (set(usage) != {"model", "input_tokens", "output_tokens", "cost_usd"}
            or not isinstance(usage["model"], str)
            or any(type(usage[key]) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens"))
            or not isinstance(usage["cost_usd"], (int, float)) or usage["cost_usd"] < 0):
        raise ValueError("Invalid summary usage object.")
    document = payload["summary"] if live else payload["document"]
    duration = max((float(row["end"]) for row in (source.get("transcript") or {}).get("segments", [])), default=0)
    if live:
        duration = payload["source"]["committed_samples"] / 16000
    validate_summary(document, duration)
    return {"meeting_id": meeting_id, "live": live, "requested_at_ms": requested_at_ms,
            "generated_at_ms": payload.get("generated_at_ms"),
            "source": payload.get("source"), "five_keys_valid": True,
            "summary_chars": len(document["summary"]), "source_version": body.get("source_version"),
            "usage": usage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--foreign-base-url", help="private-workspace stack sharing this meeting store")
    parser.add_argument("--cookie-file", type=Path, help="mode-0600 owner session value used by the replay")
    meeting = parser.add_mutually_exclusive_group(required=True)
    meeting.add_argument("--meeting-id")
    meeting.add_argument("--meeting-id-file", type=Path, help="wait for the replay's session-id.txt")
    parser.add_argument("--case", choices=("e1", "long60", "smoke"), required=True)
    parser.add_argument("--source-clip-id", help="public clip ID for a one-clip smoke run")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--rolling-until-terminal", action="store_true")
    parser.add_argument("--final-after-terminal", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.base_url.startswith("https://127.0.0.1:"):
        parser.error("local HTTPS loopback stack required")
    if args.foreign_base_url and not args.foreign_base_url.startswith("https://127.0.0.1:"):
        parser.error("local HTTPS loopback foreign stack required")
    if args.out.exists():
        parser.error("--out must be new")
    args.out.mkdir(parents=True)
    meeting_id = args.meeting_id
    if args.meeting_id_file:
        deadline = time.monotonic() + 120
        while not args.meeting_id_file.is_file() and time.monotonic() < deadline:
            time.sleep(.25)
        if not args.meeting_id_file.is_file():
            raise TimeoutError("Replay did not publish a meeting ID.")
        meeting_id = args.meeting_id_file.read_text(encoding="utf-8").strip()
    if not meeting_id:
        parser.error("meeting ID is empty")
    with httpx.Client(base_url=args.base_url, verify=False, follow_redirects=False, timeout=210) as client:
        if args.cookie_file:
            if args.cookie_file.stat().st_mode & 0o777 != 0o600:
                parser.error("owner cookie file must have mode 0600")
            client.cookies.set("__Host-moss_session", args.cookie_file.read_text(encoding="utf-8").strip())
        else:
            client.post("/api/workspace/bootstrap").raise_for_status()
        checks = []
        if args.rolling_until_terminal:
            if not args.live:
                parser.error("--rolling-until-terminal requires --live")
            next_call = time.monotonic()
            while True:
                time.sleep(max(0, next_call - time.monotonic()))
                next_call += 60
                meeting = client.get(f"/api/meetings/{meeting_id}")
                meeting.raise_for_status()
                if meeting.json()["status"] != "active":
                    break
                try:
                    checks.append(summary_check(client, meeting_id, live=True))
                    next_call = time.monotonic() + 60
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 409:
                        raise
                    next_call = time.monotonic() + 2
        else:
            checks.append(summary_check(client, meeting_id, live=args.live))
        if args.final_after_terminal:
            checks.append(summary_check(client, meeting_id, live=False))
        foreign = httpx.Client(base_url=args.foreign_base_url or args.base_url,
                               verify=False, follow_redirects=False, timeout=30)
        try:
            foreign.post("/api/workspace/bootstrap").raise_for_status()
            wrong_owner = foreign.post(f"/api/meetings/{meeting_id}/summary/{'live' if args.live else 'server'}",
                                       json={} if args.live else {"source_version": 1}).status_code
        finally:
            foreign.close()
    times = [row["requested_at_ms"] for row in checks if row["live"]]
    intervals = [b - a for a, b in zip(times, times[1:])]
    result = {"schema": "q-sum.v1", "case": args.case,
              "source_clip_id": args.source_clip_id,
              "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "checks": checks, "rolling_intervals_ms": intervals,
              "wrong_owner_status": wrong_owner,
              "usage_total_usd": round(sum(row["usage"]["cost_usd"] for row in checks), 9),
              "rolling_cadence_status": "UNMEASURED" if len(intervals) == 0 else "OBSERVED"}
    (args.out / "q-sum.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
