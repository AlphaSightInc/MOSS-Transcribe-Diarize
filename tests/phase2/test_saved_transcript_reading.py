"""Meetings saved before the text-join rule (r4 F1) read without their join spaces.

They hold one space between every Chinese character ("大 家 好"). The stored row is never
rewritten for it: the clean-up happens where the transcript is served or summarized.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from moss_transcribe_diarize.app.phase2 import (Meeting, _workspace_html, create_phase2_app,
                                             readable_transcript)
from moss_transcribe_diarize.app.transcript_text import without_join_spaces
from tests.phase2.browser_support import require_browser

ROOT = Path(__file__).resolve().parents[2]
RESULT = {"summary": "A grounded result.", "topics": [{"title": "Useful title", "description": "A mechanism."}],
          "details": [], "speaker_background": [], "data_references": []}
USAGE = {"model": "gemini-3.5-flash-lite", "input_tokens": 100, "output_tokens": 25, "cost_usd": 0.0000925}


def row(index, start, speaker_id, speaker, text):
    return {"id": f"seg_{index:04d}", "start": float(start), "end": float(start + 4),
            "speaker_entity_id": speaker_id, "speaker": speaker, "text": text, "source_lane": "system"}


# As saved by the old join: one space between every word, and Gemini's words are single characters.
STORED = {"segments": [
    row(1, 0, "speaker-0001", "Speaker 1", "大 家 好， 今 天 我 们 主 要 讨 论 一 下 第 三 季"),
    row(2, 5, "speaker-0001", "Speaker 1", "度 的 产 品 规 划。 预 算 大 概 30 万 左 右， 用 API 做 测 试。"),
    row(3, 10, "speaker-0002", "Speaker 2", "Yeah. Sounds good to me, right?"),
    row(4, 15, "speaker-0002", "Speaker 2", "오늘 회의를 시작하겠습니다."),
    row(5, 20, "speaker-0001", "Speaker 1", "今日 は 会議 です。 ありがとう ございます。"),
    row(6, 25, "speaker-0001", "Speaker 1", "我们用API做测试，大概30万。"),  # Saved by the new rule.
]}
READ = [
    "大家好，今天我们主要讨论一下第三季",
    "度的产品规划。预算大概 30 万左右，用 API 做测试。",
    "Yeah. Sounds good to me, right?",
    "오늘 회의를 시작하겠습니다.",
    "今日は会議です。ありがとうございます。",
    "我们用API做测试，大概30万。",
]


@pytest.mark.parametrize("stored, read", [
    ("大 家 好， 今 天", "大家好，今天"),
    ("用 API 做 测 试", "用 API 做测试"),          # A space beside a Latin letter is kept as stored.
    ("大 概 30 万 左 右", "大概 30 万左右"),        # ... and beside a digit.
    ("反 кве 说", "反 кве 说"),
    ("好。 OK， 好", "好。 OK，好"),
    ("今日 は 会議 です。", "今日は会議です。"),
    ("오늘 회의를 시작하겠습니다.", "오늘 회의를 시작하겠습니다."),
    ("Yeah. We did, right?", "Yeah. We did, right?"),
    ("大  家", "大  家"),                          # Only a single space is a join space.
    ("大　家 好", "大　家好"),
    ("\U00020bb7 野 家", "\U00020bb7野家"),
    ("我们用API做测试，大概30万。", "我们用API做测试，大概30万。"),
    ("", ""),
])
def test_only_a_single_space_between_two_unspaced_script_characters_is_dropped(stored, read):
    assert without_join_spaces(stored) == read
    assert without_join_spaces(read) == read  # Reading twice changes nothing more.
    assert read.replace(" ", "") == stored.replace(" ", "")  # No character but a space is touched.


def test_saved_spaced_chinese_reads_clean_in_api_and_summary_while_the_row_stays_as_stored(tmp_path):
    calls = []

    async def generate(document, *, model, language, prompt, api_key):
        calls.append(document)
        return RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(STORED, terminal=True)
            return handle.meeting_id

        async def stored_row():
            cursor = await app.state.phase2_store._connection.execute(
                "SELECT document_json FROM meeting_transcripts WHERE meeting_id = ?", (meeting_id,))
            found = await cursor.fetchone()
            await cursor.close()
            return json.loads(found["document_json"])

        meeting_id = client.portal.call(seed)
        opened = client.get(f"/api/meetings/{meeting_id}").json()
        assert [segment["text"] for segment in opened["transcript"]["segments"]] == READ
        # Everything but the text is served as stored; English, Korean and new rows are untouched.
        assert [{**segment, "text": None} for segment in opened["transcript"]["segments"]] == [
            {**segment, "text": None} for segment in STORED["segments"]]
        listed = client.get("/api/meetings").json()["meetings"]
        assert [segment["text"] for segment in listed[0]["transcript"]["segments"]] == READ
        assert client.portal.call(stored_row) == STORED

        # The server summary reads the same text the browser shows.
        response = client.post(f"/api/meetings/{meeting_id}/summary/server", json={
            "source_version": opened["transcript_version"],
            "provider": {"vendor": "gemini", "model": "gemini-3.5-flash-lite", "api_key": "user-key"}})
        assert response.status_code == 200, response.text
        assert [segment["text"] for segment in calls[0]["segments"]] == READ
        assert client.portal.call(stored_row) == STORED

        # Passages are addressed by segment id and speakers by speaker id, never by text.
        corrected = client.put(f"/api/meetings/{meeting_id}/passages/speaker",
                               json={"segment_ids": ["seg_0002"], "speaker_id": "speaker-0002"})
        assert corrected.status_code == 200, corrected.text
        named = client.put(f"/api/meetings/{meeting_id}/speakers/speaker-0001/name",
                           json={"label": "Wei", "save_voiceprint": False})
        assert named.status_code == 200, named.text
        after = client.get(f"/api/meetings/{meeting_id}").json()
        assert [segment["text"] for segment in after["transcript"]["segments"]] == READ
        assert [segment["speaker"] for segment in after["transcript"]["segments"]] == [
            "Wei", "Speaker 2", "Speaker 2", "Speaker 2", "Wei", "Wei"]
        assert after["transcript_version"] == opened["transcript_version"] + 2
        # The edits rewrote the row with its text exactly as it was saved.
        assert [segment["text"] for segment in client.portal.call(stored_row)["segments"]] == [
            segment["text"] for segment in STORED["segments"]]


def test_reading_leaves_other_documents_alone():
    assert readable_transcript(None) is None
    assert readable_transcript({"segments": "broken"}) == {"segments": "broken"}
    english = {"segments": [{"id": "seg_0001", "text": "Yeah. We did."}, {"id": "seg_0002"}, "odd"]}
    read = readable_transcript(english)
    assert read == english and all(a is b for a, b in zip(read["segments"], english["segments"]))
    once = readable_transcript(STORED)
    assert readable_transcript(once) == once
    assert STORED["segments"][0]["text"].startswith("大 家 好")  # The stored document is not mutated.


def test_saved_spaced_chinese_shows_and_exports_without_join_spaces_in_the_browser(tmp_path):
    meeting = Meeting("old", "live", "Planning", "completed", 1, transcript=STORED, transcript_version=1)
    html = _workspace_html(SimpleNamespace(display_name="Review"), [], live_enabled=True)
    first = "大家好，今天我们主要讨论一下第三季度的产品规划。预算大概 30 万左右，用 API 做测试。"
    last = "今日は会議です。ありがとうございます。我们用API做测试，大概30万。"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)

            def route(r):
                path = urlsplit(r.request.url).path
                if path == "/":
                    r.fulfill(body=html, content_type="text/html")
                elif path.startswith(("/static/", "/fonts/")):
                    r.fulfill(path=str(ROOT / "moss_transcribe_diarize/app/frontend_assets"
                                       / path.removeprefix("/static/").lstrip("/")))
                elif path == "/api/meetings":
                    r.fulfill(json={"meetings": [meeting.to_dict()]})
                elif path == "/api/meetings/old":
                    r.fulfill(json=meeting.to_dict())
                else:
                    r.fulfill(json={"summary": None, "voiceprints": [], "data": []})

            page.route("**/*", route)
            page.goto("http://review.test")
            page.locator('[data-open-meeting="old"]').click()
            page.locator("article.utt").first.wait_for()
            shown = page.locator("article.utt .utt-text").all_inner_texts()
            # P75: each durable passage is independently editable within its speaker card.
            assert shown == READ
            assert page.get_by_role("button", name="Edit text", exact=True).count() == len(READ)
            assert page.locator(".history-card-subtitle").inner_text().startswith("大家好，今天我们主要讨论")
            for value, heading in (("txt", "[00:00:00] Speaker 1:\n"), ("md", "## [00:00:00] Speaker 1\n\n")):
                page.locator("#meeting-export-format").select_option(value)
                with page.expect_download() as download:
                    page.locator(".controls-export button").click()
                saved = tmp_path / f"export.{value}"
                download.value.save_as(saved)
                exported = saved.read_text(encoding="utf-8")
                assert exported.startswith(heading + first + "\n\n"), exported
                assert exported.endswith(last)
                assert "大 家" not in exported and "Yeah. Sounds good to me, right?" in exported
        finally:
            browser.close()
