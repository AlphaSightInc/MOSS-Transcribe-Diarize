#!/usr/bin/env python3
"""Fail-closed driver for operator-run, retained dual-lane capture sessions.

This is a prototype orchestrator.  It never changes TCC, volume, a service, a
manifest, or a deployed checkout.  The deployed live service must already have
the operator-approved retention declaration; otherwise real capture refuses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, Optional


DEPLOYED_SHA = "9089b33210401111865da7abc160ab0bcb4aa266"
SERVER = "gyauo@ga0-alienware-rtx4070ti.local"
SERVER_SHELL = "wsl.exe -d Ubuntu -- bash -s"
CAPTURE_HOST = "ga0@m4mbp"
CAPTURE_CLI = "$HOME/.local/bin/mtd-capture"
MAX_TTL_SECONDS = 86_400
MAX_PROGRAM_BYTES = 2_147_483_648
TRACKS = ("system", "microphone", "mixed")
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REMOTE_ROOT = re.compile(r"^/home/[A-Za-z0-9._/-]+$")


class HarnessRefusal(RuntimeError):
    """Named fail-closed refusal safe to expose in an operator transcript."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HarnessRefusal("json_object_required:%s" % path)
    return payload


def atomic_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(raw, path)
    finally:
        if os.path.exists(raw):
            os.unlink(raw)


def validate_grant(
    grant: Dict[str, Any], ledger: Dict[str, Any], projected_bytes: int = 0
) -> Dict[str, int]:
    ttl = grant.get("ttl_seconds")
    cap = grant.get("program_cap_bytes")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0 or ttl > MAX_TTL_SECONDS:
        raise HarnessRefusal("grant_bounds_refused:ttl_seconds")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0 or cap > MAX_PROGRAM_BYTES:
        raise HarnessRefusal("grant_bounds_refused:program_cap_bytes")
    captured = ledger.get("captured_bytes_total", 0)
    if not isinstance(captured, int) or isinstance(captured, bool) or captured < 0:
        raise HarnessRefusal("cap_ledger_invalid:captured_bytes_total")
    if not isinstance(projected_bytes, int) or projected_bytes < 0:
        raise HarnessRefusal("projected_bytes_invalid")
    if captured + projected_bytes > cap:
        raise HarnessRefusal(
            "program_cap_refused:captured=%d:projected=%d:cap=%d" % (captured, projected_bytes, cap)
        )
    return {"ttl_seconds": ttl, "program_cap_bytes": cap, "captured_bytes_total": captured}


def assert_no_overdue_retained_raw(
    grant: Dict[str, Any], ledger: Dict[str, Any], now: Optional[dt.datetime] = None
) -> None:
    deadline_text = grant.get("raw_delete_deadline_et")
    if not isinstance(deadline_text, str):
        raise HarnessRefusal("raw_delete_deadline_missing")
    deadline = dt.datetime.fromisoformat(deadline_text)
    observed = now or dt.datetime.now(dt.timezone.utc)
    overdue = [
        item.get("session_id")
        for item in ledger.get("sessions", [])
        if item.get("raw_deleted") is not True
    ]
    if overdue and observed >= deadline.astimezone(dt.timezone.utc):
        raise HarnessRefusal("retained_raw_cleanup_overdue:%s" % ",".join(str(item) for item in overdue))


def validate_capture_window(
    grant: Dict[str, Any],
    ledger: Dict[str, Any],
    shape_id: str,
    now: Optional[dt.datetime] = None,
    attempt_label: Optional[str] = None,
) -> str:
    observed = now or dt.datetime.now(dt.timezone.utc)
    decision_deadline = dt.datetime.fromisoformat(str(grant["decision_deadline_et"]))
    if observed < decision_deadline.astimezone(dt.timezone.utc):
        authorizations = grant.get("shape_authorizations")
        if isinstance(authorizations, list):
            allowed = {
                item.get("shape_id"): item
                for item in authorizations
                if isinstance(item, dict) and isinstance(item.get("shape_id"), str)
            }
            authorization = allowed.get(shape_id)
            if not isinstance(authorization, dict):
                raise HarnessRefusal("shape_not_authorized:%s" % shape_id)
            if authorization.get("single_use") is not True:
                raise HarnessRefusal("shape_single_use_required:%s" % shape_id)
            grant_id = grant.get("grant_id")
            if not isinstance(grant_id, str) or not grant_id:
                raise HarnessRefusal("grant_id_missing")
            if any(
                item.get("shape_id") == shape_id and item.get("grant_id") == grant_id
                for item in ledger.get("sessions", [])
            ):
                raise HarnessRefusal("shape_already_used:%s" % shape_id)
            return "GRANT_SINGLE_USE_SHAPE"
        return "SPRINT_WINDOW"
    continuation = grant.get("post_decision_pilot_authorization")
    if not isinstance(continuation, dict) or continuation.get("authorized") is not True:
        raise HarnessRefusal("sprint_capture_window_closed")
    if continuation.get("shape_id") != shape_id or continuation.get("single_use") is not True:
        raise HarnessRefusal("post_decision_capture_not_authorized:%s" % shape_id)
    pilot_used = any(
        item.get("shape_id") == shape_id and item.get("acceptance_case") is not False
        for item in ledger.get("sessions", [])
    )
    if pilot_used:
        retry = grant.get("post_decision_retry_authorization")
        if (
            not isinstance(retry, dict)
            or retry.get("authorized") is not True
            or retry.get("single_use") is not True
            or retry.get("shape_id") != shape_id
            or retry.get("attempt_label") != attempt_label
        ):
            raise HarnessRefusal("post_decision_pilot_already_used:%s" % shape_id)
        if any(item.get("attempt_label") == attempt_label for item in ledger.get("sessions", [])):
            raise HarnessRefusal("post_decision_retry_already_used:%s" % attempt_label)
        capture_window = "POST_DECISION_SINGLE_USE_RETRY"
    else:
        capture_window = "POST_DECISION_SINGLE_USE_PILOT"
    raw_deadline = dt.datetime.fromisoformat(str(grant["raw_delete_deadline_et"]))
    if observed >= raw_deadline.astimezone(dt.timezone.utc):
        raise HarnessRefusal("raw_retention_window_closed")
    return capture_window


def validate_tape_dir(tape_dir: Path, expected_session_id: str) -> Dict[str, Any]:
    if not SESSION_ID.fullmatch(expected_session_id):
        raise HarnessRefusal("session_id_invalid")
    index_path = tape_dir / "index.json"
    if not index_path.is_file():
        raise HarnessRefusal("tape_index_missing")
    index = read_json(index_path)
    if index.get("session_id") != expected_session_id:
        raise HarnessRefusal("tape_session_mismatch")
    sample_rate = index.get("sample_rate")
    if sample_rate != 16_000:
        raise HarnessRefusal("tape_sample_rate_invalid:%s" % sample_rate)
    declared = index.get("tracks")
    if not isinstance(declared, dict):
        raise HarnessRefusal("tape_tracks_invalid")
    checked: Dict[str, Any] = {}
    for name in TRACKS:
        track = declared.get(name)
        path = tape_dir / (name + ".pcm")
        if not isinstance(track, dict) or not path.is_file():
            raise HarnessRefusal("missing_lane_tape:%s" % name)
        samples = track.get("sample_count")
        byte_count = track.get("bytes")
        actual = path.stat().st_size
        if not isinstance(samples, int) or samples <= 0 or not isinstance(byte_count, int):
            raise HarnessRefusal("missing_lane_tape:%s" % name)
        if actual <= 0 or actual != byte_count or actual != samples * 2:
            raise HarnessRefusal("lane_tape_size_mismatch:%s" % name)
        checked[name] = {
            "sample_count": samples,
            "bytes": actual,
            "sha256": sha256(path),
            "path": str(path),
        }
    total = sum(item["bytes"] for item in checked.values())
    if index.get("total_bytes") != total:
        raise HarnessRefusal("tape_total_bytes_mismatch")
    return {
        "session_id": expected_session_id,
        "sample_rate": sample_rate,
        "total_bytes": total,
        "tracks": checked,
        "index_sha256": sha256(index_path),
        "degradation": index.get("degradation"),
        "ended_at": index.get("ended_at"),
    }


def run_text(argv: list, stdin: Optional[str] = None) -> str:
    completed = subprocess.run(argv, input=stdin, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise HarnessRefusal(
            "command_failed:exit=%d:argv=%r:stderr=%s"
            % (completed.returncode, argv, completed.stderr.strip())
        )
    return completed.stdout


def server_script(script: str) -> str:
    return run_text(["ssh", SERVER, SERVER_SHELL], stdin=script)


def capture_script(script: str) -> str:
    argv = ["ssh", CAPTURE_HOST, "bash -s"]
    completed = subprocess.run(argv, input=script, text=True, capture_output=True, check=False)
    if completed.returncode == 0:
        return completed.stdout
    if "Could not resolve hostname m4mbp" not in completed.stderr:
        raise HarnessRefusal(
            "command_failed:exit=%d:argv=%r:stderr=%s"
            % (completed.returncode, argv, completed.stderr.strip())
        )
    addresses = run_text(["tailscale", "ip", "-4", "m4mbp"]).splitlines()
    if len(addresses) != 1:
        raise HarnessRefusal("m4mbp_tailscale_resolution_invalid")
    address = ipaddress.ip_address(addresses[0].strip())
    if address.version != 4 or address not in ipaddress.ip_network("100.64.0.0/10"):
        raise HarnessRefusal("m4mbp_tailscale_address_refused:%s" % address)
    return run_text(
        [
            "ssh",
            "-o",
            "HostName=%s" % address,
            "-o",
            "HostKeyAlias=m4mbp",
            CAPTURE_HOST,
            "bash -s",
        ],
        stdin=script,
    )


def _parse_tab(raw: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for line in raw.splitlines():
        if "\t" not in line:
            continue
        key, value = line.split("\t", 1)
        values[key] = value
    return values


def server_preflight(grant: Dict[str, Any]) -> Dict[str, Any]:
    raw = server_script(
        r'''set -euo pipefail
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'service:%s\t%s/%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")"
done
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
printf 'main_pid\t%s\n' "$pid"
printf 'deployed_sha\t%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD)"
printf 'deployed_dirty_count\t%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain | wc -l)"
mapfile -d '' argv < "/proc/$pid/cmdline"
for ((i=0; i<${#argv[@]}; i++)); do
  case "${argv[$i]}" in
    --live-retention-root|--live-retention-max-bytes|--live-retention-ttl-seconds)
      printf 'flag:%s\t%s\n' "${argv[$i]}" "${argv[$((i+1))]:-}"
      ;;
  esac
done
'''
    )
    values = _parse_tab(raw)
    problems = []
    for unit in ("moss-live-web.service", "moss-web.service", "moss-vllm.service"):
        if values.get("service:" + unit) != "active/enabled":
            problems.append("service_unhealthy:%s:%s" % (unit, values.get("service:" + unit)))
    if values.get("deployed_sha") != DEPLOYED_SHA:
        problems.append("deployed_sha_mismatch:%s" % values.get("deployed_sha"))
    if values.get("deployed_dirty_count") != "0":
        problems.append("deployed_tree_dirty:%s" % values.get("deployed_dirty_count"))
    expected_root = str(grant["retention_root"])
    root = values.get("flag:--live-retention-root")
    if not root:
        problems.append("retention_not_declared")
    elif root != expected_root:
        problems.append("retention_root_mismatch:%s" % root)
    try:
        service_cap = int(values.get("flag:--live-retention-max-bytes", ""))
    except ValueError:
        service_cap = 0
    try:
        service_ttl = int(float(values.get("flag:--live-retention-ttl-seconds", "")))
    except ValueError:
        service_ttl = 0
    if root and (service_cap <= 0 or service_cap > int(grant["program_cap_bytes"])):
        problems.append("retention_service_cap_out_of_grant:%s" % service_cap)
    if root and (service_ttl <= 0 or service_ttl > int(grant["ttl_seconds"])):
        problems.append("retention_service_ttl_out_of_grant:%s" % service_ttl)
    if problems:
        raise HarnessRefusal("preflight_refused:" + ";".join(problems))
    return {
        "checked_at_utc": utc_now(),
        "raw_stdout": raw,
        "services": {unit: values["service:" + unit] for unit in ("moss-live-web.service", "moss-web.service", "moss-vllm.service")},
        "deployed_sha": values["deployed_sha"],
        "deployed_dirty_count": 0,
        "retention": {"root": root, "max_bytes_per_session": service_cap, "ttl_seconds": service_ttl},
        "verdict": "PASS_HEALTHY_DECLARED_WITHIN_GRANT",
    }


def capture_state() -> Dict[str, Any]:
    raw = capture_script(
        r'''set -euo pipefail
printf 'STATUS\t'
$HOME/.local/bin/mtd-capture status | tr -d '\n'
printf '\nTOPOLOGY\t'
printf 'output_volume=%s;output_muted=%s' "$(osascript -e 'output volume of (get volume settings)')" "$(osascript -e 'output muted of (get volume settings)')"
printf '\nCLI_SHA\t%s\n' "$(shasum -a 256 "$HOME/.local/bin/mtd-capture" | cut -d' ' -f1)"
'''
    )
    rows = _parse_tab(raw)
    status = json.loads(rows["STATUS"])
    return {
        "checked_at_utc": utc_now(),
        "status": status,
        "topology_read_only": rows.get("TOPOLOGY"),
        "capture_cli_sha256": rows.get("CLI_SHA"),
        "raw_stdout": raw,
    }


def capture_audio_devices() -> Dict[str, Any]:
    raw = capture_script(
        r'''set -euo pipefail
/usr/bin/swift - <<'SWIFT'
import Foundation
import CoreAudio

func device(_ selector: AudioObjectPropertySelector) throws -> AudioDeviceID {
  var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
  var value = AudioDeviceID(0)
  var size = UInt32(MemoryLayout<AudioDeviceID>.size)
  let status = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &value)
  guard status == noErr else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
  return value
}

func text(_ device: AudioDeviceID, _ selector: AudioObjectPropertySelector) throws -> String {
  var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
  var value: Unmanaged<CFString>? = nil
  var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
  let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &value)
  guard status == noErr, let value = value else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
  return value.takeUnretainedValue() as String
}

for (kind, selector) in [("INPUT", kAudioHardwarePropertyDefaultInputDevice), ("OUTPUT", kAudioHardwarePropertyDefaultOutputDevice)] {
  let value = try device(selector)
  print("\(kind)\t\(value)\t\(try text(value, kAudioObjectPropertyName))\t\(try text(value, kAudioDevicePropertyDeviceUID))")
}
SWIFT
'''
    )
    rows = _parse_tab(raw)
    devices: Dict[str, Any] = {"checked_at_utc": utc_now(), "raw_stdout": raw}
    for kind in ("INPUT", "OUTPUT"):
        fields = rows.get(kind, "").split("\t")
        if len(fields) != 3:
            raise HarnessRefusal("audio_device_probe_invalid:%s" % kind.lower())
        devices["default_" + kind.lower()] = {
            "audio_device_id": int(fields[0]),
            "name": fields[1],
            "uid": fields[2],
        }
    return devices


def assert_block_audio_devices(state: Dict[str, Any], requirements: Dict[str, Any]) -> None:
    input_device = state.get("default_input", {})
    output_device = state.get("default_output", {})
    expected_input = requirements.get("default_input_name")
    expected_input_uid = requirements.get("default_input_uid")
    expected_output_fragment = requirements.get("default_output_name_contains")
    if input_device.get("name") != expected_input or (
        expected_input_uid and input_device.get("uid") != expected_input_uid
    ):
        raise HarnessRefusal(
            "default_input_device_refused:name=%s:uid=%s"
            % (input_device.get("name"), input_device.get("uid"))
        )
    if not isinstance(expected_output_fragment, str) or expected_output_fragment not in str(
        output_device.get("name", "")
    ):
        raise HarnessRefusal(
            "default_output_device_refused:name=%s:uid=%s"
            % (output_device.get("name"), output_device.get("uid"))
        )


def assert_capture_idle(state: Dict[str, Any]) -> None:
    status = state.get("status", {})
    if status.get("running"):
        raise HarnessRefusal("live_session_active")
    lanes = {item.get("lane"): item.get("state") for item in status.get("lanes", [])}
    if lanes != {"system": "stopped", "microphone": "stopped"}:
        raise HarnessRefusal("capture_lanes_not_idle:%r" % lanes)


def sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: ("[REDACTED]" if any(mark in key.lower() for mark in ("token", "secret", "pairing")) else sanitize(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [sanitize(value) for value in payload]
    return payload


def begin_session(args: argparse.Namespace) -> int:
    if not args.operator_present or not args.consented_content:
        raise HarnessRefusal("operator_grant_confirmation_required")
    program_root = args.program_root.resolve()
    grant = read_json(program_root / "grant.json")
    ledger_path = program_root / "program-ledger.json"
    ledger = read_json(ledger_path)
    validate_grant(grant, ledger, projected_bytes=int(args.projected_bytes))
    assert_no_overdue_retained_raw(grant, ledger)
    attempt_label = getattr(args, "attempt_label", None) or args.shape
    capture_window = validate_capture_window(
        grant, ledger, args.shape, attempt_label=attempt_label
    )
    blueprint = read_json(Path(__file__).with_name("session-blueprint.json"))
    shapes = {item["shape_id"]: item for item in blueprint["sessions"]}
    if args.shape not in shapes:
        raise HarnessRefusal("shape_not_authorized:%s" % args.shape)
    before_server = server_preflight(grant)
    before_capture = capture_state()
    assert_capture_idle(before_capture)
    before_devices = None
    device_requirements = grant.get("device_requirements")
    if isinstance(device_requirements, dict):
        before_devices = capture_audio_devices()
        assert_block_audio_devices(before_devices, device_requirements)
    label = "dl2-%s-%s" % (attempt_label.lower(), dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    raw = capture_script(
        """set -euo pipefail
cli="$HOME/.local/bin/mtd-capture"
san=ga0-alienware-rtx4070ti.tailnet.aisight.us
ip=100.64.0.8
port=7861
pin=a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff
tmp="$(mktemp -d /tmp/dl2-session-preflight.XXXXXX)"
started=0
cleanup() {
  rc=$?
  trap - EXIT INT TERM
  if [ "$rc" -ne 0 ] && [ "$started" = 1 ]; then "$cli" stop >/dev/null 2>&1 || true; fi
  pbcopy < /dev/null
  rm -rf "$tmp"
  exit "$rc"
}
trap cleanup EXIT INT TERM
start="$($cli start --label %s)"
started=1
handoff="$($cli handoff)"
deadline=$((SECONDS + 3))
lanes_ready=0
status=''
while [ "$SECONDS" -lt "$deadline" ]; do
  status="$($cli status)"
  if [ "$(printf '%%s' "$status" | jq -r .running)" = true ] && [ "$(printf '%%s' "$status" | jq '[.lanes[] | select((.lane=="system" or .lane=="microphone") and .state=="capturing")] | length')" = 2 ]; then
    lanes_ready=1
    break
  fi
  sleep 0.1
done
test "$lanes_ready" = 1 || { echo "live_preflight_abort:lanes_not_capturing:$status" >&2; exit 78; }
sid="$(printf '%%s' "$handoff" | jq -r '.sessionID // empty')"
test -n "$sid" || { echo 'live_preflight_abort:session_id_missing' >&2; exit 78; }
token="$(pbpaste)"
test -n "$token" || { echo 'live_preflight_abort:view_token_missing' >&2; exit 78; }
echo | openssl s_client -connect "$ip:$port" -servername "$san" 2>/dev/null | openssl x509 > "$tmp/leaf.pem"
got="$(openssl x509 -in "$tmp/leaf.pem" -outform DER | shasum -a 256 | cut -d' ' -f1)"
test "$got" = "$pin" || { echo 'live_preflight_abort:certificate_pin_mismatch' >&2; exit 78; }
cfg() {
  printf 'header = "Authorization: Bearer %%s"\\n' "$token"
  printf 'silent\\n'
  printf 'cacert = "%%s"\\n' "$tmp/leaf.pem"
  printf 'resolve = "%%s:%%s:%%s"\\n' "$san" "$port" "$ip"
}
snapshot_code="$(cfg | curl -K - -m 10 -o "$tmp/snapshot.json" -w '%%{http_code}' "https://$san:$port/api/live/sessions/$sid/snapshot")"
test "$snapshot_code" = 200 || { echo "live_preflight_abort:snapshot_http_$snapshot_code" >&2; exit 78; }
source_revision="$(jq -r '.snapshot.descriptor.source_revision // empty' "$tmp/snapshot.json")"
test "$source_revision" = 9089b33210401111865da7abc160ab0bcb4aa266 || { echo "live_preflight_abort:source_revision_$source_revision" >&2; exit 78; }
snapshot_sha="$(shasum -a 256 "$tmp/snapshot.json" | cut -d' ' -f1)"
started=0
printf 'START\\t%%s\\nHANDOFF\\t%%s\\nSTATUS\\t%%s\\nSNAPSHOT_HTTP\\t%%s\\nSOURCE_REVISION\\t%%s\\nSNAPSHOT_SHA256\\t%%s\\n' "$start" "$handoff" "$status" "$snapshot_code" "$source_revision" "$snapshot_sha"
""" % label
    )
    rows = _parse_tab(raw)
    start = json.loads(rows["START"])
    handoff = json.loads(rows["HANDOFF"])
    status = json.loads(rows["STATUS"])
    if rows.get("SNAPSHOT_HTTP") != "200" or rows.get("SOURCE_REVISION") != DEPLOYED_SHA:
        raise HarnessRefusal("live_descriptor_preflight_failed")
    session_id = handoff.get("sessionID")
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        raise HarnessRefusal("capture_start_missing_session_id")
    lanes = {item.get("lane"): item.get("state") for item in status.get("lanes", [])}
    if not status.get("running") or set(lanes) != {"system", "microphone"}:
        raise HarnessRefusal("missing_live_lane_after_start:%r" % lanes)
    session_dir = program_root / "sessions" / (attempt_label + "-" + session_id)
    session_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": "moss-dl2-capture-session.v1",
        "shape": shapes[args.shape],
        "attempt_label": attempt_label,
        "session_id": session_id,
        "label": label,
        "state": "recording",
        "capture_window_authority": capture_window,
        "grant_id": grant.get("grant_id"),
        "started_at_utc": utc_now(),
        "program_raw_delete_deadline_et": grant["raw_delete_deadline_et"],
        "grant_sha256": sha256(program_root / "grant.json"),
        "host_before": {"server": before_server, "capture": before_capture, "audio_devices": before_devices},
        "capture_start": sanitize(start),
        "capture_handoff": sanitize(handoff),
        "capture_running_status": sanitize(status),
        "live_descriptor_preflight": {
            "snapshot_http": 200,
            "source_revision": rows["SOURCE_REVISION"],
            "snapshot_sha256": rows["SNAPSHOT_SHA256"],
            "verdict": "PASS_BEFORE_OPERATOR_SPEECH",
        },
        "safety": {"volume_changed_by_harness": False, "tcc_changed_by_harness": False, "service_changed_by_harness": False},
    }
    atomic_json(session_dir / "session-manifest.json", manifest)
    print(
        json.dumps(
            {
                "ok": True,
                "session_dir": str(session_dir),
                "session_id": session_id,
                "shape": args.shape,
                "descriptor_preflight": "PASS_BEFORE_OPERATOR_SPEECH",
                "operator_cue": "RECORD",
            }
        )
    )
    return 0


def pull_tape(root: str, session_id: str, destination: Path) -> None:
    if not REMOTE_ROOT.fullmatch(root) or ".." in Path(root).parts or not SESSION_ID.fullmatch(session_id):
        raise HarnessRefusal("remote_tape_target_invalid")
    script = "set -euo pipefail\ncd %s\ntest -d %s\nexec tar -cf - %s\n" % (root, session_id, session_id)
    completed = subprocess.run(
        ["ssh", SERVER, SERVER_SHELL], input=script.encode("utf-8"), capture_output=True, check=False
    )
    if completed.returncode:
        raise HarnessRefusal("tape_pull_failed:%s" % completed.stderr.decode("utf-8", "replace").strip())
    if destination.exists():
        raise HarnessRefusal("local_tape_destination_exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        members = archive.getmembers()
        prefix = session_id + "/"
        for member in members:
            if member.name != session_id and not member.name.startswith(prefix):
                raise HarnessRefusal("tape_archive_path_invalid:%s" % member.name)
            if member.issym() or member.islnk():
                raise HarnessRefusal("tape_archive_link_refused:%s" % member.name)
        archive.extractall(destination.parent)
    extracted = destination.parent / session_id
    if extracted != destination:
        extracted.rename(destination)


def pcm_to_wav(pcm: Path, wav: Path, sample_rate: int = 16_000) -> None:
    with pcm.open("rb") as source, wave.open(str(wav), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for block in iter(lambda: source.read(1024 * 1024), b""):
            output.writeframesraw(block)


def finish_stop(external_stop_recovery: bool = False) -> Dict[str, Any]:
    if external_stop_recovery:
        observed = capture_state()
        assert_capture_idle(observed)
        status = observed["status"]
        if status.get("outboxRetainedFrames") != 0:
            raise HarnessRefusal("external_stop_outbox_not_empty")
        return {
            "stop": {
                "ok": True,
                "external_stop_observed": True,
                "stop_command_issued_by_harness": False,
            },
            "status": status,
            "topology": observed.get("topology_read_only"),
            "deviation": {
                "kind": "external_stop_after_controller_loss",
                "authorized_recovery": True,
                "observed_at_utc": observed.get("checked_at_utc"),
                "published_frame_count": status.get("publishedFrameCount"),
                "outbox_retained_frames": status.get("outboxRetainedFrames"),
                "stop_command_reissued": False,
            },
        }
    stop_raw = capture_script(
        r'''set -euo pipefail
printf 'STOP\t'
$HOME/.local/bin/mtd-capture stop | tr -d '\n'
printf '\nSTATUS\t'
$HOME/.local/bin/mtd-capture status | tr -d '\n'
printf '\nTOPOLOGY\t'
printf 'output_volume=%s;output_muted=%s' "$(osascript -e 'output volume of (get volume settings)')" "$(osascript -e 'output muted of (get volume settings)')"
printf '\n'
'''
    )
    rows = _parse_tab(stop_raw)
    status = json.loads(rows["STATUS"])
    if status.get("running"):
        raise HarnessRefusal("capture_stop_not_acknowledged")
    return {
        "stop": json.loads(rows["STOP"]),
        "status": status,
        "topology": rows.get("TOPOLOGY"),
        "deviation": None,
    }


def finish_session(args: argparse.Namespace) -> int:
    session_dir = args.session_dir.resolve()
    manifest_path = session_dir / "session-manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("state") != "recording":
        raise HarnessRefusal("session_not_recording")
    session_id = str(manifest.get("session_id"))
    program_root = session_dir.parents[1]
    grant = read_json(program_root / "grant.json")
    ledger_path = program_root / "program-ledger.json"
    ledger = read_json(ledger_path)
    validate_grant(grant, ledger)
    stop_result = finish_stop(bool(getattr(args, "external_stop_recovery", False)))
    stop_status = stop_result["status"]
    after_server = server_preflight(grant)
    raw_dir = session_dir / "raw"
    pull_tape(str(grant["retention_root"]), session_id, raw_dir)
    tape = validate_tape_dir(raw_dir, session_id)
    validate_grant(grant, ledger, projected_bytes=int(tape["total_bytes"]))
    audio_dir = session_dir / "audio"
    audio_dir.mkdir()
    for name in TRACKS:
        pcm_to_wav(raw_dir / (name + ".pcm"), audio_dir / (name + ".wav"))
    ledger["captured_bytes_total"] = int(ledger.get("captured_bytes_total", 0)) + int(tape["total_bytes"])
    ledger.setdefault("sessions", []).append(
        {
            "session_id": session_id,
            "grant_id": manifest.get("grant_id"),
            "shape_id": manifest["shape"]["shape_id"],
            "attempt_label": manifest.get("attempt_label", manifest["shape"]["shape_id"]),
            "raw_bytes": tape["total_bytes"],
            "pulled_at_utc": utc_now(),
            "raw_deleted": False,
        }
    )
    atomic_json(ledger_path, ledger)
    manifest.update(
        {
            "state": "pulled_pending_asr",
            "ended_at_utc": utc_now(),
            "capture_stop": sanitize(stop_result["stop"]),
            "capture_stopped_status": sanitize(stop_status),
            "topology_after_read_only": stop_result.get("topology"),
            "host_after": {"server": after_server},
            "tape": tape,
            "audio": {
                name: {"path": "audio/%s.wav" % name, "sha256": sha256(audio_dir / (name + ".wav"))}
                for name in TRACKS
            },
        }
    )
    if stop_result.get("deviation") is not None:
        manifest["capture_stop_deviation"] = stop_result["deviation"]
    if args.operator_log is not None:
        operator_log = args.operator_log.resolve()
        if not operator_log.is_file():
            raise HarnessRefusal("operator_log_missing")
        copied_log = session_dir / "operator-cue-log.txt"
        shutil.copyfile(operator_log, copied_log)
        manifest["operator_cue_log"] = {
            "path": "operator-cue-log.txt",
            "sha256": sha256(copied_log),
        }
    atomic_json(manifest_path, manifest)
    print(json.dumps({"ok": True, "state": manifest["state"], "session_dir": str(session_dir), "raw_bytes": tape["total_bytes"]}))
    return 0


def remote_delete(root: str, session_id: str) -> None:
    if not REMOTE_ROOT.fullmatch(root) or ".." in Path(root).parts or not SESSION_ID.fullmatch(session_id):
        raise HarnessRefusal("remote_cleanup_target_invalid")
    server_script(
        "set -euo pipefail\ntarget=%s/%s\ntest -d \"$target\"\ntest \"$(basename \"$target\")\" = %s\nfind \"$target\" -type f -delete\nfind \"$target\" -depth -type d -empty -delete\ntest ! -e \"$target\"\n"
        % (root, session_id, session_id)
    )


def cleanup_raw(session_dir: Path, mock: bool = False) -> Dict[str, Any]:
    session_dir = session_dir.resolve()
    manifest_path = session_dir / "session-manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("state") not in {"derived_hashed", "audit_ready_raw_retained"}:
        raise HarnessRefusal("cleanup_before_derived_hash_refused")
    program_root = session_dir.parents[1]
    grant = read_json(program_root / "grant.json")
    session_id = str(manifest["session_id"])
    if not mock:
        remote_delete(str(grant["retention_root"]), session_id)
    removed = []
    for directory in (session_dir / "raw", session_dir / "audio"):
        if directory.exists():
            removed.append(str(directory.relative_to(session_dir)))
            shutil.rmtree(directory)
    ledger_path = program_root / "program-ledger.json"
    ledger = read_json(ledger_path)
    for item in ledger.get("sessions", []):
        if item.get("session_id") == session_id:
            item["raw_deleted"] = True
            item["raw_deleted_at_utc"] = utc_now()
    atomic_json(ledger_path, ledger)
    manifest["state"] = "audit_ready_raw_deleted"
    manifest["raw_cleanup"] = {"at_utc": utc_now(), "remote_deleted": not mock, "local_removed": removed, "mock": mock}
    atomic_json(manifest_path, manifest)
    return manifest["raw_cleanup"]


def preflight_command(args: argparse.Namespace) -> int:
    grant = read_json(args.program_root / "grant.json")
    ledger = read_json(args.program_root / "program-ledger.json")
    validate_grant(grant, ledger, projected_bytes=args.projected_bytes)
    assert_no_overdue_retained_raw(grant, ledger)
    server = server_preflight(grant)
    capture = capture_state()
    assert_capture_idle(capture)
    devices = None
    device_requirements = grant.get("device_requirements")
    if isinstance(device_requirements, dict):
        devices = capture_audio_devices()
        assert_block_audio_devices(devices, device_requirements)
    print(json.dumps({"ok": True, "server": server, "capture": capture, "audio_devices": devices}, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--program-root", type=Path, required=True)
    preflight.add_argument("--projected-bytes", type=int, default=0)
    preflight.set_defaults(func=preflight_command)
    begin = sub.add_parser("begin")
    begin.add_argument("--program-root", type=Path, required=True)
    begin.add_argument("--shape", required=True)
    begin.add_argument("--attempt-label")
    begin.add_argument("--projected-bytes", type=int, default=256_000_000)
    begin.add_argument("--operator-present", action="store_true")
    begin.add_argument("--consented-content", action="store_true")
    begin.set_defaults(func=begin_session)
    finish = sub.add_parser("finish")
    finish.add_argument("--session-dir", type=Path, required=True)
    finish.add_argument("--operator-log", type=Path)
    finish.add_argument("--external-stop-recovery", action="store_true")
    finish.set_defaults(func=finish_session)
    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--session-dir", type=Path, required=True)
    cleanup.set_defaults(func=lambda args: (print(json.dumps(cleanup_raw(args.session_dir))) or 0))
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except HarnessRefusal as exc:
        print("REFUSED %s" % exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
