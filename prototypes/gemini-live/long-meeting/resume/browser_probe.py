"""Real Chrome, actual CaptureClient and worklet, fake devices, local HTTPS only.

No autoplay override: the probe must not assume AudioContext can run without a click.
Server/certificate/store live exclusively under this pane's evidence folder.
"""
import json
import math
import struct
import subprocess
import threading
import time
import wave
from pathlib import Path

import uvicorn
from fastapi.responses import HTMLResponse, FileResponse
from playwright.sync_api import sync_playwright

from run import build_app, ROOT, EV
from protocol import ResumeProtocol

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 18987
URL = f"https://127.0.0.1:{PORT}"
TITLE = "P74 Synthetic Shared Audio"


def main():
    subprocess.run(["/opt/homebrew/bin/node", str(Path(__file__).with_name("build-browser.mjs"))], check=True)
    directory = EV / ("browser-" + time.strftime("%Y%m%d-%H%M%S"))
    app, cookies, engines = build_app(directory)
    ResumeProtocol(app, "S2", time.monotonic_ns)
    with wave.open(str(directory / "fake-microphone.wav"), "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
        handle.writeframes(struct.pack("<16000h", *(int(3000 * math.sin(i * 2 * math.pi * 330 / 16000)) for i in range(16000))) * 30)
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(directory / "tls-key.pem"), "-out", str(directory / "tls-cert.pem"),
        "-days", "1", "-subj", "/CN=127.0.0.1"], check=True, capture_output=True)

    @app.get("/prototype/")
    async def capture_page():
        return HTMLResponse('<!doctype html><title>P74 Capture Resume</title><body style="font:20px sans-serif">'
            '<h1>P74 resume protocol prototype</h1><p id="state"></p><button id="start">Start recording</button> '
            '<button id="resume">Resume recording</button> <button id="stop">Stop recording</button>'
            '<script src="/prototype/resume.js"></script></body>')

    @app.get("/prototype/resume.js")
    async def script(): return FileResponse(EV / "browser-bundle/resume.js", media_type="application/javascript")

    @app.get("/prototype/worklet.js")
    async def worklet(): return FileResponse(ROOT / "frontend/public/worklets/lane-framer.js", media_type="application/javascript")

    @app.get("/prototype/source")
    async def source():
        return HTMLResponse(f'<!doctype html><title>{TITLE}</title><h1>{TITLE}</h1><button id="play">Play synthetic tone</button>'
            '<script>document.getElementById("play").onclick=async()=>{window.a=new AudioContext();'
            'window.o=a.createOscillator();o.frequency.value=440;window.g=a.createGain();g.gain.value=.1;'
            'o.connect(g).connect(a.destination);o.start();await a.resume();};</script>')

    @app.get("/prototype/gesture")
    async def gesture():
        # Executes during navigation, before any Playwright evaluate can grant
        # transient activation. No capture chooser automation in this browser.
        return HTMLResponse('''<!doctype html><title>P74 activation check</title><script>
            window.displayCall={active:navigator.userActivation.isActive};
            navigator.mediaDevices.getDisplayMedia({audio:true,video:true}).then(s=>{
                s.getTracks().forEach(t=>t.stop());window.displayResult={...displayCall,result:'unexpected-success'};
            },e=>window.displayResult={...displayCall,result:e.name,message:e.message});
            </script>''')

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT,
        ssl_keyfile=str(directory / "tls-key.pem"), ssl_certfile=str(directory / "tls-cert.pem"), log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    browser = None
    result = {"evidence": str(directory), "flags": ["fake-device", "fake microphone file", "auto-select named shared tab"],
              "autoplay_override": False}
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        assert server.started, "local server failed to start"
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, headless=True,
                ignore_default_args=["--mute-audio"], args=["--use-fake-device-for-media-stream",
                "--auto-accept-camera-and-microphone-capture",
                f"--auto-select-tab-capture-source-by-title={TITLE}",
                f"--use-file-for-fake-audio-capture={directory / 'fake-microphone.wav'}"])
            result["chrome_version"] = browser.version
            context = browser.new_context(ignore_https_errors=True)
            context.grant_permissions(["microphone"], origin=URL)
            context.add_cookies([{"name": "__Host-moss_session", "value": cookies["a"],
                "domain": "127.0.0.1", "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"}])
            src = context.new_page(); src.goto(URL + "/prototype/source"); src.click("#play")
            page = context.new_page(); page.goto(URL + "/prototype/")
            def wait_state(value):
                try:
                    page.wait_for_function("value => document.querySelector('#state').textContent === value", arg=value, timeout=15000)
                except Exception:
                    result["failure_page"] = page.evaluate("({state:document.querySelector('#state').textContent, log:measurement})")
                    page.screenshot(path=str(directory / "failure.png"))
                    raise
            page.click("#start")
            wait_state("Recording")
            page.wait_for_function("measurement.frames.filter(f=>f.status===200).length >= 12", timeout=15000)
            result["before"] = page.evaluate("measurement")
            sid = page.evaluate("JSON.parse(sessionStorage.getItem('p74-resume-settings')).meetingId")
            result["meeting_id"] = sid
            before_clock = page.evaluate("capture.context.currentTime")
            crash_at = time.monotonic_ns()
            page.reload()
            # Page reload stops the old capture graph. No Stop or Abort request.
            page.wait_for_timeout(1500)
            # Playwright evaluate supplies user activation. Start after its 5 s
            # transient activation expires, then read the stored result.
            page.evaluate("setTimeout(() => noGestureProbe().then(v => window.gestureResult=v), 5500)")
            page.wait_for_function("window.gestureResult !== undefined", timeout=10000)
            result["no_gesture"] = page.evaluate("gestureResult")
            page.screenshot(path=str(directory / "interrupted.png"))
            page.bring_to_front()
            page.click("#resume")
            wait_state("Recording resumed")
            result["time_to_resume_seconds"] = (time.monotonic_ns() - crash_at) / 1e9
            result["old_context_time"] = before_clock
            page.wait_for_function("measurement.frames.filter(f=>f.status===200).length >= 12", timeout=15000)
            result["after"] = page.evaluate("measurement")
            result["stored_after"] = page.evaluate("JSON.parse(sessionStorage.getItem('p74-resume-settings'))")
            page.screenshot(path=str(directory / "resumed.png"))
            page.click("#stop")
            wait_state("Completed")
            result["meeting"] = page.evaluate("async id => (await (await fetch('/api/meetings/' + id)).json())", sid)
            result["snapshot"] = page.evaluate("async id => (await (await fetch('/api/live/sessions/' + id + '/snapshot')).json())", sid)
            result["final_client_state"] = page.evaluate("measurement")
            browser.close(); browser = None
            # Separate stock activation check: auto-select-tab-capture bypasses
            # activation in Chrome automation, so it cannot establish this fact.
            strict = p.chromium.launch(executable_path=CHROME, headless=True,
                args=["--use-fake-device-for-media-stream"])
            ctx = strict.new_context(ignore_https_errors=True)
            tab = ctx.new_page(); tab.goto(URL + "/prototype/gesture")
            try:
                tab.wait_for_function("window.displayResult !== undefined", timeout=3000)
                result["display_without_gesture_no_autoselect"] = tab.evaluate("displayResult")
            except Exception:
                result["display_without_gesture_no_autoselect"] = tab.evaluate("({...displayCall,result:'UNMEASURED: no reply in 3 s'})")
            strict.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        result["local_server_stopped"] = not thread.is_alive()
        (directory / "result.json").write_text(json.dumps(result, indent=2))
        (EV / "BROWSER-LATEST.txt").write_text(str(directory) + "\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__": main()
