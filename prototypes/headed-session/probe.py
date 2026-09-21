"""THROWAWAY headed-session capability probe.

One command:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \\
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \\
  prototypes/headed-session/probe.py --output evidence/round4/headed-session/browser-probe.json

It launches exactly as tools.qualify.visible_word_headed does: headed Chromium and
only --mute-audio.  It serves a loopback-only static page, then prints the whole
observable browser state.  This answers only whether this launchd session can make
and render a headed browser; it is not acoustic or decoder qualification.
"""
from __future__ import annotations

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
from typing import Sequence

from tests.phase2.browser_support import browser_executable
from tools.qualify.visible_word_headed import _chromium_args


class _Page(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name.
        body = b"<!doctype html><main data-headed-session-probe='ready'>headed DOM</main>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


async def _probe(base: str) -> dict[str, object]:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        executable = browser_executable(playwright)
        browser = await playwright.chromium.launch(
            executable_path=str(executable),
            channel="chromium",
            headless=False,
            args=_chromium_args(),
        )
        context = await browser.new_context(viewport={"width": 800, "height": 600})
        page = await context.new_page()
        try:
            response = await page.goto(base, wait_until="domcontentloaded")
            dom = await page.evaluate(
                """() => ({
                  marker: document.querySelector('[data-headed-session-probe]')?.textContent,
                  outer_html_length: document.documentElement.outerHTML.length,
                  visibility_state: document.visibilityState,
                  hidden: document.hidden
                })"""
            )
            return {
                "managername": subprocess.check_output(
                    ["launchctl", "managername"], text=True
                ).strip(),
                "executable": str(executable),
                "headless": False,
                "chromium_args": _chromium_args(),
                "navigation_http_status": None if response is None else response.status,
                "browser_version": browser.version,
                "dom": dom,
            }
        finally:
            await context.close()
            await browser.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output must not already exist")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Page)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = asyncio.run(_probe(f"http://127.0.0.1:{server.server_port}/"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
