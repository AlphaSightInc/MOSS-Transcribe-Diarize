"""Production browser/store path, real cross-origin HTTPS fake provider; no audio.

Run: PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/final_browser_probe.py
Question: does the shipped UI call a CORS provider directly and save only the final
result? Falsifiers: a wrong-owner sentinel/provider setting crosses a boundary, or
merely opening history invokes inference. Scratch DB, synthetic transcripts, muted
headless Chrome. Test-only self-signed provider TLS is explicitly NOT trusted-TLS or
deployed qualification. No provider mocking/interception in the browser.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright
from moss_transcribe_diarize.phase2_acceptance_summary import SummaryProbeProvider

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workspace_bench", ROOT / "prototypes/phase2-account-lifecycle/browser_workspace_probe.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


async def run(root):
    import sqlite3
    from moss_transcribe_diarize.app import phase2
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    cert, key = root / "probe.crt", root / "probe.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True)
    moss_writes = []
    provider = SummaryProbeProvider(origin="http://localhost:1", certificate=cert, key=key)
    provider.__enter__()
    calls, preflights = provider.calls, provider.preflights
    endpoint = provider.endpoint("okay")
    evidence = {"muted": True, "sqlite": sqlite3.sqlite_version, "synthetic_transcripts": True, "provider_tls_trust_verified": False, "deployed_qualification": False}
    try:
        async with bench.running(root / "probe.sqlite3") as (app, port):
            origin = f"http://localhost:{port}"
            provider.origin = origin
            async with async_playwright() as p:
                browser = await p.chromium.launch(channel="chrome", headless=True, args=["--mute-audio"])
                try:
                    contexts = [await browser.new_context(ignore_https_errors=True) for _ in range(2)]
                    pages = [await c.new_page() for c in contexts]
                    ids, owners = [], []
                    for index, page in enumerate(pages):
                        page.on("request", lambda request: moss_writes.append(request.post_data or "") if request.url.startswith(origin + "/api/") and request.method != "GET" else None)
                        owners.append(await bench.open_workspace(page, origin))
                        cookie = next(c["value"] for c in await contexts[index].cookies() if c["name"] == phase2.SESSION_COOKIE)
                        account = await app.state.phase2_store.account_for_session(cookie)
                        handle = await app.state.phase2_store.workspace(account).create_meeting("file")
                        await handle.commit_transcript({"segments": [{"start": 0, "end": 4, "speaker": "Alex", "text": f"ONLY-OWNER-{index}-TRANSCRIPT"}]}, terminal=True)
                        ids.append(handle.meeting_id)
                        await page.locator('[data-history-boot="ready"]').wait_for()
                        await page.get_by_role("button", name="Refresh", exact=True).click()
                        await page.locator(f'[data-open-meeting="{handle.meeting_id}"]').click()
                        await page.get_by_test_id("final-summary-generate").wait_for()
                    evidence["history_causes_zero_provider_requests"] = len(calls) == 0
                    for index, page in enumerate(pages):
                        await page.get_by_role("button", name="Optional AI summaries · off", exact=True).click()
                        for label, value in (("Provider HTTPS URL", endpoint), ("Model", f"probe-model-{index}"),
                                             ("API key (optional)", f"probe-secret-{index}"), ("Final-summary prompt", f"probe-prompt-{index}")):
                            await page.get_by_label(label, exact=True).fill(value)
                        await page.get_by_role("button", name="Save on this browser", exact=True).click()
                        await page.get_by_test_id("final-summary-generate").click()
                        await page.locator('[data-summary-state="current"]').wait_for(timeout=15000)
                    evidence["real_preflight_and_post"] = len(preflights) == len(calls) == 2
                    evidence["separate_payloads"] = all(f"ONLY-OWNER-{i}-TRANSCRIPT".encode() in call["body"] and f"ONLY-OWNER-{1-i}-TRANSCRIPT".encode() not in call["body"] for i, call in enumerate(calls))
                    evidence["no_owner_meeting_ids_or_ambient_credentials"] = all(
                        not any(value.encode() in call["body"] for value in [*owners, *ids]) and "Cookie" not in call["headers"] and "Referer" not in call["headers"] for call in calls)
                    writes = "\n".join(moss_writes)
                    evidence["settings_never_sent_to_moss"] = not any(value in writes for value in [endpoint, "probe-model-", "probe-secret-", "probe-prompt-"])
                    foreign = await pages[1].evaluate("async id => (await fetch('/api/meetings/'+id+'/summary')).status", ids[0])
                    evidence["foreign_result_404"] = foreign == 404
                    for page in pages:
                        await page.reload()
                        await page.locator('[data-history-boot="ready"]').wait_for()
                    evidence["reload_does_not_call_provider"] = len(calls) == 2
                    cursor = await app.state.phase2_store._connection.execute("SELECT state,document_json,provenance_json FROM llm_artifacts")
                    rows = await cursor.fetchall(); await cursor.close()
                    evidence["two_durable_results_no_provider_metadata"] = len(rows) == 2 and all(row["state"] == "current" and set(json.loads(row["provenance_json"])) == {"attempt_id", "source_version", "artifact_version", "error_code"} for row in rows)
                finally:
                    await browser.close()
    finally:
        provider.__exit__()
    checks = {k: v for k, v in evidence.items() if k not in {"muted", "sqlite", "synthetic_transcripts", "provider_tls_trust_verified", "deployed_qualification"}}
    evidence["passed"] = sum(v is True for v in checks.values()); evidence["total"] = len(checks)
    print(json.dumps(evidence, indent=2))
    if evidence["passed"] != evidence["total"]: raise SystemExit(1)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="moss-final-browser-probe-") as directory:
        asyncio.run(run(Path(directory)))
