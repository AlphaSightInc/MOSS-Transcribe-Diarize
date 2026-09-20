"""One headed-Chrome live source-word visibility observation.

Raw transcripts stay in memory. The retained output contains reference IDs,
outcomes, timings, counts, and content-free server clock fields only.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
from pathlib import Path
import time
from typing import Any, Sequence
from urllib.parse import urlsplit
import wave

from tests.phase2.browser_support import BrowserExecutableMissing, browser_executable
from tools.qualify.visible_words import (
    TranscriptObservation,
    TranscriptSegment,
    evaluate_visible_word_surfaces,
    reference_words_from_intervals,
)


_CLOCK_FIELDS = frozenset(
    {
        "runtime_monotonic_ns",
        "queue_wait_ms",
        "canonical_processing_elapsed_ms",
        "queued_to_processed_ms",
        "queued_to_completed_ms",
        "canonical_decode_elapsed_sec",
        "rolling_decode_elapsed_sec",
        "preparation_elapsed_sec",
        "other_finalize_elapsed_sec",
        "total_elapsed_sec",
        "window_index",
        "batch_index",
        "batch_size",
        "start_sample",
        "end_sample",
        "window_samples",
        "finalization_status",
        "outcome",
    }
)


def _clock_projection(event: dict[str, Any]) -> dict[str, object] | None:
    kind = event.get("kind")
    if kind not in {
        "canonical_processed",
        "rolling_decode_queued",
        "rolling_decode_completed",
        "terminal_finalization_started",
        "terminal_finalization_completed",
        "terminal_finalization_failed",
    }:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return {
        "seq": event.get("seq"),
        "kind": kind,
        **{key: payload[key] for key in _CLOCK_FIELDS if key in payload},
    }


def _read_reference(path: Path, seconds: float) -> tuple[dict[str, object], ...]:
    result = []
    for index, line in enumerate(path.read_text().splitlines()):
        row = json.loads(line)
        if float(row["end"]) <= seconds:
            result.append(
                {
                    "id": str(row.get("id", f"source-{index}")),
                    "text": str(row["text"]),
                    "start": float(row["start"]),
                    "end": float(row["end"]),
                }
            )
    return tuple(result)


def _chromium_args() -> list[str]:
    return ["--mute-audio"]


async def _api(page: Any, path: str) -> dict[str, Any]:
    result = await page.evaluate(
        """async path => {
          const response = await fetch(path);
          return {status: response.status, body: await response.json()};
        }""",
        path,
    )
    if result["status"] >= 400:
        raise RuntimeError(f"API {path} returned HTTP {result['status']}")
    return result["body"]


async def _api_post(page: Any, path: str, body: dict[str, object]) -> dict[str, Any]:
    result = await page.evaluate(
        """async request => {
          const response = await fetch(request.path, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(request.body)
          });
          return {status: response.status, body: await response.json()};
        }""",
        {"path": path, "body": body},
    )
    if result["status"] >= 400:
        raise RuntimeError(f"API {path} returned HTTP {result['status']}: {result['body']}")
    return result["body"]


def _read_pcm16(path: Path, sample_rate: int, seconds: float) -> bytes:
    with wave.open(str(path), "rb") as source:
        if (
            source.getnchannels() != 1
            or source.getsampwidth() != 2
            or source.getframerate() != sample_rate
        ):
            raise ValueError(f"{path} must be mono 16-bit PCM at {sample_rate} Hz")
        expected = round(seconds * sample_rate)
        if source.getnframes() != expected:
            raise ValueError(f"{path} must contain exactly {seconds:g} seconds")
        return source.readframes(expected)


def _frame_payload(
    lane: str,
    sequence: int,
    pcm: bytes,
    *,
    frame_samples: int,
    sample_rate: int,
    device_epoch: int,
) -> dict[str, object]:
    return {
        "lane": lane,
        "sequence": sequence,
        "capture_timestamp_ns": device_epoch
        + round(sequence * frame_samples / sample_rate * 1_000_000_000),
        "device_epoch": device_epoch,
        "pcm_base64": base64.b64encode(pcm).decode("ascii"),
        "sample_count": frame_samples,
        "sample_rate": sample_rate,
        "silent": not any(pcm),
        "discontinuity": False,
    }


def _snapshot_segments(body: dict[str, Any]) -> tuple[TranscriptSegment, ...]:
    session = ((body.get("snapshot") or {}).get("session") or {})
    transcript = session.get("effective_transcript") or []
    segments = transcript.get("segments", []) if isinstance(transcript, dict) else transcript
    return tuple(
        TranscriptSegment(
            float(segment["start_sample"]) / 16_000,
            float(segment["end_sample"]) / 16_000,
            str(segment.get("text", "")),
        )
        for segment in segments
        if isinstance(segment, dict)
        and float(segment.get("end_sample", 0)) > float(segment.get("start_sample", 0))
    )


def _dom_segments(
    rows: list[dict[str, object]],
) -> tuple[tuple[TranscriptSegment, ...], str | None]:
    result = []
    for row in rows:
        try:
            start = float(row["start"])
            end = float(row["end"])
        except (KeyError, TypeError, ValueError):
            return (), "rendered row lacks its model-state source span"
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            return (), "rendered row lacks a finite positive model-state source span"
        result.append(TranscriptSegment(start, end, str(row["text"])))
    return tuple(result), None


def _observation_due(
    segments: tuple[TranscriptSegment, ...],
    *,
    previous_segments: tuple[TranscriptSegment, ...] | None,
    previous_elapsed_sec: float | None,
    elapsed_sec: float,
    source_ends: Sequence[float],
) -> bool:
    """Record content changes and the first poll across each source-phrase end."""

    return (
        previous_segments is None
        or segments != previous_segments
        or previous_elapsed_sec is None
        or any(previous_elapsed_sec < end <= elapsed_sec for end in source_ends)
    )


async def _run(args: argparse.Namespace) -> dict[str, object]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is unavailable") from exc

    intervals = _read_reference(args.reference, args.seconds)
    references = reference_words_from_intervals(intervals)
    source_ends = tuple(sorted({reference.source_end_sec for reference in references}))
    api_observations: list[TranscriptObservation] = []
    dom_observations: list[TranscriptObservation] = []
    decoder_queue_clocks: list[dict[str, object]] = []
    hidden_observations = 0
    total_visibility_observations = 0
    final_status = None
    finalization_status = None
    dom_unmeasured_reason = None

    async with async_playwright() as playwright:
        try:
            executable = browser_executable(playwright)
        except BrowserExecutableMissing as exc:
            raise RuntimeError(str(exc)) from exc
        browser = await playwright.chromium.launch(
            executable_path=str(executable),
            channel="chromium",
            headless=False,
            args=_chromium_args(),
        )
        context = await browser.new_context(
            ignore_https_errors=urlsplit(args.base).hostname in {"127.0.0.1", "localhost"},
            viewport={"width": 1440, "height": 1100},
        )
        page = await context.new_page()
        try:
                    await page.goto(args.base)
                    await page.locator('[data-auth-state="signed-in"]').wait_for(timeout=30_000)
                    await page.locator('[data-boot="ready"]').wait_for(timeout=30_000)
                    descriptor = (await _api(page, "/api/live/descriptor"))["descriptor"]
                    frame_samples = int(descriptor["frame_samples"])
                    sample_rate = int(descriptor["sample_rate"])
                    cadence = frame_samples / sample_rate
                    if cadence != 0.5:
                        raise RuntimeError("headed arm requires 0.5-second live frames")
                    lane_pcm = {
                        "system": _read_pcm16(args.system_wav, sample_rate, args.seconds),
                        "microphone": _read_pcm16(
                            args.microphone_wav, sample_rate, args.seconds
                        ),
                    }
                    created = await _api_post(
                        page,
                        "/api/live/sessions",
                        {"source_revision": descriptor["source_revision"]},
                    )
                    meeting_id = str(created["id"])
                    await page.evaluate(
                        """meetingId => document.dispatchEvent(new CustomEvent(
                          "moss:observe-live-meeting", {detail: {meetingId}}
                        ))""",
                        meeting_id,
                    )
                    started = time.monotonic()
                    device_epoch = time.time_ns()
                    next_event = -1
                    last_api: tuple[TranscriptSegment, ...] | None = None
                    last_dom: tuple[TranscriptSegment, ...] | None = None
                    last_api_elapsed: float | None = None
                    last_dom_elapsed: float | None = None

                    async def observe() -> None:
                        nonlocal next_event, last_api, last_dom, hidden_observations
                        nonlocal total_visibility_observations, final_status, finalization_status
                        nonlocal dom_unmeasured_reason
                        nonlocal last_api_elapsed, last_dom_elapsed
                        snapshot = await _api(page, f"/api/live/sessions/{meeting_id}/snapshot")
                        api_elapsed = time.monotonic() - started
                        api_segments = _snapshot_segments(snapshot)
                        if _observation_due(
                            api_segments,
                            previous_segments=last_api,
                            previous_elapsed_sec=last_api_elapsed,
                            elapsed_sec=api_elapsed,
                            source_ends=source_ends,
                        ):
                            api_observations.append(
                                TranscriptObservation(api_elapsed, api_segments)
                            )
                            last_api = api_segments
                            last_api_elapsed = api_elapsed
                        dom_rows = await page.locator(".utt").evaluate_all(
                            """nodes => nodes.map(node => {
                              return {
                                start: node.dataset.turnStart ?? null,
                                end: node.dataset.turnEnd ?? null,
                                targetKeys: node.dataset.targetKeys ?? null,
                                text: node.querySelector('.utt-text')?.textContent || ''
                              };
                            })"""
                        )
                        dom_elapsed = time.monotonic() - started
                        dom_segments, span_error = _dom_segments(dom_rows)
                        if span_error is not None:
                            dom_unmeasured_reason = span_error
                            dom_observations.clear()
                            last_dom = None
                            last_dom_elapsed = None
                        elif dom_unmeasured_reason is None and _observation_due(
                            dom_segments,
                            previous_segments=last_dom,
                            previous_elapsed_sec=last_dom_elapsed,
                            elapsed_sec=dom_elapsed,
                            source_ends=source_ends,
                        ):
                            dom_observations.append(
                                TranscriptObservation(dom_elapsed, dom_segments)
                            )
                            last_dom = dom_segments
                            last_dom_elapsed = dom_elapsed
                        hidden = bool(await page.evaluate("document.hidden"))
                        total_visibility_observations += 1
                        hidden_observations += int(hidden)
                        event_body = await _api(
                            page, f"/api/live/sessions/{meeting_id}/events?since_seq={next_event}"
                        )
                        events = event_body.get("events", [])
                        for event in events:
                            projection = _clock_projection(event)
                            if projection is not None:
                                decoder_queue_clocks.append(projection)
                        if events:
                            next_event = int(events[-1]["seq"]) + 1
                        session = ((snapshot.get("snapshot") or {}).get("session") or {})
                        final_status = session.get("status")
                        finalization_status = session.get("finalization_status")

                    frame_bytes = frame_samples * 2
                    total_frames = round(args.seconds / cadence)
                    for sequence in range(total_frames):
                        target = started + sequence * cadence
                        await asyncio.sleep(max(0, target - time.monotonic()))
                        health = {
                            "state": "capturing",
                            "device_epoch": device_epoch,
                            "dropped_frames": 0,
                            "discontinuities": 0,
                            "failure_code": None,
                        }
                        await _api_post(
                            page,
                            f"/api/live/sessions/{meeting_id}/heartbeat",
                            {
                                "schema": "moss-live-helper-health.v1",
                                "instance_id": "visible-word-headed",
                                "sequence": sequence,
                                "sent_monotonic_ns": time.monotonic_ns(),
                                "helper_version": "qualification",
                                "state": "capturing",
                                "lanes": {
                                    "system": health,
                                    "microphone": dict(health),
                                },
                            },
                        )
                        offset = sequence * frame_bytes
                        for lane, pcm in lane_pcm.items():
                            chunk = pcm[offset : offset + frame_bytes]
                            await _api_post(
                                page,
                                f"/api/live/sessions/{meeting_id}/frames",
                                _frame_payload(
                                    lane,
                                    sequence,
                                    chunk,
                                    frame_samples=frame_samples,
                                    sample_rate=sample_rate,
                                    device_epoch=device_epoch,
                                ),
                            )
                        await observe()
                    await asyncio.sleep(max(0, started + args.seconds - time.monotonic()))
                    await _api_post(
                        page, f"/api/live/sessions/{meeting_id}/stop", {"deadline": 30}
                    )
                    terminal_deadline = time.monotonic() + args.terminal_timeout
                    while time.monotonic() < terminal_deadline:
                        await asyncio.sleep(args.poll_seconds)
                        await observe()
                        if finalization_status in {"final", "failed", "unavailable"}:
                            break
                    else:
                        raise RuntimeError("headed live session did not reach terminal state")

                    measured = evaluate_visible_word_surfaces(
                        references,
                        api_observations=api_observations,
                        rendered_observations=dom_observations,
                        rendered_unmeasured_reason=dom_unmeasured_reason,
                        decoder_queue_clocks=decoder_queue_clocks,
                    )
                    return {
                        "schema": "moss-visible-word-headed.v1",
                        "browser": "headed Chromium",
                        "capture_path": "production live-frame API",
                        "session_seconds": args.seconds,
                        "reference_intervals": len(intervals),
                        "reference_words": len(references),
                        "api_state_changes": len(api_observations),
                        "dom_state_changes": len(dom_observations),
                        "visibility_observations": total_visibility_observations,
                        "document_hidden_true": hidden_observations,
                        "hidden_tab_behavior": (
                            "MEASURED" if hidden_observations else "UNMEASURED"
                        ),
                        "meeting_status": final_status,
                        "finalization_status": finalization_status,
                        "measurement": measured,
                        "numeric_latency_target": "USER_DECISION",
                    }
        finally:
            await context.close()
            await browser.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--system-wav", required=True, type=Path)
    parser.add_argument("--microphone-wav", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=float, default=300.0)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--terminal-timeout", type=float, default=600.0)
    args = parser.parse_args(argv)
    if args.seconds != 300.0:
        parser.error("the headed arm is exactly one 300-second session")
    if args.output.exists():
        parser.error("output must not already exist")
    result = asyncio.run(_run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "reference_words": result["reference_words"],
                "api_state_changes": result["api_state_changes"],
                "dom_state_changes": result["dom_state_changes"],
                "hidden_tab_behavior": result["hidden_tab_behavior"],
                "meeting_status": result["meeting_status"],
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
