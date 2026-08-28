"""One-command falsification probe for Phase-2 URL acquisition policy."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from moss_transcribe_diarize.app.phase2_url import UrlAcquisitionRejected, UrlMediaAcquirer


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name.
        if self.path == "/ok.wav":
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"wave")
            return
        if self.path == "/declared-too-large.wav":
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", "9")
            self.end_headers()
            return
        if self.path == "/stream-too-large.wav":
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.end_headers()
            self.wfile.write(b"12345")
            self.wfile.write(b"6789")
            return
        if self.path == "/cancel.wav":
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.end_headers()
            self.wfile.write(b"partial")
            self.wfile.flush()
            time.sleep(0.3)
            return
        if self.path == "/page":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html></html>")
            return
        if self.path.startswith("/redirect/"):
            step = int(self.path.rsplit("/", 1)[1])
            self.send_response(302)
            self.send_header("Location", "/ok.wav" if step == 0 else f"/redirect/{step - 1}")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_: object) -> None:
        pass


async def rejected(acquirer: UrlMediaAcquirer, url: str, root: Path) -> str:
    try:
        await acquirer.acquire(url, root)
    except UrlAcquisitionRejected as exc:
        return str(exc)
    raise AssertionError("probe expected acquisition rejection")


async def probe(base_url: str, root: Path) -> dict[str, object]:
    direct = UrlMediaAcquirer(max_bytes=8, total_timeout_seconds=1, max_redirects=5)
    accepted = await direct.acquire(f"{base_url}/ok.wav", root / "accepted")
    direct_cancel_task = asyncio.create_task(
        direct.acquire(f"{base_url}/cancel.wav", root / "direct-cancel")
    )
    await asyncio.sleep(0.05)
    direct_cancel_task.cancel()
    direct_cancellation_propagated = False
    try:
        await direct_cancel_task
    except asyncio.CancelledError:
        direct_cancellation_propagated = True

    fake_yt_dlp = root / "fake_yt_dlp.py"
    fake_yt_dlp.write_text(
        "import sys\n"
        "if '--max-downloads' in sys.argv:\n"
        "    raise SystemExit(101)\n"
        "if sys.argv[sys.argv.index('-o') + 1] != '-':\n"
        "    raise SystemExit(102)\n"
        "sys.stdout.buffer.write(b'youtube')\n",
        encoding="utf-8",
    )
    youtube = UrlMediaAcquirer(
        max_bytes=8,
        total_timeout_seconds=1,
        yt_dlp_command=(sys.executable, str(fake_yt_dlp)),
    )
    youtube_path = await youtube.acquire(
        "https://www.youtube.com/watch?v=fixture", root / "youtube"
    )

    oversize_yt_dlp = root / "oversize_yt_dlp.py"
    oversize_yt_dlp.write_text(
        "import sys, time\n"
        "sys.stdout.buffer.write(b'123456789')\n"
        "sys.stdout.buffer.flush()\n"
        "time.sleep(1)\n",
        encoding="utf-8",
    )
    oversize = UrlMediaAcquirer(
        max_bytes=8,
        total_timeout_seconds=1,
        yt_dlp_command=(sys.executable, str(oversize_yt_dlp)),
    )

    descendant_marker = root / "descendant-survived"
    slow_yt_dlp = root / "slow_yt_dlp.py"
    slow_yt_dlp.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', "
        f"\"import time; from pathlib import Path; time.sleep(.3); Path({str(descendant_marker)!r}).write_text('alive')\""
        "])\n"
        "time.sleep(1)\n",
        encoding="utf-8",
    )
    timeout = UrlMediaAcquirer(
        max_bytes=8,
        total_timeout_seconds=0.05,
        yt_dlp_command=(sys.executable, str(slow_yt_dlp)),
    )
    oversize_reason = await rejected(
        oversize, "https://youtu.be/oversize", root / "oversize"
    )
    timeout_reason = await rejected(timeout, "https://youtu.be/fixture", root / "timeout")
    await asyncio.sleep(0.4)

    cancel_marker = root / "cancel-descendant-survived"
    cancel_yt_dlp = root / "cancel_yt_dlp.py"
    cancel_yt_dlp.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', "
        f"\"import time; from pathlib import Path; time.sleep(.3); Path({str(cancel_marker)!r}).write_text('alive')\""
        "])\n"
        "sys.stdout.buffer.write(b'partial')\n"
        "sys.stdout.buffer.flush()\n"
        "time.sleep(1)\n",
        encoding="utf-8",
    )
    cancel_acquirer = UrlMediaAcquirer(
        max_bytes=8,
        total_timeout_seconds=1,
        yt_dlp_command=(sys.executable, str(cancel_yt_dlp)),
    )
    cancel_task = asyncio.create_task(
        cancel_acquirer.acquire("https://youtu.be/cancel", root / "cancel")
    )
    await asyncio.sleep(0.05)
    cancel_task.cancel()
    cancellation_propagated = False
    try:
        await cancel_task
    except asyncio.CancelledError:
        cancellation_propagated = True
    await asyncio.sleep(0.4)

    return {
        "accepted": {"name": accepted.name, "bytes": accepted.read_bytes().decode("ascii")},
        "declared_size": await rejected(
            direct, f"{base_url}/declared-too-large.wav", root / "declared"
        ),
        "streamed_size": await rejected(
            direct, f"{base_url}/stream-too-large.wav", root / "streamed"
        ),
        "direct_cancel": {
            "cancellation_propagated": direct_cancellation_propagated,
            "remaining_files": sorted(
                path.name for path in (root / "direct-cancel").iterdir()
            ),
        },
        "html": await rejected(direct, f"{base_url}/page", root / "html"),
        "redirects": await rejected(direct, f"{base_url}/redirect/5", root / "redirects"),
        "youtube": {
            "name": youtube_path.name,
            "bytes": youtube_path.read_bytes().decode("ascii"),
        },
        "youtube_streamed_size": {
            "rejection": oversize_reason,
            "remaining_files": sorted(path.name for path in (root / "oversize").iterdir()),
        },
        "youtube_timeout": {
            "rejection": timeout_reason,
            "descendant_survived_parent_kill": descendant_marker.exists(),
            "remaining_files": sorted(path.name for path in (root / "timeout").iterdir()),
        },
        "youtube_cancel": {
            "cancellation_propagated": cancellation_propagated,
            "descendant_survived_parent_kill": cancel_marker.exists(),
            "remaining_files": sorted(path.name for path in (root / "cancel").iterdir()),
        },
    }


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="moss-url-prototype-") as directory:
            state = asyncio.run(
                probe(f"http://127.0.0.1:{server.server_port}", Path(directory))
            )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
