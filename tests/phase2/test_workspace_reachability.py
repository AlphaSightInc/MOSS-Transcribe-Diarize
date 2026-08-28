from __future__ import annotations

import html
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote

import pytest

from moss_transcribe_diarize.app.phase2 import Account, Meeting, _workspace_html


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
    frontend = REPOSITORY_ROOT / "ProjectResources" / "Frontend"
    shutil.copy2(frontend / "app.js", tmp_path / "app.js")
    shutil.copy2(frontend / "styles.css", tmp_path / "styles.css")
    page = _workspace_html(
        Account("account-a", "person@example.com", "Person", 0),
        [
            Meeting(
                meeting_id="meeting-observe",
                mode="live",
                title="Observed meeting",
                status="active",
                created_at_ms=0,
                transcript=None,
                transcript_version=0,
            )
        ],
        live_enabled=True,
    )
    page = page.replace(
        '<link rel="stylesheet" href="/static/styles.css">',
        '<link rel="stylesheet" href="./styles.css">',
    ).replace(
        '<script type="module" src="/static/app.js"></script>',
        '<script type="module" src="./app.js"></script>',
    )
    fetch_probe = """
<script>
window.__probeRequests = [];
window.fetch = async (input) => {
  const url = String(input);
  window.__probeRequests.push(url);
  const response = (body, status = 200) => new Response(JSON.stringify(body), {
    status,
    headers: {'Content-Type': 'application/json'}
  });
  if (url === '/api/meetings/meeting-observe') {
    return response({
      id: 'meeting-observe', mode: 'live', status: 'active', title: 'Observed meeting',
      created_at_ms: 0, transcript: null, transcript_version: 0
    });
  }
  if (url.includes('/api/live/sessions/meeting-observe/snapshot')) {
    if (url.includes('since_version=0')) {
      return response({
        snapshot: {
          session_id: 'meeting-observe',
          descriptor: {sample_rate: 16000},
          session: {
            status: 'active', version: 1, failure_reason: null,
            finalization_status: 'not_started', label_revision_version: 0,
            identity_snapshot: {canonical_speakers: ['speaker-0001']},
            committed: [{
              span_id: 1, start_sample: 0,
              transcript: '[0][S01]Observed live words[1]', revised_transcript: null
            }],
            provisional: null
          }
        },
        unchanged: false,
        status_line: 'Observer connected'
      });
    }
    return response({snapshot: null, unchanged: true, status_line: 'Observer connected'});
  }
  if (url.includes('/api/live/sessions/meeting-observe/events')) return response({events: []});
  return response({detail: 'not found'}, 404);
};
</script>
"""
    page = page.replace('<script type="module" src="./app.js"></script>', fetch_probe + '<script type="module" src="./app.js"></script>')
    probe = """
<script>
window.addEventListener('load', () => {
  setTimeout(() => document.querySelector('[data-open-meeting="meeting-observe"]').click(), 50);
  setTimeout(() => {
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
      appBoot: app.dataset.boot,
      viewportHeight: window.innerHeight,
      documentScrollHeight: root.scrollHeight,
      documentClientHeight: root.clientHeight,
      beforeHistoryTop,
      scrollTop: root.scrollTop,
      historyVisible: historyBox.top < window.innerHeight && historyBox.bottom > 0,
      observerPhase: document.querySelector('[data-capture-phase]')?.dataset.capturePhase,
      observerMode: document.querySelector('[data-observer-mode]')?.dataset.observerMode,
      enableMicrophoneVisible: Array.from(document.querySelectorAll('button')).some(
        button => button.textContent.trim() === 'Enable microphone'
      ),
      detachVisible: Array.from(document.querySelectorAll('button')).some(
        button => button.textContent.trim() === 'Detach transcript'
      ),
      transcriptVisible: document.querySelector('#tr-body')?.textContent.includes('Observed live words'),
      reattachStored: sessionStorage.getItem('lt:session:reattach'),
      requests: window.__probeRequests
    };
    document.documentElement.dataset.layoutProbe = encodeURIComponent(JSON.stringify(result));
  }, 750);
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
            "--virtual-time-budget=2500",
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
    assert measured["appBoot"] == "ready"
    assert measured["documentScrollHeight"] > measured["documentClientHeight"]
    assert measured["beforeHistoryTop"] > measured["viewportHeight"]
    assert measured["scrollTop"] > 0
    assert measured["historyVisible"] is True
    assert measured["observerPhase"] == "viewing"
    assert measured["observerMode"] == "read-only"
    assert measured["enableMicrophoneVisible"] is False
    assert measured["detachVisible"] is True
    assert measured["transcriptVisible"] is True
    assert measured["reattachStored"] is None
    assert "/api/meetings/meeting-observe" in measured["requests"]
    assert any("/api/live/sessions/meeting-observe/snapshot" in url for url in measured["requests"])
    assert any("/api/live/sessions/meeting-observe/events" in url for url in measured["requests"])
