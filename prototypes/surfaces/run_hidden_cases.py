"""PROTOTYPE: browser-stress cases 3/15 with genuine macOS hiding.

Run from an Aqua GUI login. The target page is observed, never told, that it is
hidden. Full visibility state and visibilitychange events are retained in results.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.phase2.browser_support import browser_executable  # noqa: E402
from prototypes.surfaces.native_visibility import NativeVisibility, manager_name, relaunch_recipe  # noqa: E402


def load_bench():
    path = ROOT / "prototypes/browser-stress/run.py"
    spec = importlib.util.spec_from_file_location("moss_browser_stress", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


async def native_hidden_case(self, number: int):
    ident = await self.begin()
    await asyncio.sleep(8)
    before = await self.state_at("before-native-hidden")
    native = NativeVisibility(self.page, Path(browser_executable()))
    await native.install_observer()
    mechanism = None
    try:
        mechanism, attempts = await native.apply_first_working()
        if mechanism is None:
            meeting = await self.stop(ident)
            return {"meeting": ident, "attempts": attempts, "visibility_events": (await native.state())["events"],
                    "terminal": meeting["status"], "blocked": "No native mechanism produced document.hidden=true",
                    "ok": False}
        start = time.monotonic()
        samples = []
        for _ in range(60):
            samples.append({"elapsed": time.monotonic() - start, **await native.state()})
            await asyncio.sleep(1)
        end = time.monotonic()
        after = await self.state_at("after-native-hidden")
        cadence = {}
        for lane in ("system", "microphone"):
            times = [row["t"] for row in self.frames if row["status"] == 200 and row["lane"] == lane and start <= row["t"] <= end]
            points = [start, *times, end]
            cadence[lane] = {"frames": len(times), "max_gap_seconds": max(b - a for a, b in zip(points, points[1:]))}
        await native.restore(mechanism)
        await self.page.bring_to_front()
        await asyncio.sleep(2)
        restored = not await self.page.evaluate("document.hidden")
        meeting = await self.stop(ident)
        events = (await native.state())["events"]
        ok = (all(row["hidden"] for row in samples) and end - start >= 60
              and all(row["frames"] > 0 for row in cadence.values())
              and after["transcript_words"] > before["transcript_words"]
              and restored and meeting["status"] == "completed")
        return {"meeting": ident, "mechanism": mechanism, "attempts": attempts,
                "visibility_samples": samples, "visibility_events": events,
                "hidden_seconds": end - start, "cadence": cadence,
                "word_delta": after["transcript_words"] - before["transcript_words"],
                "restored_visible": restored, "terminal": meeting["status"], "ok": ok}
    finally:
        await native.restore(mechanism)
        await native.close()


def main() -> int:
    manager = manager_name()
    print(f"launchctl managername: {manager}", flush=True)
    if manager != "Aqua":
        print("BLOCKED-ON-SESSION: headed Chromium has no Aqua window.", flush=True)
        print(relaunch_recipe(), flush=True)
        return 77
    module = load_bench()
    original = module.Bench.case_live

    async def case_live(self, number):
        if number == 3:
            return await native_hidden_case(self, number)
        return await original(self, number)

    module.Bench.case_live = case_live
    module.Bench.hidden_headed = lambda self: native_hidden_case(self, 15)
    if "--headed" not in sys.argv:
        sys.argv.append("--headed")
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())
