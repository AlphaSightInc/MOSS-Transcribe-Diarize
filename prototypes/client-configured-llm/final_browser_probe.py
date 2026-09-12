"""Production browser/store path, real cross-origin HTTPS fake provider; no audio.

Run: PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/final_browser_probe.py
Question: does the shipped UI call a CORS provider directly and save only the final
result? Falsifiers: a wrong-owner sentinel/provider setting crosses a boundary, or
merely opening history invokes inference. Scratch DB, synthetic transcripts, muted
headless Chrome. Test-only self-signed provider TLS is explicitly NOT trusted-TLS or
deployed qualification. No provider mocking/interception in the browser.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright
from moss_transcribe_diarize.phase2_browser_evidence import BrowserTimeoutEvidence, AsyncEvidencePage
from moss_transcribe_diarize.phase2_acceptance_summary import SummaryProbeProvider, select_external_summary_provider

spec = importlib.util.spec_from_file_location("workspace_bench", ROOT / "prototypes/phase2-account-lifecycle/browser_workspace_probe.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


async def regenerate_summary(page, meeting_id):
    """Await the new POST's attempt, never an asynchronously restored old artifact."""
    async with page.expect_response(lambda response: response.request.method == "POST"
                                    and response.url.endswith(f"/api/meetings/{meeting_id}/summary")) as pending:
        await page.get_by_test_id("final-summary-generate").click()
    response = await pending.value
    if response.status != 200:
        raise RuntimeError(f"Summary attempt POST returned HTTP {response.status}")
    payload = await response.json()
    attempt = payload["attempt_id"]
    await page.wait_for_function("attempt => { const el=document.querySelector('[data-summary-state]'); return el?.dataset.summaryState === 'current' && el.dataset.summaryAttempt === attempt; }", arg=attempt)
    return attempt


async def run(root, chrome_binary=None, timeout_evidence=None):
    evidence_writer = BrowserTimeoutEvidence(timeout_evidence or root, "browser_final_summary-relay")
    import sqlite3
    from moss_transcribe_diarize.app import phase2
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    cert, key = root / "probe.crt", root / "probe.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True)
    moss_writes = []
    provider = SummaryProbeProvider(origin="http://localhost:1", certificate=cert, key=key)
    provider.__enter__()
    relay_provider = SummaryProbeProvider(origin="http://127.0.0.1")
    relay_provider.__enter__()
    calls, preflights = provider.calls, provider.preflights
    endpoint = provider.endpoint("okay")
    evidence = {"muted": True, "sqlite": sqlite3.sqlite_version, "synthetic_transcripts": True, "provider_tls_trust_verified": False, "deployed_qualification": False}
    try:
        async with bench.running(root / "probe.sqlite3", llm_upstreams=json.dumps([{
            "name": "G9 fake upstream", "base_url": relay_provider.endpoint("relay"), "models": ["g9-relay-model"]
        }])) as (app, port):
            origin = f"http://localhost:{port}"
            provider.origin = origin
            async with async_playwright() as p:
                from tests.phase2.browser_support import browser_executable
                browser = await p.chromium.launch(executable_path=chrome_binary or str(browser_executable(p)), headless=True, args=["--mute-audio"])
                try:
                    contexts = [await browser.new_context(ignore_https_errors=True) for _ in range(2)]
                    pages = [AsyncEvidencePage(await c.new_page(), evidence_writer, f"provider-probe.owner-{i}.workspace") for i, c in enumerate(contexts)]
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
                        page.stage = f"provider-probe.owner-{index}.external-configure"
                        await page.get_by_role("button", name=re.compile(r"^Optional AI summaries · ")).click()
                        await select_external_summary_provider(page.get_by_role("region", name="Browser AI settings", exact=True))
                        for label, value in (("Provider HTTPS URL", endpoint), ("Model", f"probe-model-{index}"),
                                             ("API key (optional)", f"probe-secret-{index}"), ("Final-summary prompt", f"probe-prompt-{index}")):
                            await page.get_by_label(label, exact=True).fill(value)
                        await page.get_by_role("button", name="Save on this browser", exact=True).click()
                        page.stage = f"provider-probe.owner-{index}.external-generate"
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
                    # A second G9 scenario: actual browser -> same-origin app -> HTTP fake
                    # upstream. No network interception or mutation of staged host config.
                    page = pages[0]
                    page.stage = "provider-probe.relay"
                    await page.get_by_role("region", name="Meeting history", exact=True).locator(f'[data-open-meeting="{ids[0]}"]').click()
                    region = page.get_by_role("region", name="Browser AI settings", exact=True)
                    if await region.locator("form").count() == 0:
                        await region.get_by_role("button").click()
                    await region.get_by_label("Provider", exact=True).select_option(label="Server relay (tailnet models)")
                    await region.get_by_label("Final-summary prompt", exact=True).fill("G9 relay structural fixture")
                    await region.get_by_role("button", name="Save on this browser", exact=True).click()
                    relay_posts = []
                    page.on("request", lambda request: relay_posts.append(request.url) if request.method == "POST" and "/api/llm/" in request.url else None)
                    await regenerate_summary(page, ids[0])
                    result = await page.evaluate("async id => (await (await fetch('/api/meetings/'+id+'/summary')).json()).summary", ids[0])
                    relay_calls = relay_provider.calls
                    body = json.loads(relay_calls[0]["body"]) if len(relay_calls) == 1 else {}
                    evidence["relay"] = {
                        "checks": {
                            "same_origin_request": relay_posts == [origin + "/api/llm/chat/completions"],
                            "configured_model": body.get("model") == "g9-relay-model",
                            "token_floor": body.get("max_tokens", 0) >= 2048,
                            "owner_transcript_only": "ONLY-OWNER-0-TRANSCRIPT" in str(body) and "ONLY-OWNER-1-TRANSCRIPT" not in str(body),
                            "no_ambient_credentials": len(relay_calls) == 1 and not any(k.lower() in {"cookie", "authorization"} for k in relay_calls[0]["headers"]),
                            "durable_result": result["state"] == "current" and result["document"]["summary"] == "Qualification summary",
                        },
                        "upstream_requests": len(relay_calls),
                    }
                finally:
                    await browser.close()
    finally:
        provider.__exit__()
        relay_provider.__exit__()
    checks = {k: v for k, v in evidence.items() if k not in {"muted", "sqlite", "synthetic_transcripts", "provider_tls_trust_verified", "deployed_qualification", "relay"}}
    evidence["passed"] = sum(v is True for v in checks.values()); evidence["total"] = len(checks)
    from moss_transcribe_diarize.phase2_acceptance_completion import validate_relay_summary_observation
    if evidence["passed"] != evidence["total"] or not validate_relay_summary_observation(evidence["relay"]):
        raise RuntimeError(json.dumps(evidence, indent=2))
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chrome-binary")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-evidence", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="moss-final-browser-probe-") as directory:
        result = asyncio.run(run(Path(directory), args.chrome_binary, args.timeout_evidence))
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output: args.output.write_text(encoded)
    print(encoded)
