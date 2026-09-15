"""Browser stress for the §6 items verify_workspace.py leaves alone.

History at scale + after reload (and the duplicate-history-node regression), the
stale-asset regression across a deployment change, and tab hidden/backgrounded while a
meeting is on screen.
"""
import json, os, ssl, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.phase2.browser_support import browser_executable

BASE = os.environ.get("MOSS_BASE", "https://127.0.0.1:17861")
CTX = ssl._create_unverified_context()
AUDIO = (Path(__file__).resolve().parents[2]
         / "evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav")
AT_SCALE = 25

results = []
def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{(' | ' + str(detail)[:120]) if detail else ''}")

jar = {}
def api(method, path, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Content-Type": ctype}
    if jar: h["Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
        for hh in r.headers.get_all("Set-Cookie") or []:
            k, _, v = hh.partition("="); jar[k] = v.split(";")[0]
        return r.status, json.loads(r.read() or b"{}")

api("POST", "/api/workspace/bootstrap")

print(f"\n=== creating {AT_SCALE} meetings for the at-scale history check ===")
boundary = "----mossstress"
wav = AUDIO.read_bytes()
made = 0
for i in range(AT_SCALE):
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"scale-{i}.wav\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n").encode() + wav + f"\r\n--{boundary}--\r\n".encode()
    try:
        s, _ = api("POST", "/api/meetings/file", raw=body, ctype=f"multipart/form-data; boundary={boundary}")
        made += s in (200, 201)
    except Exception as e:
        print("   create failed:", type(e).__name__, e); break
print(f"  created {made}/{AT_SCALE}")

cookie_header = "; ".join(f"{k}={v}" for k, v in jar.items())

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=browser_executable(), headless=True)
    ctx = browser.new_context(ignore_https_errors=True)
    ctx.add_cookies([{"name": k, "value": v, "url": BASE} for k, v in jar.items()])
    page = ctx.new_page()
    console = []
    page.on("console", lambda m: console.append(f"{m.type}:{m.text}"[:200]))
    page.on("pageerror", lambda e: console.append(f"pageerror:{e}"[:200]))
    http_bad = []
    page.on("response", lambda r: http_bad.append((r.status, r.url)) if r.status >= 400 else None)
    page.on("requestfailed", lambda r: http_bad.append(("FAILED", r.url)))
    page.goto(BASE, wait_until="networkidle")
    page.locator('[data-history-boot="ready"]').wait_for(timeout=60000)

    print("\n=== history at scale ===")
    page.locator('[aria-label="Meeting history"]').get_by_role("button", name="Refresh", exact=True).click()
    page.wait_for_timeout(2500)
    cards = page.locator(".account-history-panel [data-meeting-card]")
    ids = cards.evaluate_all("els => els.map(e => e.getAttribute('data-meeting-card'))")
    check(f"history renders many meetings ({len(ids)} cards)", len(ids) >= min(made, 10), f"created={made} rendered={len(ids)}")
    check("no duplicate history nodes", len(ids) == len(set(ids)),
          f"{len(ids)-len(set(ids))} duplicate(s)")

    print("\n=== history after reload ===")
    page.reload(wait_until="networkidle")
    page.locator('[data-history-boot="ready"]').wait_for(timeout=60000)
    page.locator('[aria-label="Meeting history"]').get_by_role("button", name="Refresh", exact=True).click()
    page.wait_for_timeout(2500)
    ids2 = page.locator(".account-history-panel [data-meeting-card]").evaluate_all(
        "els => els.map(e => e.getAttribute('data-meeting-card'))")
    check("history survives reload with no duplicates", len(ids2) == len(set(ids2)) and len(ids2) == len(ids),
          f"before={len(ids)} after={len(ids2)} unique_after={len(set(ids2))}")

    print("\n=== stale-asset regression: every asset is content-versioned ===")
    srcs = page.evaluate("""() => [...document.querySelectorAll('script[src],link[rel=stylesheet][href]')]
        .map(e => e.getAttribute('src') || e.getAttribute('href'))""")
    versioned = [s for s in srcs if s and "/static/" in s]
    check("static assets carry a ?v= content hash",
          bool(versioned) and all("?v=" in s for s in versioned),
          f"{[s.split('/')[-1][:46] for s in versioned]}")

    print("\n=== tab hidden / backgrounded while a meeting is on screen ===")
    if ids2:
        page.locator(f'.account-history-panel [data-open-meeting="{ids2[0]}"]').click()
        page.wait_for_timeout(1500)
        before = page.evaluate("() => document.body.innerText.length")
        page.evaluate("""() => { Object.defineProperty(document,'visibilityState',{value:'hidden',configurable:true});
                                 Object.defineProperty(document,'hidden',{value:true,configurable:true});
                                 document.dispatchEvent(new Event('visibilitychange')); }""")
        page.wait_for_timeout(4000)
        page.evaluate("""() => { Object.defineProperty(document,'visibilityState',{value:'visible',configurable:true});
                                 Object.defineProperty(document,'hidden',{value:false,configurable:true});
                                 document.dispatchEvent(new Event('visibilitychange')); }""")
        page.wait_for_timeout(2500)
        after = page.evaluate("() => document.body.innerText.length")
        alive = page.locator('[data-history-boot="ready"]').count() > 0
        check("page survives hide/show and still renders", alive and after > 0, f"text_len {before} -> {after}")
    else:
        check("page survives hide/show and still renders", False, "no meeting to open")

    print("\n=== non-2xx resources seen during the whole pass ===")
    for st, u in http_bad: print(f"    {st}  {u[:130]}")
    if not http_bad: print("    none")
    errs = [c for c in console if c.startswith("pageerror")]
    check("no uncaught JS page errors during the pass", not errs, f"{errs[:3]}")
    check("no failed resource loads during the pass", not http_bad, f"{[(s_,u[:80]) for s_,u in http_bad[:3]]}")
    browser.close()

bad = results.count(False)
print(f"\n  {len(results)-bad}/{len(results)} UI stress checks passed")
sys.exit(1 if bad else 0)
