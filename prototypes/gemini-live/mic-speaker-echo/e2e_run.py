"""One real-product meeting through real Chrome: fake microphone from a wav, real tab capture of a second
tab playing the system wav, one Start click, Stop, clean-up. Observation only (throwaway; P71 harness, trimmed).

    PYTHON prototypes/gemini-live/mic-speaker-echo/e2e_run.py <run> <port> <system.wav> <mic.wav> [seconds] [shot_e,...]

Records, for public/synthetic audio only: every distinct server snapshot (committed rows, grey preview segments
with their lane, engine diagnostics), every distinct set of rows the page shows, screenshots, the saved meeting.
"""
from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "tests" / "phase2"), str(HERE)]
import ledger  # noqa: E402
from browser_support import browser_executable  # noqa: E402

RUN, PORT, SYSTEM_WAV, MIC_WAV = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
LENGTH = float(sys.argv[5]) if len(sys.argv) > 5 else 37.0
SHOT_AT = [float(v) for v in sys.argv[6].split(",")] if len(sys.argv) > 6 else [19.0, 27.0]
assert 18970 <= PORT <= 18979
BASE = f"https://127.0.0.1:{PORT}"
SOURCE_PORT = 18979
SOURCE_TITLE = "R5D Shared Meeting Audio"
PREFIX = 3.0            # the fake microphone file starts at getUserMedia; the tab plays PREFIX s later
OUT = ledger.EV / "runs" / RUN
RATE = 16000

SOURCE_HTML = f"""<!doctype html><meta charset="utf-8"><title>{SOURCE_TITLE}</title>
<body style="font:14px sans-serif"><h1>{SOURCE_TITLE}</h1><audio id="a" controls></audio>
<script>
window.loadLane = async (name) => {{
  const blob = await (await fetch('/' + name)).blob();
  const a = document.getElementById('a');
  a.src = URL.createObjectURL(blob);
  await new Promise(r => a.addEventListener('canplaythrough', r, {{once: true}}));
  return a.duration;
}};
window.playLane = async () => {{ const a = document.getElementById('a'); await a.play(); return Date.now(); }};
</script>"""

INIT = r"""
(() => {
  if (window.__h) return;
  const H = window.__h = { calls: [], creates: [], summaryPosts: 0 };
  const md = navigator.mediaDevices; if (!md) return;
  const gum = md.getUserMedia.bind(md);
  md.getUserMedia = async c => {
    const row = { api: 'getUserMedia', t0: Date.now(), echoCancellation: c && c.audio && c.audio.echoCancellation }; H.calls.push(row);
    const s = await gum(c); row.t1 = Date.now(); row.ok = true; row.settings = s.getAudioTracks()[0]?.getSettings(); return s; };
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, init) => {
    const u = String(url instanceof Request ? url.url : url); const method = (init && init.method) || 'GET';
    if (u.includes('/summary') && method === 'POST') H.summaryPosts += 1;
    const r = await realFetch(url, init);
    try { if (u.endsWith('/api/live/sessions') && method === 'POST') {
      const row = { t: Date.now(), status: r.status }; H.creates.push(row);
      r.clone().json().then(j => { row.id = j.session_id ?? j.id ?? j.session?.session_id ?? null; }).catch(() => {}); } } catch {}
    return r;
  };
})();
"""

ROWS_JS = r"""() => [...document.querySelectorAll('article.utt')].map(r => ({
  lane: r.getAttribute('data-source-lane'), state: r.getAttribute('data-state'),
  guess: r.getAttribute('data-tentative-block') === 'true', continuation: r.getAttribute('data-continuation') === 'true',
  start: +r.getAttribute('data-turn-start'), end: +r.getAttribute('data-turn-end'),
  speaker: (r.querySelector('.utt-speaker-label')?.textContent ?? '').trim(),
  source: (r.querySelector('.utt-source')?.textContent ?? '').trim(),
  metaShown: !!r.querySelector('.utt-meta') && r.querySelector('.utt-meta').checkVisibility() && getComputedStyle(r.querySelector('.utt-speaker') ?? r).visibility !== 'hidden',
  fragments: [...r.querySelectorAll('.utt-content')].map(f => ({ status: f.getAttribute('data-text-status'),
    grey: !!f.querySelector('.prov'), text: (f.querySelector('.utt-text')?.innerText ?? '').trim() })) }))"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/source.html"):
            body = SOURCE_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def now_ms() -> int:
    return int(time.time() * 1000)


def jdump(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False, default=str) + "\n")


def api(page, path):
    return page.evaluate("""async (path) => { try {
        const r = await fetch(path, {credentials: 'same-origin'});
        let j = null; try { j = await r.json(); } catch {}
        return {status: r.status, body: j}; } catch (e) { return {status: -1, error: String(e)}; } }""", path)


def summaries_off(page):
    page.get_by_role("button", name="Settings").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_role("tab", name="Summary", exact=True).wait_for(timeout=10000)
    dlg.get_by_role("tab", name="Summary", exact=True).click()
    dlg.get_by_label("Summary vendor").select_option("off")
    time.sleep(1.2)
    dlg.get_by_role("button", name="Save", exact=True).click()
    time.sleep(0.5)
    if page.get_by_role("dialog").count():
        page.keyboard.press("Escape")
    saved = page.evaluate("JSON.parse(localStorage.getItem('moss.settings.v2'))?.summary ?? null")
    return {k: v for k, v in (saved or {}).items() if k not in ("prompt", "apiKey")}


def with_output(diag: dict) -> float:
    return float(diag.get("cost_usd") or 0) - float(diag.get("metered_output_usd") or 0) + float(
        diag.get("output_cost_estimate_usd") or 0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("snapshots.jsonl", "rows.jsonl", "timeline.jsonl"):
        (OUT / name).write_text("")
    mic = sf.read(str(MIC_WAV), dtype="float64")[0]
    floor = np.random.default_rng(7).normal(0, 10 ** (-63 / 20), int(PREFIX * RATE))
    mic_file = OUT / "mic-prefixed.wav"
    sf.write(str(mic_file), np.clip(np.concatenate([floor, mic]), -1, 1), RATE, subtype="PCM_16")
    handler = functools.partial(_Quiet, directory=str(SYSTEM_WAV.parent))
    source_server = http.server.ThreadingHTTPServer(("127.0.0.1", SOURCE_PORT), handler)
    threading.Thread(target=source_server.serve_forever, daemon=True).start()
    planned = (2 * (15 + 30 + 15 + 45) * ledger.BATCH_PER_S + 2 * 45 * ledger.LIVE_PER_S) * 1.3
    ledger.check(planned, f"e2e {RUN}")
    ev: dict = {"run": RUN, "system_wav": SYSTEM_WAV.name, "mic_wav": MIC_WAV.name, "prefix_s": PREFIX, "planned_usd": planned}

    def append(name, row):
        with (OUT / name).open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with sync_playwright() as p:
        exe = browser_executable(p)
        browser = p.chromium.launch(executable_path=str(exe), headless=True, ignore_default_args=["--mute-audio"], args=[
            "--auto-accept-camera-and-microphone-capture", "--use-fake-device-for-media-stream",
            f"--auto-select-tab-capture-source-by-title={SOURCE_TITLE}", "--autoplay-policy=no-user-gesture-required",
            f"--use-file-for-fake-audio-capture={mic_file}%noloop"])
        ev["browser"] = [str(exe), browser.version]
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        ctx.grant_permissions(["microphone"], origin=BASE)
        source = ctx.new_page()
        source.goto(f"http://127.0.0.1:{SOURCE_PORT}/source.html")
        page = ctx.new_page()
        page.add_init_script(INIT)
        page.goto(BASE + "/", wait_until="networkidle")
        page.bring_to_front()
        page.wait_for_selector('[data-capture-phase="idle"]', timeout=15000)
        time.sleep(1)
        ev["summary_settings"] = summaries_off(page)
        for label in ("System sound", "Microphone"):
            b = page.locator(".capture-sources label.check-row", has_text=label).locator("input")
            if not b.is_checked():
                b.click(); time.sleep(0.3)
        ev["system_lane_seconds"] = source.evaluate(f"loadLane('{SYSTEM_WAV.name}')")
        t_click = now_ms()
        page.get_by_role("button", name="Start recording").click()
        while now_ms() - t_click < 25000:
            if page.evaluate("document.querySelector('[data-capture-phase]')?.getAttribute('data-capture-phase')") == "active":
                break
            time.sleep(0.05)
        else:
            raise SystemExit("Start did not reach active")
        h = page.evaluate("() => window.__h")
        meeting_id = (h["creates"][-1].get("id") if h["creates"] else None) or page.evaluate(
            "JSON.parse(sessionStorage.getItem('lt:session:reattach') ?? 'null')?.sessionId ?? null")
        gum = [c for c in h["calls"] if c.get("ok")]
        ev.update(meeting_id=meeting_id, capture_calls=h["calls"], click_to_active_s=(now_ms() - t_click) / 1000)
        t_zero = gum[-1]["t1"] + PREFIX * 1000
        while now_ms() < t_zero:
            time.sleep(0.005)
        t_zero = source.evaluate("playLane()")
        ev["play_minus_gum_s"] = (t_zero - gum[-1]["t1"]) / 1000

        def e():
            return (now_ms() - t_zero) / 1000

        last_version, last_rows, shots = None, None, set()

        def observe(note=None):
            nonlocal last_version, last_rows
            r = api(page, f"/api/live/sessions/{meeting_id}/snapshot")
            if r["status"] == 200 and r["body"].get("snapshot"):
                sn = r["body"]["snapshot"]; s = sn["session"]
                if s["version"] != last_version or note:
                    last_version = s["version"]
                    append("snapshots.jsonl", {"t": now_ms(), "e": round(e(), 2), "note": note, "version": s["version"],
                        "status": s["status"], "finalization_status": s["finalization_status"],
                        "accepted": s["accepted_samples"], "committed": s["committed_samples"],
                        "canonical_through": s["canonical_through_sample"], "effective": s["effective_transcript"],
                        "provisional": s["provisional"], "pending": sn.get("pending_work_items"),
                        "diag": sn.get("engine_diagnostics")})
            rows = page.evaluate(ROWS_JS)
            key = json.dumps(rows, ensure_ascii=False)
            if key != last_rows or note:
                last_rows = key
                append("rows.jsonl", {"t": now_ms(), "e": round(e(), 2), "note": note, "rows": rows})

        while e() < LENGTH + 1.0:
            observe()
            for at in SHOT_AT:
                if at not in shots and e() >= at:
                    page.screenshot(path=str(OUT / f"shot-e{int(at)}.png")); shots.add(at)
                    observe(f"shot e{int(at)}")
            time.sleep(0.2)
        observe("before Stop")
        page.screenshot(path=str(OUT / "shot-before-stop.png"))
        t_stop = now_ms()
        page.get_by_role("button", name="Stop recording").click()
        ev["stop_e"] = round(e(), 2)
        last_row, meeting, done_at, completed_at = None, None, None, None
        while now_ms() - t_stop < 300_000:
            observe()
            r = api(page, f"/api/meetings/{meeting_id}")
            if r["status"] == 200:
                meeting = r["body"]
                row = (meeting.get("status"), meeting.get("refinement_state"), meeting.get("transcript_version"),
                       meeting.get("refined_version"))
                if row != last_row:
                    append("timeline.jsonl", {"since_stop_s": round((now_ms() - t_stop) / 1000, 1), "meeting": row})
                    print(RUN, "meeting", round((now_ms() - t_stop) / 1000, 1), row, flush=True)
                    if completed_at is None and meeting["status"] != "active":
                        completed_at = now_ms()
                        jdump(OUT / "saved-meeting-live.json", meeting)   # the live transcript as saved at Stop
                        observe("completed (live transcript saved)")
                        page.screenshot(path=str(OUT / "shot-live-saved.png"))
                    last_row = row
                if completed_at and (meeting.get("refinement_state") in ("done", "failed")
                                     or now_ms() - completed_at > 60000):
                    done_at = now_ms(); break
            time.sleep(0.4)
        time.sleep(2.5)
        observe("settled")
        page.screenshot(path=str(OUT / "shot-settled.png"))
        r = api(page, f"/api/meetings/{meeting_id}")
        if r["status"] == 200:
            jdump(OUT / "saved-meeting.json", r["body"])
        snap = api(page, f"/api/live/sessions/{meeting_id}/snapshot")
        diag = ((snap.get("body") or {}).get("snapshot") or {}).get("engine_diagnostics") or {}
        jdump(OUT / "engine.json", diag)
        ev.update(stop_to_done_s=(done_at - t_stop) / 1000 if done_at else None,
                  refinement_state=(meeting or {}).get("refinement_state"),
                  summary_posts=page.evaluate("window.__h.summaryPosts"), engine_with_output_usd=with_output(diag))
        ledger.add(f"e2e {RUN}", with_output(diag) + 0.02 * ev["summary_posts"], basis="engine_diagnostics_with_output",
                   audio_seconds_sent=diag.get("audio_seconds_sent"), calls=diag.get("calls_by_kind"))
        jdump(OUT / "receipt.json", ev)
        print(json.dumps({k: ev[k] for k in ("meeting_id", "click_to_active_s", "play_minus_gum_s", "stop_e",
                                             "stop_to_done_s", "refinement_state", "summary_posts",
                                             "engine_with_output_usd")}, default=str))
        browser.close()
    source_server.shutdown()


main()
