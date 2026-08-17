#!/usr/bin/env python3
"""Measure the Phase-1 UI against the LiveTranscribe reference at fixed viewports.

Run with a Python environment that has Playwright and Pillow, for example:
  PYENV_VERSION=3.12.12 pyenv exec python tests/reference_ui_screenshot_diff.py \
    --output evidence/phase1/r1-reference-ui/screenshot-diff

The probe serves both source trees with their Vite toolchains, injects the same
transcript fixture through each tree's real session-state module, masks only the exemptions
ruled in the Phase-1 charter, and exits nonzero when either charter threshold is exceeded.

The exemption set lives in tests/fixtures/reference_ui_screenshot_diff.json and is not the
probe's to choose: charter §5 rules each one individually, and an exemption whose selector does
not render is an error here rather than a silent pass (see `selector_box`).
"""

from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.request import urlopen

from PIL import Image, ImageChops
from playwright.sync_api import Browser, Page, sync_playwright


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_FRONTEND = Path("/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend")
DEFAULT_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/reference_ui_screenshot_fixture.json"
DEFAULT_CONFIG = REPOSITORY_ROOT / "tests/fixtures/reference_ui_screenshot_diff.json"
READY_TIMEOUT_SECONDS = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-frontend",
        type=Path,
        default=DEFAULT_REFERENCE_FRONTEND,
        help="Reference frontend source root (default: the charter's LiveTranscribe checkout).",
    )
    parser.add_argument(
        "--candidate-frontend",
        type=Path,
        default=REPOSITORY_ROOT / "frontend",
        help="Candidate frontend source root.",
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "evidence/phase1/r1-reference-ui/screenshot-diff",
        help="Directory for screenshots, masks, Vite logs, and report.json.",
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


def install_reference_api_stub(page: Page) -> None:
    page.add_init_script(
        """
        (() => {
          localStorage.clear();
          sessionStorage.clear();
          const responses = {
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
    page.wait_for_selector(".main")
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
        reference = selector_box(reference_page, exemption["reference_selector"])
        candidate = selector_box(candidate_page, exemption["candidate_selector"])
        left, top, right, bottom = union_box(reference, candidate)
        left, top = max(0, left), max(0, top)
        right, bottom = min(width, right), min(height, bottom)
        for row in range(top, bottom):
            start = row * width + left
            difference[start : row * width + right] = b"\0" * (right - left)
        evidence.append(
            {
                "id": exemption["id"],
                "reference_selector": exemption["reference_selector"],
                "candidate_selector": exemption["candidate_selector"],
                "reference_box": reference,
                "candidate_box": candidate,
                "masked_union_box": {"left": left, "top": top, "right": right, "bottom": bottom},
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
        reference = selector_box(reference_page, selector)
        candidate = selector_box(candidate_page, selector)
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
    reference_port, candidate_port = unused_local_port(), unused_local_port()
    reference_server = start_vite(args.reference_frontend.resolve(), reference_port, output / "reference-vite.log")
    candidate_server = start_vite(args.candidate_frontend.resolve(), candidate_port, output / "candidate-vite.log")

    try:
        wait_for_server(f"http://127.0.0.1:{reference_port}/", reference_server)
        wait_for_server(f"http://127.0.0.1:{candidate_port}/", candidate_server)
        with sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch()
            try:
                viewport_results: list[dict[str, Any]] = []
                for viewport in config["viewports"]:
                    reference_context = browser.new_context(viewport=viewport, device_scale_factor=1)
                    candidate_context = browser.new_context(viewport=viewport, device_scale_factor=1)
                    try:
                        reference_page = reference_context.new_page()
                        candidate_page = candidate_context.new_page()
                        install_reference_api_stub(reference_page)
                        install_reference_api_stub(candidate_page)
                        reference_page.goto(f"http://127.0.0.1:{reference_port}/", wait_until="networkidle")
                        candidate_page.goto(f"http://127.0.0.1:{candidate_port}/", wait_until="networkidle")
                        reference_page.wait_for_selector('[data-boot="ready"]')
                        candidate_page.wait_for_selector(".main")
                        reference_fixture = prepare_page(reference_page, fixture, is_reference=True)
                        candidate_fixture = prepare_page(candidate_page, fixture, is_reference=False)
                        wait_for_visual_settle(reference_page)
                        wait_for_visual_settle(candidate_page)
                        label = f"{viewport['width']}x{viewport['height']}"
                        reference_path = output / f"reference-{label}.png"
                        candidate_path = output / f"candidate-{label}.png"
                        mask_path = output / f"difference-mask-{label}.png"
                        reference_page.screenshot(path=str(reference_path))
                        candidate_page.screenshot(path=str(candidate_path))
                        result = compare_viewport(
                            reference_path,
                            candidate_path,
                            mask_path,
                            config,
                            diagnostic_regions,
                            reference_page,
                            candidate_page,
                        )
                        result["fixture"] = {"reference": reference_fixture, "candidate": candidate_fixture}
                        viewport_results.append(result)
                    finally:
                        reference_context.close()
                        candidate_context.close()
            finally:
                browser.close()
    finally:
        stop_process(reference_server)
        stop_process(candidate_server)

    report = {
        "probe": "tests/reference_ui_screenshot_diff.py",
        "reference_frontend": str(args.reference_frontend.resolve()),
        "candidate_frontend": str(args.candidate_frontend.resolve()),
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
