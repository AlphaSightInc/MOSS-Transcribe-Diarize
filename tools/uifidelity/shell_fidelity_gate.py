"""Desktop shell fidelity gate: MOSS account workspace vs the LiveTranscribe reference.

The existing tests/reference_ui_screenshot_diff.py gates ONLY #transcript-panel and explicitly
excludes the product shell. This gate covers the shell -- the region the operator called crappy.
Run: .venv/bin/python ui_fidelity.py
"""
import json, subprocess, sys, time, pathlib, socket
from types import SimpleNamespace
from urllib.parse import urlsplit
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from moss_transcribe_diarize.app.phase2 import _workspace_html, Meeting
from tests.phase2.browser_support import browser_executable

VIEWPORTS = [(1440, 900), (1280, 800)]
SEL = [".topbar", ".control-panel", ".transcript-shell", ".history-panel"]

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

SEGS = [{"id": f"s{i}", "start": i*3.0, "end": i*3.0+2.6, "speaker": f"S0{(i%2)+1}",
         "speaker_entity_id": f"spk-{(i%2)+1}", "display_name": f"S0{(i%2)+1}", "state": "final", "text": t}
        for i, t in enumerate(["Thanks for joining - let me start with where the pipeline stands today.",
        "We measured the live path at parity with the file path last week.",
        "That was the blocker for the whole demo, so it is a real milestone.",
        "Agreed. The remaining risk is latency under concurrent sessions.",
        "Four concurrent is the supported capacity; eight degrades but does not fail."])]
meetings = [Meeting(f"demo-{i}", m, t, "completed", i+1, transcript={"segments": SEGS} if i == 0 else None)
            for i, (m, t) in enumerate([("file", "Quarterly pipeline review"), ("live", "Standup - Tuesday"),
            ("file", "Customer call - Acme"), ("live", "Design sync")])]
import time as _t
for _i, _m in enumerate(meetings):
    try: _m.created_at_ms = int(_t.time()*1000) - _i*3600_000
    except Exception: pass
html = _workspace_html(SimpleNamespace(display_name="Open workspace"), meetings, live_enabled=True)

VOICEPRINTS = [{"id": f"vp-{i}", "label": f"Enrolled speaker {i:02d}", "sample_count": 3 + i,
                "compatibility": "ok"} for i in range(1, 15)]

def route(r):
    path = urlsplit(r.request.url).path
    if path == "/": r.fulfill(body=html, content_type="text/html")
    elif path.startswith("/static/"):
        a = ROOT/"moss_transcribe_diarize/app/frontend_assets"/path.removeprefix("/static/")
        r.fulfill(path=str(a)) if a.is_file() else r.fulfill(status=404)
    elif path == "/api/meetings/demo-0": r.fulfill(json=meetings[0].to_dict())
    else: r.fulfill(json={"meetings": [m.to_dict() for m in meetings], "voiceprints": VOICEPRINTS, "summary": None})

def measure(pg):
    out = {"scrollHeight": pg.evaluate("document.documentElement.scrollHeight"),
           "bodyOverflow": pg.evaluate("getComputedStyle(document.body).overflowY")}
    for s in SEL:
        loc = pg.locator(s).first
        bx = loc.bounding_box() if loc.count() else None
        out[s] = {k: round(bx[k]) for k in ("x","y","width","height")} if bx else None
    return out

port = free_port()
oracle = subprocess.Popen([sys.executable, str(ROOT/"tools/uifidelity/reference_oracle.py"),
                           "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)
results, failures = [], []
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=str(browser_executable(p)), args=["--hide-scrollbars"])
        for w, h in VIEWPORTS:
            rp = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            rp.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle"); rp.wait_for_timeout(1500)
            ref = measure(rp); rp.close()
            mp = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            mp.route("**/*", route); mp.goto("http://demo.test")
            mp.locator('[data-history-boot="ready"]').wait_for(timeout=20000)
            mp.locator('[data-open-meeting="demo-0"]').click(); mp.wait_for_timeout(1200)
            moss = measure(mp)
            moss["sectionOrder"] = mp.evaluate(
                "[...document.querySelectorAll('[data-workspace-section]')].map(s=>s.dataset.workspaceSection)")
            # Voiceprints is now a TAB inside the history rail (reference parity). Switching it
            # must not resize the other panes at all, and the section must live inside the rail.
            expanded = None
            toggle = mp.get_by_role("tab", name="Voiceprints", exact=True)
            named = toggle.count()
            if named == 1:
                toggle.click(); mp.wait_for_timeout(800)
                expanded = measure(mp)
                expanded["voiceprintRows"] = mp.locator("[data-voiceprint-id]").count()
                expanded["namedButtons"] = named
                sessions_tab = mp.get_by_role("tab", name="Sessions", exact=True)
                if sessions_tab.count() == 1:
                    sessions_tab.click(); mp.wait_for_timeout(400)
                    toggle.click(); mp.wait_for_timeout(600)
                expanded["rowsAfterRoundTrip"] = mp.locator("[data-voiceprint-id]").count()
                expanded["insideRail"] = mp.evaluate(
                    """() => {const v=document.querySelector('[data-workspace-section="voiceprints"]');
                       const h=document.querySelector('.history-panel');
                       return !!(v && h && (h.contains(v) || v.contains(h)));}""")
            else:
                expanded = {"namedButtons": named}
            mp.close()
            vp = f"{w}x{h}"
            def check(name, ok, detail):
                failures.append(f"{vp} {name}: {detail}") if not ok else None
                print(f"  {'PASS' if ok else 'FAIL'}  {vp} {name} | {detail}")
            check("no-page-scroll", moss["scrollHeight"] <= h,
                  f"moss scrollHeight={moss['scrollHeight']} ref={ref['scrollHeight']} (must be <= {h})")
            check("body-overflow-hidden", moss["bodyOverflow"] == "hidden",
                  f"moss={moss['bodyOverflow']} ref={ref['bodyOverflow']}")
            rh, mh = ref[".history-panel"], moss[".history-panel"]
            check("history-is-right-rail", bool(mh) and mh["x"] > w*0.7,
                  f"moss x={mh['x'] if mh else None} ref x={rh['x'] if rh else None}")
            check("history-above-fold", bool(mh) and mh["y"] < h,
                  f"moss y={mh['y'] if mh else None} ref y={rh['y'] if rh else None}")
            check("history-rail-width", bool(mh) and abs(mh["width"] - rh["width"]) <= 8,
                  f"moss w={mh['width'] if mh else None} ref w={rh['width'] if rh else None}")
            check("section-order", moss["sectionOrder"] == ["file","live","history","voiceprints"],
                  str(moss["sectionOrder"]))
            rt, mt = ref[".topbar"], moss[".topbar"]
            check("topbar-near-top", bool(mt) and mt["y"] <= 120,
                  f"moss y={mt['y'] if mt else None} ref y={rt['y'] if rt else None} (<=120)")
            rs, ms_ = ref[".transcript-shell"], moss[".transcript-shell"]
            check("transcript-fills-height", bool(ms_) and ms_["height"] >= rs["height"] * 0.85,
                  f"moss h={ms_['height'] if ms_ else None} ref h={rs['height']} (>=85% of ref)")
            check("history-fills-height", bool(mh) and mh["height"] >= rh["height"] * 0.85,
                  f"moss h={mh['height'] if mh else None} ref h={rh['height']} (>=85% of ref)")
            check("vp-exactly-one-tab", expanded.get("namedButtons") == 1,
                  f"tabs named 'Voiceprints' = {expanded.get('namedButtons')} (must be 1)")
            if expanded.get("namedButtons") == 1:
                check("vp-inside-history-rail", expanded.get("insideRail") is True,
                      f"voiceprints section nested in .history-panel = {expanded.get('insideRail')}")
                check("vp-rows-render", (expanded.get("voiceprintRows") or 0) >= 10,
                      f"rows={expanded.get('voiceprintRows')}")
                check("vp-survives-rerender", (expanded.get("rowsAfterRoundTrip") or 0) >= 10,
                      f"rows after Voiceprints->Sessions->Voiceprints = {expanded.get('rowsAfterRoundTrip')}")
                check("vp-tab-no-page-scroll", expanded["scrollHeight"] <= h,
                      f"scrollHeight={expanded['scrollHeight']} (<= {h})")
                for nm, sel in (("controls", ".control-panel"), ("transcript", ".transcript-shell")):
                    b4, af = moss[sel], expanded[sel]
                    check(f"vp-tab-no-shift-{nm}",
                          bool(b4) and bool(af) and abs(b4["height"] - af["height"]) <= 2
                          and abs(b4["y"] - af["y"]) <= 2,
                          f"{sel} before y={b4['y'] if b4 else None} h={b4['height'] if b4 else None} "
                          f"-> after y={af['y'] if af else None} h={af['height'] if af else None}")
                hp = expanded[".history-panel"]
                check("vp-rail-still-full-height", bool(hp) and hp["height"] >= ref[".history-panel"]["height"] * 0.85,
                      f"moss h={hp['height'] if hp else None} ref h={ref['.history-panel']['height']}")
            results.append({"viewport": vp, "reference": ref, "moss": moss, "expanded": expanded})
        b.close()
finally:
    oracle.terminate()
report = {"results": results, "failures": failures, "passed": not failures}
pathlib.Path("/tmp/ui-fidelity-report.json").write_text(json.dumps(report, indent=2))
print(json.dumps({"failures": failures, "passed": not failures}, indent=2))
print(("\nGATE PASS" if not failures else f"\nGATE FAIL ({len(failures)})"))
sys.exit(0 if not failures else 1)
