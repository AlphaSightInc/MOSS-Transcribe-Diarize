"""A renamed speaker reads under its new name in the saved summary, at once, with no new summary.

The real server (in-process, with a counting stand-in for the model) answers a real Chromium
running the built bundle: the summary is generated once while the speaker is "Speaker 1", then the
speaker is renamed twice through the naming dialog. Needs the bundle built from this source.
"""
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from moss_transcribe_diarize.app.phase2 import _workspace_html, create_phase2_app
from tests.phase2.browser_support import require_browser

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = {"vendor": "gemini", "model": "gemini-3.5-flash-lite", "api_key": "user-key"}
USAGE = {"model": "gemini-3.5-flash-lite", "input_tokens": 100, "output_tokens": 25, "cost_usd": 0.0000925}
TRANSCRIPT = {"segments": [
    {"id": "seg_0001", "start": 0.0, "end": 4.0, "speaker_entity_id": "speaker-0001", "speaker": "Speaker 1",
     "source_lane": "system", "text": "Shall we start with the budget?"},
    {"id": "seg_0002", "start": 4.0, "end": 8.0, "speaker_entity_id": "speaker-0010", "speaker": "Speaker 10",
     "source_lane": "system", "text": "Yes, thirty thousand is the plan."},
]}
# What a model writes: the names it was given, verbatim (252 of 252 mentions in the recorded
# summaries under prototypes/gemini-live/live-summary).
SUMMARY = {"summary": "Speaker 1 asked Speaker 10 about the budget.",
           "topics": [{"title": "Budget", "description": "Speaker 10 told Speaker 1 the plan is thirty thousand."}],
           "details": [{"title": "Speaker 1 opens", "description": "Speaker 1 starts with the budget.",
                        "timestamp": "00:00:00"}],
           "speaker_background": ["Speaker 1: chair", "Speaker 10: finance"], "data_references": []}


def test_a_renamed_speaker_reads_under_the_new_name_in_summary_and_markdown_without_a_new_summary(tmp_path):
    generated = []

    async def generate(document, *, model, language, prompt, api_key):
        generated.append([row["speaker"] for row in document["segments"]])
        return SUMMARY, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    html = _workspace_html(SimpleNamespace(display_name="Review"), [], live_enabled=True)
    with TestClient(app, base_url="https://moss.test") as client, sync_playwright() as p:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("live")
            await handle.finish_with_transcript(TRANSCRIPT, "completed")
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        saved = client.post(f"/api/meetings/{meeting_id}/summary/server",
                            json={"source_version": 1, "provider": PROVIDER})
        assert saved.status_code == 200, saved.text
        assert generated == [["Speaker 1", "Speaker 10"]]

        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
            requests = []

            def route(r):
                path = urlsplit(r.request.url).path
                if path == "/":
                    r.fulfill(body=html, content_type="text/html")
                elif path.startswith(("/static/", "/fonts/")):
                    r.fulfill(path=str(ROOT / "moss_transcribe_diarize/app/frontend_assets"
                                       / path.removeprefix("/static/").lstrip("/")))
                else:
                    requests.append((r.request.method, path))
                    answer = client.request(r.request.method, path, content=r.request.post_data_buffer,
                                            headers={"Content-Type": "application/json"})
                    r.fulfill(status=answer.status_code, body=answer.content,
                              content_type=answer.headers.get("content-type", "application/json"))

            page.route("**/*", route)
            page.goto("http://review.test")
            page.locator(f'[data-open-meeting="{meeting_id}"]').click()
            page.locator("article.utt").first.wait_for()
            summary = page.locator(".summary-content")

            def rename(current, name):
                page.get_by_role("tab", name="Transcript", exact=True).click()
                page.locator(".utt-speaker", has_text=current).first.click()
                page.locator("#speaker-name-input").fill(name)
                page.locator("dialog .sp-voiceprint input").uncheck()
                page.get_by_role("button", name="Save name", exact=True).click()
                expect(page.locator("dialog")).to_have_count(0)
                page.get_by_role("tab", name="Summary", exact=True).click()

            def markdown(name):
                page.locator("#meeting-export-format").select_option("md")
                with page.expect_download() as download:
                    page.locator(".controls-export button").click()
                target = tmp_path / name
                download.value.save_as(target)
                return target.read_text(encoding="utf-8")

            page.get_by_role("tab", name="Summary", exact=True).click()
            expect(summary).to_contain_text("Speaker 1 asked Speaker 10 about the budget.")

            rename("Speaker 1", "Alice")
            expect(summary).to_contain_text("Alice asked Speaker 10 about the budget.")
            expect(summary).to_contain_text("Speaker 10 told Alice the plan is thirty thousand.")
            expect(summary).to_contain_text("00:00:00 · Alice opens")
            expect(summary).to_contain_text("Alice: chair")
            expect(summary).to_contain_text("Speaker 10: finance")
            exported = markdown("first.md")
            assert exported.startswith("# Summary\n\nAlice asked Speaker 10 about the budget.\n\n"), exported
            assert "- Alice: chair\n- Speaker 10: finance" in exported
            assert "## [00:00:00] Alice\n\nShall we start with the budget?" in exported
            assert "Speaker 1 " not in exported and "Speaker 1:" not in exported

            # A second rename of the same speaker, to a Chinese name (Alice -> 王芳).
            rename("Alice", "王芳")
            expect(summary).to_contain_text("王芳 asked Speaker 10 about the budget.")
            expect(summary).to_contain_text("王芳: chair")
            expect(summary).not_to_contain_text("Alice")
            exported = markdown("second.md")
            assert exported.startswith("# Summary\n\n王芳 asked Speaker 10 about the budget.\n\n"), exported
            assert "Alice" not in exported and "## [00:00:00] 王芳\n\n" in exported
        finally:
            browser.close()

        # Two renames, no summary request from the page and no second generation.
        assert ("PUT", f"/api/meetings/{meeting_id}/speakers/speaker-0001/name") in requests
        assert [entry for entry in requests if "/summary" in entry[1] and entry[0] != "GET"] == []
        assert generated == [["Speaker 1", "Speaker 10"]]
        stored = client.get(f"/api/meetings/{meeting_id}/summary").json()["summary"]
        assert stored["document"] == SUMMARY
        assert stored["speaker_names"] == {"speaker-0001": "Speaker 1", "speaker-0010": "Speaker 10"}
