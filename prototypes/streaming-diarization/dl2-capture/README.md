# DL2 retained dual-lane capture sprint

Prototype-only operator harness. Authoritative sprint: 2026-08-05 21:50 ET through 2026-08-06 07:50 ET. Program grant: TTL at most 24 hours, 2 GiB cumulative raw bytes, immediate raw deletion after derived outputs are sealed.

Real sequence:

```sh
python3 capture_harness.py preflight --program-root program --projected-bytes 256000000
python3 capture_harness.py begin --program-root program --shape S01 --operator-present --consented-content
python3 capture_harness.py finish --session-dir program/sessions/S01-SESSION_ID --operator-log /path/to/operator-cues.txt
python3 post_session.py program/sessions/S01-SESSION_ID
```

After pairing, the operator remains silent until `begin` returns success. `begin` verifies the
live snapshot at `.snapshot.descriptor.source_revision`, requires the pinned deployed revision,
and stops the session on any mismatch before issuing the recording cue.

`post_session.py` blind-transcribes system, microphone, and mixed WAVs through the deployed batch API, writes the JSON/text outputs and audit HTML, hashes derived artifacts, then deletes local and remote raw audio. A real run cannot use `--keep-raw`.

Fail-closed deployment fact: current retention is service-startup-scoped. The harness does not enable or edit it. `preflight` requires the live service already to declare the exact grant root/cap/TTL and returns `retention_not_declared` otherwise. This is intentionally not a service-management tool.

## Next-block rail — designed, not implemented

Add an authenticated controller heartbeat to every live harness session. If the
controller heartbeat is absent for more than 120 seconds, a separate bounded
watchdog should issue exactly one stop, then seal the reason, lane states,
published-frame count, and outbox count. This proposal follows the S05 orphaned-
capture incident; it is not present in this harness and grants no capture authority.
