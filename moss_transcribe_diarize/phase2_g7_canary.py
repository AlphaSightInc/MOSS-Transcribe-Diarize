"""Candidate-owned attended Chrome observation for the Wave-1 G7 cutover gate.

The profile supplies only host prerequisites.  This module owns the two browser scenarios,
observes the real capture requests and product state, and emits a content-free projection.  It
does not accept a caller-authored result document.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, Page, sync_playwright


G7_EVIDENCE_SCHEMA = "moss-phase2-attended-g7.v1"
G7_EVIDENCE_SOURCE = "candidate-owned-production-browser"
G7_SCENARIOS = {
    "microphone_meeting_tab": "browser",
    "microphone_entire_screen": "monitor",
}
FRAME_KEYS = {
    "lane",
    "sequence",
    "capture_timestamp_ns",
    "device_epoch",
    "pcm_base64",
    "sample_count",
    "sample_rate",
    "silent",
    "discontinuity",
}


class AttendedCanaryError(RuntimeError):
    """The production-origin attended observation did not establish G7."""


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AttendedCanaryError(f"attended prerequisite absent: {key}")
    return value.strip()


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _load_pre_admission_profile(path: Path) -> Mapping[str, object]:
    resolved = path.expanduser().resolve()
    if stat.S_IMODE(resolved.stat().st_mode) != 0o600:
        raise AttendedCanaryError("acceptance profile must be mode 0600")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    measurements = payload.get("measurements") if isinstance(payload, dict) else None
    config = measurements.get("pre_admission") if isinstance(measurements, dict) else None
    if not isinstance(config, dict):
        raise AttendedCanaryError("pre-admission browser prerequisites are absent")
    return config


def _frame_summary(frames: list[Mapping[str, object]], descriptor: Mapping[str, object]) -> dict[str, object]:
    frame_samples = descriptor.get("frame_samples")
    sample_rate = descriptor.get("sample_rate")
    if not isinstance(frame_samples, int) or frame_samples <= 0:
        raise AttendedCanaryError("descriptor frame geometry is invalid")
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise AttendedCanaryError("descriptor sample rate is invalid")
    result: dict[str, object] = {}
    for lane in ("microphone", "system"):
        rows = [row for row in frames if row.get("lane") == lane]
        sequences = sorted(
            {
                int(row["sequence"])
                for row in rows
                if isinstance(row.get("sequence"), int)
            }
        )
        gaps = (
            []
            if not sequences
            else sorted(set(range(sequences[0], sequences[-1] + 1)) - set(sequences))
        )
        result[lane] = {
            "accepted_frames": len(sequences),
            "first_sequence": None if not sequences else sequences[0],
            "last_sequence": None if not sequences else sequences[-1],
            "sequence_gaps": len(gaps),
            "geometry_mismatches": sum(
                1
                for row in rows
                if set(row) != FRAME_KEYS
                or row.get("sample_count") != frame_samples
                or row.get("sample_rate") != sample_rate
            ),
        }
    return result


def _probe_mp3(payload: bytes) -> dict[str, object]:
    process = subprocess.run(
        (
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bit_rate",
            "-of",
            "json",
            "pipe:0",
        ),
        input=payload,
        capture_output=True,
        check=False,
    )
    if process.returncode:
        raise AttendedCanaryError("owner audio download is not playable")
    try:
        stream = json.loads(process.stdout)["streams"][0]
        return {
            "codec": stream.get("codec_name"),
            "sample_rate_hz": int(stream.get("sample_rate")),
            "channels": int(stream.get("channels")),
            "bit_rate_bps": int(stream.get("bit_rate")),
            "byte_count": len(payload),
        }
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AttendedCanaryError("owner audio probe is incomplete") from exc


def _meeting_id_from_url(url: str) -> str | None:
    parts = urlsplit(url).path.strip("/").split("/")
    if len(parts) == 5 and parts[:3] == ["api", "live", "sessions"] and parts[4] == "frames":
        return parts[3]
    return None


def _meter_level(page: Page, label: str) -> int:
    value = page.locator(f'[aria-label^="{label} level "]').get_attribute("aria-label")
    if not isinstance(value, str) or not value.endswith("%"):
        return 0
    try:
        return int(value.rsplit(" ", 1)[1][:-1])
    except ValueError:
        return 0


def _observe_nonzero_meters(page: Page) -> dict[str, int]:
    """Observe, rather than infer, one nonzero sample from each independent lane."""

    counts = {"microphone": 0, "system": 0}
    for _sample in range(40):
        counts["microphone"] += int(_meter_level(page, "Microphone") > 0)
        counts["system"] += int(_meter_level(page, "Shared audio") > 0)
        if all(value > 0 for value in counts.values()):
            return counts
        page.wait_for_timeout(250)
    raise AttendedCanaryError("attended checkpoint did not observe both audio meters")


def _speaker_count(meeting: Mapping[str, object]) -> int:
    transcript = meeting.get("transcript")
    segments = transcript.get("segments") if isinstance(transcript, Mapping) else None
    if not isinstance(segments, list):
        return 0
    speakers: set[str] = set()
    for segment in segments:
        if not isinstance(segment, Mapping):
            continue
        text = segment.get("text")
        speaker = segment.get("speaker")
        if isinstance(text, str) and text.strip() and isinstance(speaker, str) and speaker:
            speakers.add(speaker)
    return len(speakers)


def _install_display_observer(context: BrowserContext) -> None:
    context.add_init_script(
        """
        (() => {
          const devices = navigator.mediaDevices;
          if (!devices || !devices.getDisplayMedia) return;
          const original = devices.getDisplayMedia.bind(devices);
          devices.getDisplayMedia = async (constraints) => {
            const stream = await original(constraints);
            const video = stream.getVideoTracks()[0];
            globalThis.__mossAttendedDisplay = {
              surface: video?.getSettings?.().displaySurface ?? null,
              audio_tracks: stream.getAudioTracks().length,
            };
            return stream;
          };
        })();
        """
    )


def _run_scenario(
    context: BrowserContext,
    *,
    origin: str,
    scenario: str,
    expected_surface: str,
    confirm: Callable[[str], str],
) -> dict[str, object]:
    page = context.new_page()
    accepted_frames: list[Mapping[str, object]] = []
    meeting_ids: set[str] = set()

    def observe(response: Any) -> None:
        meeting_id = _meeting_id_from_url(response.request.url)
        if meeting_id is None or response.status != 200:
            return
        try:
            body = response.request.post_data_json
        except Exception:
            return
        if isinstance(body, dict):
            accepted_frames.append(dict(body))
            meeting_ids.add(meeting_id)

    page.on("response", observe)
    try:
        page.goto(origin, wait_until="networkidle")
        page.wait_for_selector('[data-auth-state="signed-in"]')
        page.wait_for_selector('[data-boot="ready"]')
        descriptor_response = context.request.get(f"{origin}/api/live/descriptor")
        if descriptor_response.status != 200:
            raise AttendedCanaryError("Live descriptor is unavailable")
        descriptor_envelope = descriptor_response.json()
        descriptor = descriptor_envelope.get("descriptor")
        if not isinstance(descriptor, dict):
            raise AttendedCanaryError("Live descriptor is malformed")

        page.get_by_role("button", name="Enable microphone").click()
        page.get_by_role("button", name="Share audio").click()
        page.wait_for_function(
            "globalThis.__mossAttendedDisplay !== undefined", timeout=300_000
        )
        display = page.evaluate("globalThis.__mossAttendedDisplay ?? null")
        if not isinstance(display, dict):
            raise AttendedCanaryError("display capture observation is absent")
        if display.get("surface") != expected_surface or display.get("audio_tracks") != 1:
            raise AttendedCanaryError(f"{scenario} selected the wrong Chrome capture surface")
        confirm(
            f"{scenario}: make the microphone and selected shared source audible, then press "
            "Enter so MOSS can observe both lane meters before capture. "
        )
        meter_samples = _observe_nonzero_meters(page)
        page.wait_for_selector('[data-capture-phase="ready"]', timeout=120_000)

        page.get_by_role("button", name="Start capture").click()
        page.wait_for_selector('[data-capture-phase="active"]', timeout=120_000)
        confirm(
            f"{scenario}: keep both sources audible, speak distinctly, and press Enter only "
            "after the transcript visibly contains both speakers. "
        )
        if page.locator('[data-capture-phase="active"]').count() != 1:
            raise AttendedCanaryError(f"{scenario} capture ended before attended confirmation")
        page.get_by_role("button", name="Stop and finalize").click()
        page.wait_for_selector('[data-capture-phase="terminal"]', timeout=600_000)
        if len(meeting_ids) != 1:
            raise AttendedCanaryError(f"{scenario} did not bind exactly one Live Meeting")
        meeting_id = next(iter(meeting_ids))
        meeting_response = context.request.get(f"{origin}/api/meetings/{meeting_id}")
        if meeting_response.status != 200:
            raise AttendedCanaryError(f"{scenario} Meeting is not owner-readable")
        meeting = meeting_response.json()
        if not isinstance(meeting, dict):
            raise AttendedCanaryError(f"{scenario} Meeting payload is malformed")
        audio_response = context.request.get(
            f"{origin}/api/meetings/{meeting_id}/audio/download"
        )
        if audio_response.status != 200:
            raise AttendedCanaryError(f"{scenario} owner MP3 download failed")
        audio_probe = _probe_mp3(audio_response.body())
        frames = _frame_summary(accepted_frames, descriptor)
        return {
            "id": scenario,
            "session_id": meeting_id,
            "source_revision": descriptor.get("source_revision"),
            "display_surface": display.get("surface"),
            "display_audio_tracks": display.get("audio_tracks"),
            "meter_nonzero_samples": meter_samples,
            "frames": frames,
            "distinct_speakers": _speaker_count(meeting),
            "meeting_status": meeting.get("status"),
            "audio_state": (
                meeting.get("audio", {}).get("state")
                if isinstance(meeting.get("audio"), dict)
                else None
            ),
            "owner_download_status": audio_response.status,
            "audio_probe": audio_probe,
        }
    finally:
        page.close()


def validate_attended_g7(
    payload: Mapping[str, object], *, candidate: Mapping[str, object]
) -> None:
    identity = payload.get("candidate")
    scenarios = payload.get("scenarios")
    if (
        payload.get("schema") != G7_EVIDENCE_SCHEMA
        or payload.get("source") != G7_EVIDENCE_SOURCE
        or payload.get("production_origin") is not True
        or payload.get("operator_attended") is not True
        or payload.get("admitted") is not False
        or not isinstance(payload.get("origin"), str)
        or not str(payload.get("origin")).startswith("https://")
        or not isinstance(identity, Mapping)
        or any(identity.get(key) != candidate.get(key) for key in ("git_sha", "git_tree", "uv_lock_sha256"))
        or not isinstance(payload.get("chrome_version"), str)
        or not payload.get("chrome_version")
        or not isinstance(scenarios, list)
        or len(scenarios) != 2
    ):
        raise AttendedCanaryError("attended G7 evidence identity is incomplete")
    by_id = {
        row.get("id"): row for row in scenarios if isinstance(row, Mapping)
    }
    if set(by_id) != set(G7_SCENARIOS):
        raise AttendedCanaryError("attended G7 scenarios are incomplete")
    session_ids = {
        row.get("session_id") for row in by_id.values() if isinstance(row.get("session_id"), str)
    }
    if len(session_ids) != 2 or any(not value for value in session_ids):
        raise AttendedCanaryError("attended G7 session identity is incomplete")
    for scenario, surface in G7_SCENARIOS.items():
        row = by_id[scenario]
        frames = row.get("frames")
        meters = row.get("meter_nonzero_samples")
        probe = row.get("audio_probe")
        if (
            row.get("display_surface") != surface
            or row.get("display_audio_tracks") != 1
            or not isinstance(meters, Mapping)
            or set(meters) != {"microphone", "system"}
            or any(not _positive_int(meters.get(lane)) for lane in meters)
            or not isinstance(frames, Mapping)
            or set(frames) != {"microphone", "system"}
            or row.get("source_revision") != candidate.get("git_sha")
            or not _positive_int(row.get("distinct_speakers"))
            or int(row["distinct_speakers"]) < 2
            or row.get("meeting_status") != "completed"
            or row.get("audio_state") != "available"
            or row.get("owner_download_status") != 200
            or not isinstance(probe, Mapping)
            or probe.get("codec") != "mp3"
            or probe.get("sample_rate_hz") != 16_000
            or probe.get("channels") != 1
            or probe.get("bit_rate_bps") != 48_000
            or not _positive_int(probe.get("byte_count"))
        ):
            raise AttendedCanaryError(f"attended G7 scenario failed: {scenario}")
        for lane in ("microphone", "system"):
            lane_row = frames.get(lane)
            if (
                not isinstance(lane_row, Mapping)
                or not _positive_int(lane_row.get("accepted_frames"))
                or lane_row.get("first_sequence") != 0
                or lane_row.get("sequence_gaps") != 0
                or lane_row.get("geometry_mismatches") != 0
            ):
                raise AttendedCanaryError(
                    f"attended G7 {scenario} {lane} frame evidence failed"
                )


def run_attended_g7_canary(
    *,
    acceptance_profile: Path,
    candidate: Mapping[str, object],
    confirm: Callable[[str], str] = input,
) -> dict[str, object]:
    """Run both fixed attended scenarios against the production origin.

    A non-interactive process cannot silently manufacture attendance; it fails before browser
    mutation.  The caller persists only the returned content-free projection in its own attempt.
    """

    if confirm is input and not sys.stdin.isatty():
        raise AttendedCanaryError("attended G7 requires an interactive terminal")
    config = _load_pre_admission_profile(acceptance_profile)
    origin = _required_text(config, "https_origin").rstrip("/")
    if not origin.startswith("https://"):
        raise AttendedCanaryError("attended G7 requires the production HTTPS origin")
    chrome = Path(_required_text(config, "chrome_binary")).expanduser().resolve()
    profile = Path(
        _required_text(config, "allowed_google_browser_profile")
    ).expanduser().resolve()
    if not chrome.is_file() or not profile.is_dir():
        raise AttendedCanaryError("attended Chrome prerequisites are unavailable")

    scenarios: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile), executable_path=str(chrome), headless=False
        )
        try:
            _install_display_observer(context)
            for scenario, surface in G7_SCENARIOS.items():
                print(
                    f"G7 attended canary: choose Chrome display surface {surface!r} for {scenario}; "
                    "enable shared audio.",
                    flush=True,
                )
                scenarios.append(
                    _run_scenario(
                        context,
                        origin=origin,
                        scenario=scenario,
                        expected_surface=surface,
                        confirm=confirm,
                    )
                )
            chrome_version = context.browser.version if context.browser is not None else ""
        finally:
            context.close()
    evidence = {
        "schema": G7_EVIDENCE_SCHEMA,
        "source": G7_EVIDENCE_SOURCE,
        "production_origin": True,
        "operator_attended": True,
        "admitted": False,
        "origin": origin,
        "candidate": {
            key: candidate.get(key) for key in ("git_sha", "git_tree", "uv_lock_sha256")
        },
        "chrome_version": chrome_version,
        "scenarios": scenarios,
    }
    validate_attended_g7(evidence, candidate=candidate)
    return evidence
