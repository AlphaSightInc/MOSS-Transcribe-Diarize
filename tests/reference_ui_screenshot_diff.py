#!/usr/bin/env python3
"""Measure the shared TranscriptPane against LiveTranscribe at fixed viewports.

Run with a Python environment that has Playwright and Pillow, for example:
  PYENV_VERSION=3.12.12 pyenv exec python tests/reference_ui_screenshot_diff.py \
    --output evidence/phase2/account-ui/screenshot-diff

The probe serves the reference with Vite, opens the real authenticated FastAPI Account origin
over TLS, loads its committed production bundle, opens a durable history Meeting, and captures the
complete TranscriptPane DOM rectangle in both products. It exits nonzero when either settled 2%/1%
threshold is exceeded. The intentionally new Account product shell has separate semantic, layout,
mobile, and accessibility browser contracts; it is neither compared nor masked here.

The exemption set lives in tests/fixtures/reference_ui_screenshot_diff.json. A null reference
selector denotes candidate-only UX; an explicitly optional candidate selector masks nothing
when absent. Existing paired selectors remain required.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.request import urlopen

from PIL import Image, ImageChops
from playwright.sync_api import Browser, Page, sync_playwright
import uvicorn

_REPOSITORY_BOOTSTRAP = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_BOOTSTRAP))

from moss_transcribe_diarize.phase2_browser_evidence import BrowserTimeoutEvidence, wait_for_final_tail
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.phase2 import (
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_FRONTEND = Path("/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend")
DEFAULT_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/reference_ui_screenshot_fixture.json"
DEFAULT_CONFIG = REPOSITORY_ROOT / "tests/fixtures/reference_ui_screenshot_diff.json"
READY_TIMEOUT_SECONDS = 30
def chrome_executable(playwright) -> Path:
    from tests.phase2.browser_support import require_browser
    return require_browser(playwright)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-frontend",
        type=Path,
        default=DEFAULT_REFERENCE_FRONTEND,
        help="Reference frontend source root (default: the charter's LiveTranscribe checkout).",
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "evidence/phase2/account-ui/screenshot-diff",
        help="Directory for screenshots, masks, reference Vite logs, and report.json.",
    )
    parser.add_argument(
        "--diagnostic-region",
        action="append",
        default=[],
        metavar="ID=SELECTOR",
        help=(
            "Non-gating measurement region. The selector must render in both UIs; "
            "the report records its union box and its share of the charter-masked diff. "
            "May be repeated."
        ),
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_vite(frontend_root: Path, port: int, log_path: Path) -> subprocess.Popen[str]:
    vite = frontend_root / "node_modules/.bin/vite"
    if not vite.is_file():
        raise FileNotFoundError(f"Missing Vite executable: {vite}")

    log_handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(vite), "--base", "/", "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=frontend_root,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    process._reference_ui_log_handle = log_handle  # type: ignore[attr-defined]
    return process


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    process._reference_ui_log_handle.close()  # type: ignore[attr-defined]


def wait_for_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Vite exited before serving {url} (exit {process.returncode}).")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError as error:
            last_error = error
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


class _NoSpeech:
    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int):
        del frame, start_sample, end_sample
        return ()


class _NoDecode:
    max_samples = 4_000

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del span, pcm
        return InferenceTranscript("")


class _NoIdentity:
    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        del pcm, transcript
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=base_snapshot,
            relabeled_transcript="",
        )


def _ui_runtime() -> LiveServiceRuntime:
    descriptor = LiveServiceDescriptor(
        source_revision="a" * 40,
        provider_name="account-ui-fidelity",
        provider_revision="test",
        provider_manifest_hash=hash_config({"provider": "account-ui-fidelity"}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"min_speech_samples": 1, "min_silence_samples": 1},
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": 4_000},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=4_000,
            max_queue_depth=4,
            max_retained_samples=16_000,
            max_identity_speakers=2,
            max_events=128,
            hard_cap_samples=4_000,
            max_tape_bytes=32_000,
        ),
        frame_samples=2,
    )
    storage_owner = tempfile.TemporaryDirectory()
    runtime = LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1,
                min_silence_samples=1,
                hard_cap_samples=4_000,
            )
        ),
        speech_provider_factory=_NoSpeech,
        decoder_factory=_NoDecode,
        rolling_decoder_factory=None,
        identity_preparer_factory=_NoIdentity,
        tape_storage_root=storage_owner.name,
    )
    runtime._test_tape_storage_owner = storage_owner
    return runtime


async def _provision_account(database: Path, fixture: list[dict[str, Any]]) -> str:
    store = await Phase2Store.open(database)
    try:
        account, session_id = await store.bootstrap_browser(None)
        handle = await store.workspace(account).create_meeting("file")
        await handle.rename("LiveTranscribe")
        document = {
            "segments": [
                {
                    "id": item.get("segment_id", f"fixture-{index}"),
                    "start": item["start"],
                    "end": item["end"],
                    "speaker": item["speaker"],
                    "text": item["text"],
                }
                for index, item in enumerate(fixture)
            ]
        }
        await handle.record_audio_unavailable()
        await handle.finish_with_transcript(document, "completed")
        return session_id
    finally:
        await store.close()


def _certificate(directory: Path) -> tuple[Path, Path]:
    certificate = directory / "candidate-certificate.pem"
    private_key = directory / "candidate-private-key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return certificate, private_key


def start_candidate_account(
    directory: Path,
    fixture: list[dict[str, Any]],
) -> tuple[uvicorn.Server, threading.Thread, str, str]:
    database = directory / "account.sqlite3"
    session_id = asyncio.run(_provision_account(database, fixture))
    app = create_phase2_app(
        database_path=database,
        live_runtime_factory=_ui_runtime,
        live_helper_lease_seconds=30,
        file_work_root=directory / "file-work",
        meeting_audio_root=directory / "meetings",
    )
    certificate, private_key = _certificate(directory)
    port = unused_local_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="critical",
            ssl_certfile=str(certificate),
            ssl_keyfile=str(private_key),
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline and not server.started:
        if not thread.is_alive():
            raise RuntimeError("candidate Account server exited during startup")
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("candidate Account server did not start")
    return server, thread, f"https://127.0.0.1:{port}", session_id


def stop_candidate_account(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=8)
    if thread.is_alive():
        raise RuntimeError("candidate Account server did not stop")


def install_reference_api_stub(page: Page) -> None:
    page.add_init_script(
        """
        (() => {
          localStorage.clear();
          sessionStorage.clear();
          const responses = {
            // Pinned 6a8d0c1f bootstrap requires health before publishing boot=ready.
            "/api/health": {
              status: "ok",
              calibration_profile: {
                live_refined_overlay_enabled: false,
                live_refined_osf_enabled: false,
                live_refined_insertion_mode: "off"
              }
            },
            "/api/settings": {},
            "/api/devices/input": { devices: [] },
            "/api/devices/live": { microphones: [] },
            "/api/sessions/history": { sessions: [] },
            "/api/fingerprints": { profiles: [] }
          };
          const originalFetch = window.fetch.bind(window);
          window.fetch = async (input, init) => {
            const rawUrl = typeof input === "string" ? input : input.url;
            const path = new URL(rawUrl, window.location.href).pathname;
            if (Object.prototype.hasOwnProperty.call(responses, path)) {
              return new Response(JSON.stringify(responses[path]), {
                status: 200,
                headers: { "Content-Type": "application/json" }
              });
            }
            if (path.startsWith("/api/")) {
              return new Response(JSON.stringify({ error: "fixture endpoint unavailable" }), {
                status: 404,
                headers: { "Content-Type": "application/json" }
              });
            }
            return originalFetch(input, init);
          };
        })();
        """
    )


def prepare_page(page: Page, fixture: list[dict[str, Any]], is_reference: bool) -> dict[str, Any]:
    if is_reference:
        page.wait_for_selector('[data-boot="ready"]')
        page.evaluate(
            """
            async () => {
              const ui = await import("/src/state/ui.ts");
              ui.historyPanelCollapsed.value = true;
              ui.clearToasts();
            }
            """
        )
        page.evaluate(
            """
            async (items) => {
              const session = await import("/src/state/session.ts");
              session.replaceTranscript(items);
              await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            }
            """,
            fixture,
        )
    else:
        page.wait_for_selector('[data-auth-state="signed-in"]')
        page.wait_for_selector('[data-boot="ready"]')
        page.locator("[data-open-meeting]").first.click()
        wait_for_final_tail(page, fixture[-1]["text"])
        # Compare the production bundle's work area, not the Account document's intentional
        # File -> Live -> History vertical composition. This moves already-rendered product
        # state; it does not substitute markup, source modules, or API responses.
        page.evaluate(
            """
            () => {
              const app = document.querySelector("#app > .app");
              if (!app) throw new Error("production Account bundle did not mount");
              document.body.replaceChildren(app);
              document.body.className = "";
              document.documentElement.style.margin = "0";
              document.body.style.margin = "0";
              app.style.position = "fixed";
              app.style.inset = "0";
              app.style.width = "100vw";
              app.style.height = "100vh";
            }
            """
        )
    page.wait_for_selector(".main")
    content = page.locator("#transcript-panel").inner_text()
    required_text = fixture[-1]["text"]
    if required_text not in content:
        raise AssertionError("Injected fixture did not render through the transcript component.")
    return {"fixture_tail_rendered": required_text, "transcript_text": content}


def wait_for_visual_settle(page: Page) -> None:
    page.evaluate(
        """
        async () => {
          await document.fonts.ready;
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }
        """
    )
    # The reference rail's collapsed-state transition is 0.28 s. Screenshot only after it ends.
    page.wait_for_timeout(300)


def selector_box(page: Page, selector: str) -> dict[str, float]:
    box = page.locator(selector).bounding_box()
    if box is None:
        raise AssertionError(f"Required declared exemption selector did not render: {selector}")
    return {key: float(box[key]) for key in ("x", "y", "width", "height")}


def selector_box_within(page: Page, selector: str, root_selector: str) -> dict[str, float]:
    box = selector_box(page, selector)
    root = selector_box(page, root_selector)
    return {
        "x": box["x"] - root["x"],
        "y": box["y"] - root["y"],
        "width": box["width"],
        "height": box["height"],
    }


def selector_boxes_within(page: Page, selector: str, root_selector: str) -> list[dict[str, float]]:
    """All matching boxes, relative to the pane; needed for repeated candidate controls."""
    matches = page.locator(selector)
    count = matches.count()
    if not count:
        return []
    root = selector_box(page, root_selector)
    boxes = []
    for index in range(count):
        box = matches.nth(index).bounding_box()
        if box is None:
            raise AssertionError(f"Declared exemption selector has no box: {selector}")
        boxes.append({
            "x": float(box["x"]) - root["x"],
            "y": float(box["y"]) - root["y"],
            "width": float(box["width"]),
            "height": float(box["height"]),
        })
    return boxes


def union_box(reference: dict[str, float], candidate: dict[str, float]) -> tuple[int, int, int, int]:
    left = int(min(reference["x"], candidate["x"]))
    top = int(min(reference["y"], candidate["y"]))
    right = int(max(reference["x"] + reference["width"], candidate["x"] + candidate["width"]) + 1)
    bottom = int(max(reference["y"] + reference["height"], candidate["y"] + candidate["height"]) + 1)
    return left, top, right, bottom


def parse_diagnostic_regions(raw_regions: list[str]) -> list[tuple[str, str]]:
    regions: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for raw_region in raw_regions:
        region_id, separator, selector = raw_region.partition("=")
        if not separator or not region_id or not selector:
            raise ValueError(
                f"Diagnostic region must use ID=SELECTOR, got {raw_region!r}."
            )
        if region_id in seen_ids:
            raise ValueError(f"Duplicate diagnostic region id: {region_id!r}.")
        seen_ids.add(region_id)
        regions.append((region_id, selector))
    return regions


def apply_exemptions(
    difference: bytearray,
    width: int,
    height: int,
    exemptions: list[dict[str, Any]],
    reference_page: Page,
    candidate_page: Page,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for exemption in exemptions:
        reference_selector = exemption.get("reference_selector")
        candidate_selector = exemption.get("candidate_selector")
        if not isinstance(reference_selector, str) and not isinstance(candidate_selector, str):
            raise ValueError("An exemption needs a reference or candidate selector")
        references = (
            selector_boxes_within(reference_page, reference_selector, "#transcript-panel")
            if isinstance(reference_selector, str) else []
        )
        candidates = (
            selector_boxes_within(candidate_page, candidate_selector, "#transcript-panel")
            if isinstance(candidate_selector, str) else []
        )
        if isinstance(reference_selector, str) and not references:
            raise AssertionError(f"Required declared exemption selector did not render: {reference_selector}")
        if isinstance(candidate_selector, str) and not candidates:
            if reference_selector is None or exemption.get("candidate_optional") is True:
                # D7/D9 is absent, or the D7-conditional tools selector is inactive.
                # Do not hide the reference's ordinary pixels in this case.
                pairs = []
            else:
                raise AssertionError(f"Required declared exemption selector did not render: {candidate_selector}")
        elif references and candidates:
            if len(references) != len(candidates):
                raise AssertionError("Paired exemption selectors rendered different counts")
            pairs = list(zip(references, candidates))
        elif references:
            pairs = [(reference, reference) for reference in references]
        else:
            pairs = [(candidate, candidate) for candidate in candidates]
        masked_boxes = []
        for reference, candidate in pairs:
            left, top, right, bottom = union_box(reference, candidate)
            left, top = max(0, left), max(0, top)
            right, bottom = min(width, right), min(height, bottom)
            for row in range(top, bottom):
                start = row * width + left
                difference[start : row * width + right] = b"\0" * (right - left)
            masked_boxes.append({"left": left, "top": top, "right": right, "bottom": bottom})
        evidence.append(
            {
                "id": exemption["id"],
                "reference_selector": reference_selector,
                "candidate_selector": candidate_selector,
                "reference_box": references[0] if len(references) == 1 else None,
                "candidate_box": candidates[0] if len(candidates) == 1 else None,
                "masked_union_box": masked_boxes[0] if len(masked_boxes) == 1 else None,
                "masked_union_boxes": masked_boxes,
            }
        )
    return evidence


def measure_diagnostic_regions(
    difference: bytearray,
    width: int,
    height: int,
    regions: list[tuple[str, str]],
    reference_page: Page,
    candidate_page: Page,
) -> list[dict[str, Any]]:
    differing_pixels_after_exemptions = sum(difference)
    evidence: list[dict[str, Any]] = []
    for region_id, selector in regions:
        reference = selector_box_within(reference_page, selector, "#transcript-panel")
        candidate = selector_box_within(candidate_page, selector, "#transcript-panel")
        left, top, right, bottom = union_box(reference, candidate)
        left, top = max(0, left), max(0, top)
        right, bottom = min(width, right), min(height, bottom)
        region_pixels = sum(
            difference[row * width + column]
            for row in range(top, bottom)
            for column in range(left, right)
        )
        evidence.append(
            {
                "id": region_id,
                "selector": selector,
                "reference_box": reference,
                "candidate_box": candidate,
                "union_box": {"left": left, "top": top, "right": right, "bottom": bottom},
                "differing_pixels_after_exemptions": region_pixels,
                "percent_of_viewport": region_pixels * 100 / (width * height),
                "percent_of_charter_masked_difference": (
                    region_pixels * 100 / differing_pixels_after_exemptions
                    if differing_pixels_after_exemptions
                    else 0.0
                ),
            }
        )
    return evidence


def largest_component(difference: bytearray, width: int, height: int, connectivity: int) -> int:
    if connectivity != 4:
        raise ValueError(f"Only four-connected regions are supported, got {connectivity}.")
    largest = 0
    for start in range(len(difference)):
        if not difference[start]:
            continue
        difference[start] = 0
        component_size = 0
        pending = deque([start])
        while pending:
            pixel = pending.pop()
            component_size += 1
            row, column = divmod(pixel, width)
            for neighbor in (
                pixel - 1 if column else None,
                pixel + 1 if column + 1 < width else None,
                pixel - width if row else None,
                pixel + width if row + 1 < height else None,
            ):
                if neighbor is not None and difference[neighbor]:
                    difference[neighbor] = 0
                    pending.append(neighbor)
        largest = max(largest, component_size)
    return largest


def compare_viewport(
    reference_path: Path,
    candidate_path: Path,
    mask_path: Path,
    config: dict[str, Any],
    diagnostic_regions: list[tuple[str, str]],
    reference_page: Page,
    candidate_page: Page,
) -> dict[str, Any]:
    reference = Image.open(reference_path).convert("RGB")
    candidate = Image.open(candidate_path).convert("RGB")
    if reference.size != candidate.size:
        raise AssertionError(f"Screenshot sizes differ: {reference.size} != {candidate.size}")

    width, height = reference.size
    raw_difference = ImageChops.difference(reference, candidate).tobytes()
    pixel_channel_tolerance = int(config.get("pixel_channel_tolerance", 0))
    if pixel_channel_tolerance < 0 or pixel_channel_tolerance > 255:
        raise ValueError(
            f"pixel_channel_tolerance must be in [0, 255], got {pixel_channel_tolerance}."
        )
    difference = bytearray(width * height)
    for pixel in range(width * height):
        offset = pixel * 3
        difference[pixel] = int(
            raw_difference[offset] > pixel_channel_tolerance
            or raw_difference[offset + 1] > pixel_channel_tolerance
            or raw_difference[offset + 2] > pixel_channel_tolerance
        )
    raw_differing_pixels = sum(difference)
    exemptions = apply_exemptions(
        difference, width, height, config["exemptions"], reference_page, candidate_page
    )
    differing_pixels = sum(difference)
    diagnostics = measure_diagnostic_regions(
        difference,
        width,
        height,
        diagnostic_regions,
        reference_page,
        candidate_page,
    )
    Image.frombytes("L", (width, height), bytes(value * 255 for value in difference)).save(mask_path)
    largest = largest_component(difference, width, height, config["connectivity"])
    area = width * height
    differing_percent = differing_pixels * 100 / area
    largest_percent = largest * 100 / area
    return {
        "reference_screenshot": reference_path.name,
        "candidate_screenshot": candidate_path.name,
        "difference_mask": mask_path.name,
        "viewport": {"width": width, "height": height},
        "raw_differing_pixels_before_exemptions": raw_differing_pixels,
        "pixel_channel_tolerance": pixel_channel_tolerance,
        "differing_pixels_after_exemptions": differing_pixels,
        "different_pixel_percent": differing_percent,
        "largest_four_connected_region_pixels": largest,
        "largest_four_connected_region_percent": largest_percent,
        "exemptions": exemptions,
        "diagnostic_regions": diagnostics,
        "passed": (
            differing_percent <= config["max_different_pixel_percent"]
            and largest_percent <= config["max_largest_region_percent"]
        ),
    }


def main() -> int:
    args = parse_args()
    fixture = load_json(args.fixture)
    config = load_json(args.config)
    diagnostic_regions = parse_diagnostic_regions(args.diagnostic_region)
    if not isinstance(fixture, list) or not fixture:
        raise ValueError("The screenshot fixture must be a non-empty JSON array.")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    timeout_evidence = BrowserTimeoutEvidence(output, "reference_screenshot")
    reference_port = unused_local_port()
    reference_server = start_vite(args.reference_frontend.resolve(), reference_port, output / "reference-vite.log")
    candidate_origin = "local authenticated Account origin"

    try:
        wait_for_server(f"http://127.0.0.1:{reference_port}/", reference_server)
        with tempfile.TemporaryDirectory(prefix="moss-account-ui-fidelity-") as temp:
            candidate_server, candidate_thread, candidate_url, session_id = start_candidate_account(
                Path(temp), fixture
            )
            try:
                with sync_playwright() as playwright:
                    browser: Browser = playwright.chromium.launch(
                        executable_path=str(chrome_executable(playwright))
                    )
                    try:
                        viewport_results: list[dict[str, Any]] = []
                        for viewport in config["viewports"]:
                            reference_context = browser.new_context(
                                viewport=viewport, device_scale_factor=1
                            )
                            candidate_context = browser.new_context(
                                viewport=viewport,
                                device_scale_factor=1,
                                ignore_https_errors=True,
                            )
                            try:
                                reference_page = timeout_evidence.page(reference_context.new_page(), "reference.prepare")
                                candidate_page = timeout_evidence.page(candidate_context.new_page(), "candidate.prepare")
                                install_reference_api_stub(reference_page)
                                candidate_context.add_cookies(
                                    [
                                        {
                                            "name": SESSION_COOKIE,
                                            "value": session_id,
                                            "url": candidate_url,
                                            "secure": True,
                                            "httpOnly": True,
                                            "sameSite": "Lax",
                                        }
                                    ]
                                )
                                reference_page.goto(
                                    f"http://127.0.0.1:{reference_port}/",
                                    wait_until="networkidle",
                                )
                                candidate_page.goto(candidate_url, wait_until="networkidle")
                                reference_fixture = prepare_page(
                                    reference_page, fixture, is_reference=True
                                )
                                candidate_fixture = prepare_page(
                                    candidate_page, fixture, is_reference=False
                                )
                                wait_for_visual_settle(reference_page)
                                wait_for_visual_settle(candidate_page)
                                wait_for_final_tail(candidate_page, fixture[-1]["text"])
                                label = f"{viewport['width']}x{viewport['height']}"
                                reference_path = output / f"reference-{label}.png"
                                candidate_path = output / f"candidate-{label}.png"
                                mask_path = output / f"difference-mask-{label}.png"
                                reference_page.locator("#transcript-panel").screenshot(
                                    path=str(reference_path)
                                )
                                candidate_page.locator("#transcript-panel").screenshot(
                                    path=str(candidate_path)
                                )
                                result = compare_viewport(
                                    reference_path,
                                    candidate_path,
                                    mask_path,
                                    config,
                                    diagnostic_regions,
                                    reference_page,
                                    candidate_page,
                                )
                                result["fixture"] = {
                                    "reference": reference_fixture,
                                    "candidate": candidate_fixture,
                                }
                                viewport_results.append(result)
                            finally:
                                reference_context.close()
                                candidate_context.close()
                    finally:
                        browser.close()
            finally:
                stop_candidate_account(candidate_server, candidate_thread)
    finally:
        stop_process(reference_server)

    report = {
        "probe": "tests/reference_ui_screenshot_diff.py",
        "reference_frontend": str(args.reference_frontend.resolve()),
        "candidate_product": candidate_origin,
        "fixture": str(args.fixture.resolve()),
        "config": str(args.config.resolve()),
        "thresholds": {
            "max_different_pixel_percent": config["max_different_pixel_percent"],
            "max_largest_region_percent": config["max_largest_region_percent"],
            "pixel_channel_tolerance": config.get("pixel_channel_tolerance", 0),
            "connectivity": config["connectivity"],
        },
        "diagnostic_regions": [
            {"id": region_id, "selector": selector}
            for region_id, selector in diagnostic_regions
        ],
        "viewports": viewport_results,
        "passed": all(result["passed"] for result in viewport_results),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"reference-ui screenshot probe error: {error}", file=sys.stderr)
        raise SystemExit(2)
