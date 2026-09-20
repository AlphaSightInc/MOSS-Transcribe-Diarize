"""PROTOTYPE: apply real macOS window state and observe Page Visibility.

Question: can an unmodified headed Chromium page enter document.hidden through
native window management?  This module never writes or emulates visibility APIs.
"""
from __future__ import annotations

import asyncio
import json
import plistlib
import subprocess
import tempfile
import time
from pathlib import Path


def chromium_application(executable: Path) -> tuple[str, str | None]:
    app = next((parent for parent in executable.parents if parent.suffix == ".app"), None)
    if app is None:
        return executable.stem, None
    with (app / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    return info.get("CFBundleDisplayName") or info.get("CFBundleName") or app.stem, info.get("CFBundleIdentifier")


class NativeVisibility:
    def __init__(self, page, executable: Path):
        self.page = page
        self.executable = executable
        self.app_name, self.bundle_id = chromium_application(executable)
        self.occluder: subprocess.Popen | None = None
        self.profile: tempfile.TemporaryDirectory | None = None
        self.attempts: list[dict] = []

    async def install_observer(self) -> None:
        await self.page.evaluate(
            """() => {
              window.__mossVisibilityEvents = [{
                type: 'initial', hidden: document.hidden,
                visibilityState: document.visibilityState,
                monotonicMs: performance.now(), wallTime: new Date().toISOString()
              }];
              document.addEventListener('visibilitychange', () => {
                window.__mossVisibilityEvents.push({
                  type: 'visibilitychange', hidden: document.hidden,
                  visibilityState: document.visibilityState,
                  monotonicMs: performance.now(), wallTime: new Date().toISOString()
                });
              });
            }"""
        )

    async def state(self) -> dict:
        return await self.page.evaluate(
            """() => ({hidden: document.hidden,
              visibilityState: document.visibilityState,
              events: window.__mossVisibilityEvents || []})"""
        )

    async def _wait_hidden(self, seconds: float = 4.0) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if await self.page.evaluate("document.hidden"):
                return True
            await asyncio.sleep(0.1)
        return False

    def _osascript(self, source: str) -> subprocess.CompletedProcess:
        return subprocess.run(["osascript", "-e", source], text=True, capture_output=True)

    async def _minimize(self) -> dict:
        source = f'tell application {json.dumps(self.app_name)} to set minimized of every window to true'
        result = await asyncio.to_thread(self._osascript, source)
        hidden = await self._wait_hidden()
        return {"mechanism": "applescript-minimize", "returncode": result.returncode,
                "stderr": result.stderr.strip(), "hidden": hidden, "state": await self.state()}

    async def _restore_minimize(self) -> None:
        source = f'tell application {json.dumps(self.app_name)} to set minimized of every window to false'
        await asyncio.to_thread(self._osascript, source)
        await asyncio.sleep(1)

    async def _occlude(self) -> dict:
        self.profile = tempfile.TemporaryDirectory(prefix="moss-native-occluder-")
        self.occluder = subprocess.Popen(
            [str(self.executable), f"--user-data-dir={self.profile.name}", "--no-first-run",
             "--no-default-browser-check", "--new-window", "--start-fullscreen",
             "data:text/html,<title>MOSS native occluder</title><body style='background:black'></body>"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        hidden = await self._wait_hidden(8.0)
        return {"mechanism": "second-process-fullscreen-occlusion", "pid": self.occluder.pid,
                "hidden": hidden, "state": await self.state()}

    async def _stop_occluder(self) -> None:
        if self.occluder and self.occluder.poll() is None:
            self.occluder.terminate()
            try:
                await asyncio.to_thread(self.occluder.wait, 8)
            except subprocess.TimeoutExpired:
                self.occluder.kill()
                await asyncio.to_thread(self.occluder.wait)
        self.occluder = None
        if self.profile:
            self.profile.cleanup()
            self.profile = None
        await asyncio.sleep(1)

    async def _app_hide(self) -> dict:
        source = (f'tell application "System Events" to set visible of '
                  f'first process whose name is {json.dumps(self.app_name)} to false')
        result = await asyncio.to_thread(self._osascript, source)
        hidden = await self._wait_hidden()
        return {"mechanism": "system-events-app-hide", "requires": "Accessibility TCC",
                "returncode": result.returncode, "stderr": result.stderr.strip(),
                "hidden": hidden, "state": await self.state()}

    async def apply_first_working(self) -> tuple[str | None, list[dict]]:
        for mechanism, apply, restore in (
            ("applescript-minimize", self._minimize, self._restore_minimize),
            ("second-process-fullscreen-occlusion", self._occlude, self._stop_occluder),
            ("system-events-app-hide", self._app_hide, self._restore_app_hide),
        ):
            row = await apply()
            self.attempts.append(row)
            print("NATIVE_VISIBILITY", json.dumps(row), flush=True)
            if row["hidden"]:
                return mechanism, self.attempts
            await restore()
        return None, self.attempts

    async def _restore_app_hide(self) -> None:
        source = f'tell application {json.dumps(self.app_name)} to activate'
        await asyncio.to_thread(self._osascript, source)
        await asyncio.sleep(1)

    async def restore(self, mechanism: str | None) -> None:
        if mechanism == "applescript-minimize":
            await self._restore_minimize()
        elif mechanism == "second-process-fullscreen-occlusion":
            await self._stop_occluder()
        elif mechanism == "system-events-app-hide":
            await self._restore_app_hide()

    async def close(self) -> None:
        await self._stop_occluder()


def manager_name() -> str:
    result = subprocess.run(["launchctl", "managername"], text=True, capture_output=True, check=True)
    return result.stdout.strip()


def relaunch_recipe() -> str:
    return "From the physical Mac console: open -a Terminal; then run the same command in that GUI Terminal."
