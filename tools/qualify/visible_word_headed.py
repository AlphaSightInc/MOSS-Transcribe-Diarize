"""One headed-Chrome live source-word visibility observation.

Raw transcripts stay in memory. The retained output contains reference IDs,
outcomes, timings, counts, and content-free server clock fields only.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import json
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Sequence
from urllib.parse import urlsplit

from tests.phase2.browser_support import BrowserExecutableMissing, browser_executable
from tools.qualify.visible_words import (
    TranscriptObservation,
    TranscriptSegment,
    evaluate_visible_word_surfaces,
    reference_words_from_intervals,
)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        pass


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


def _dom_segments(rows: list[dict[str, object]], frontier: float) -> tuple[TranscriptSegment, ...]:
    result = []
    for index, row in enumerate(rows):
        start = float(row["start"])
        end = (
            float(rows[index + 1]["start"])
            if index + 1 < len(rows)
            else max(start + 0.001, frontier)
        )
        if end > start:
            result.append(TranscriptSegment(start, end, str(row["text"])))
    return tuple(result)


async def _meeting_id(page: Any, before: set[str]) -> str:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        rows = (await _api(page, "/api/meetings")).get("meetings", [])
        created = [
            str(row["id"])
            for row in rows
            if row.get("mode") == "live" and str(row.get("id")) not in before
        ]
        if created:
            return created[0]
        await asyncio.sleep(0.2)
    raise RuntimeError("headed live meeting was not admitted")


async def _run(args: argparse.Namespace) -> dict[str, object]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is unavailable") from exc

    intervals = _read_reference(args.reference, args.seconds)
    references = reference_words_from_intervals(intervals)
    api_observations: list[TranscriptObservation] = []
    dom_observations: list[TranscriptObservation] = []
    decoder_queue_clocks: list[dict[str, object]] = []
    hidden_observations = 0
    total_visibility_observations = 0
    final_status = None
    finalization_status = None

    with tempfile.TemporaryDirectory(prefix="moss-visible-word-browser-") as temporary:
        media = Path(temporary)
        (media / "source.wav").symlink_to(args.system_wav.resolve())
        (media / "source.html").write_text(
            '<title>MOSS Visible Word Audio Source</title>'
            '<audio src="source.wav" controls autoplay></audio>'
        )
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(_QuietHandler, directory=str(media))
        )
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            async with async_playwright() as playwright:
                try:
                    executable = browser_executable(playwright)
                except BrowserExecutableMissing as exc:
                    raise RuntimeError(str(exc)) from exc
                browser = await playwright.chromium.launch(
                    executable_path=str(executable),
                    channel="chromium",
                    headless=False,
                    ignore_default_args=["--mute-audio"],
                    args=[
                        "--use-fake-device-for-media-stream",
                        "--auto-accept-camera-and-microphone-capture",
                        f"--use-file-for-fake-audio-capture={args.microphone_wav.resolve()}",
                        "--auto-select-tab-capture-source-by-title=MOSS Visible Word Audio Source",
                        "--autoplay-policy=no-user-gesture-required",
                    ],
                )
                context = await browser.new_context(
                    ignore_https_errors=urlsplit(args.base).hostname in {"127.0.0.1", "localhost"},
                    viewport={"width": 1440, "height": 1100},
                )
                page = await context.new_page()
                source = await context.new_page()
                try:
                    await source.goto(f"http://127.0.0.1:{server.server_port}/source.html")
                    await source.locator("audio").evaluate("audio => audio.play()")
                    await page.bring_to_front()
                    await page.goto(args.base)
                    await page.locator('[data-auth-state="signed-in"]').wait_for(timeout=30_000)
                    await page.locator('[data-boot="ready"]').wait_for(timeout=30_000)
                    await page.get_by_label("Listening setup", exact=True).select_option("headphones")
                    await page.get_by_role("button", name="Enable microphone", exact=True).click()
                    await page.wait_for_function(
                        'document.querySelector(".capture-status")?.textContent.includes("Microphone connected")'
                    )
                    await page.get_by_role("button", name="Share audio", exact=True).click()
                    start_button = page.get_by_role("button", name="Start capture", exact=True)
                    await start_button.wait_for(timeout=20_000)
                    before = {
                        str(row["id"])
                        for row in (await _api(page, "/api/meetings")).get("meetings", [])
                    }
                    await source.locator("audio").evaluate(
                        "audio => { audio.currentTime = 0; return audio.play(); }"
                    )
                    started = time.monotonic()
                    await start_button.click()
                    meeting_id = await _meeting_id(page, before)
                    next_event = -1
                    last_api: tuple[TranscriptSegment, ...] | None = None
                    last_dom: tuple[TranscriptSegment, ...] | None = None

                    async def observe() -> None:
                        nonlocal next_event, last_api, last_dom, hidden_observations
                        nonlocal total_visibility_observations, final_status, finalization_status
                        snapshot = await _api(page, f"/api/live/sessions/{meeting_id}/snapshot")
                        api_elapsed = time.monotonic() - started
                        api_segments = _snapshot_segments(snapshot)
                        if api_segments != last_api:
                            api_observations.append(
                                TranscriptObservation(api_elapsed, api_segments)
                            )
                            last_api = api_segments
                        dom_rows = await page.locator(".utt").evaluate_all(
                            """nodes => nodes.map(node => {
                              const clock = (node.querySelector('.utt-time')?.textContent || '').trim();
                              const parts = clock.split(':').map(Number);
                              const start = parts.length === 3
                                ? parts[0] * 3600 + parts[1] * 60 + parts[2]
                                : Number.NaN;
                              return {start, text: node.querySelector('.utt-text')?.textContent || ''};
                            }).filter(row => Number.isFinite(row.start))"""
                        )
                        dom_elapsed = time.monotonic() - started
                        dom_segments = _dom_segments(dom_rows, min(dom_elapsed, args.seconds))
                        if dom_segments != last_dom:
                            dom_observations.append(
                                TranscriptObservation(dom_elapsed, dom_segments)
                            )
                            last_dom = dom_segments
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

                    await observe()
                    while time.monotonic() - started < args.seconds:
                        await asyncio.sleep(min(args.poll_seconds, args.seconds - (time.monotonic() - started)))
                        await observe()
                    await page.get_by_role("button", name="Stop and finalize", exact=True).click()
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
                        decoder_queue_clocks=decoder_queue_clocks,
                    )
                    return {
                        "schema": "moss-visible-word-headed.v1",
                        "browser": "headed Chromium",
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
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join()


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
