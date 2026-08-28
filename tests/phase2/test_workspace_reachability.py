from __future__ import annotations

import html
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

import pytest

from moss_transcribe_diarize.app.phase2 import Account, _workspace_html


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/chromium"),
)


def _chrome() -> Path:
    for candidate in CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    pytest.skip("Chrome/Chromium is required for the workspace reachability regression.")


def _browser_layout(tmp_path: Path, *, width: int, height: int) -> dict[str, object]:
    css = (REPOSITORY_ROOT / "frontend/src/styles/index.css").read_text(encoding="utf-8")
    page = _workspace_html(
        Account("account-a", "person@example.com", "Person", 0),
        [],
        live_enabled=True,
    )
    page = page.replace(
        '<link rel="stylesheet" href="/static/styles.css">',
        f"<style>{css}</style>",
    ).replace(
        '<script type="module" src="/static/app.js"></script>',
        "",
    ).replace(
        '<div id="app"></div>',
        '<div id="app"><div class="app"><div class="main">Live workspace</div></div></div>',
    )
    probe = """
<script>
window.addEventListener('load', () => {
  const sections = Array.from(document.querySelectorAll('[data-workspace-section]'));
  const history = document.querySelector('[data-workspace-section="history"]');
  const app = document.querySelector('[data-live-capture="account"] .app');
  const root = document.scrollingElement;
  const beforeHistoryTop = history.getBoundingClientRect().top;
  history.scrollIntoView({block: 'end'});
  const historyBox = history.getBoundingClientRect();
  const result = {
    order: sections.map(section => section.dataset.workspaceSection),
    topOrder: sections.map(section => section.getBoundingClientRect().top),
    bodyOverflowY: getComputedStyle(document.body).overflowY,
    appHeight: app.getBoundingClientRect().height,
    viewportHeight: window.innerHeight,
    documentScrollHeight: root.scrollHeight,
    documentClientHeight: root.clientHeight,
    beforeHistoryTop,
    scrollTop: root.scrollTop,
    historyVisible: historyBox.top < window.innerHeight && historyBox.bottom > 0
  };
  document.documentElement.dataset.layoutProbe = encodeURIComponent(JSON.stringify(result));
});
</script>
"""
    page = page.replace("</body>", f"{probe}</body>")
    document = tmp_path / f"workspace-{width}x{height}.html"
    document.write_text(page, encoding="utf-8")
    profile = tmp_path / f"chrome-{width}x{height}"
    process = subprocess.Popen(
        [
            str(_chrome()),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--allow-file-access-from-files",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            "--virtual-time-budget=1000",
            "--dump-dom",
            document.as_uri(),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        # Chrome 151 on macOS emits the complete dump but can retain a keychain helper.
        # The DOM marker is authoritative; terminate only after the bounded dump window.
        process.kill()
        stdout, stderr = process.communicate()
    match = re.search(r'data-layout-probe="([^"]+)"', stdout)
    assert match is not None, stderr
    return json.loads(unquote(html.unescape(match.group(1))))


@pytest.mark.parametrize("width,height", [(1280, 720), (390, 844)])
def test_signed_in_workspace_keeps_file_live_history_ordered_and_reachable(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    measured = _browser_layout(tmp_path, width=width, height=height)

    assert measured["order"] == ["file", "live", "history"]
    assert measured["topOrder"] == sorted(measured["topOrder"])
    assert measured["bodyOverflowY"] == "auto"
    assert measured["appHeight"] >= measured["viewportHeight"]
    assert measured["documentScrollHeight"] > measured["documentClientHeight"]
    assert measured["beforeHistoryTop"] > measured["viewportHeight"]
    assert measured["scrollTop"] > 0
    assert measured["historyVisible"] is True
