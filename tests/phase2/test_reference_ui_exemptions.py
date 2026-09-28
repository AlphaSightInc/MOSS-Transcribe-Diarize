"""G10 fixture controls through the production screenshot comparator."""

import importlib.util
from copy import deepcopy
from pathlib import Path

from PIL import Image
import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "g10_reference_diff", ROOT / "tests/reference_ui_screenshot_diff.py"
)
DIFF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIFF)


class Locator:
    def __init__(self, boxes):
        self.boxes = boxes

    def count(self):
        return len(self.boxes)

    def nth(self, index):
        return Locator([self.boxes[index]])

    def bounding_box(self):
        if len(self.boxes) != 1:
            raise AssertionError("expected one DOM box")
        return self.boxes[0]


class Page:
    def __init__(self, boxes):
        self.boxes = {"#transcript-panel": [(0, 0, 20, 20)], **boxes}

    def locator(self, selector):
        return Locator([
            {"x": x, "y": y, "width": width, "height": height}
            for x, y, width, height in self.boxes.get(selector, [])
        ])


def test_fixture_names_only_decision_scoped_exemptions():
    config = DIFF.load_json(ROOT / "tests/fixtures/reference_ui_screenshot_diff.json")
    assert config["max_different_pixel_percent"] == 2.0
    assert config["max_largest_region_percent"] == 1.0
    assert [item["id"] for item in config["exemptions"]] == [
        "transcript-summary-toggle",
        "d7-review-banner",
        "d7-uncertain-legend-chip",
        "d7-uncertain-speaker-label",
        "d9-u1-inline-reassign",
        "d7-shifted-transcript-tools",
    ]


def test_q5_baseline_exempts_only_reworked_cards_and_settled_labels():
    config = DIFF.load_json(ROOT / "tests/fixtures/reference_ui_screenshot_diff_q5.json")
    old = DIFF.load_json(ROOT / "tests/fixtures/reference_ui_screenshot_diff.json")
    assert config["max_different_pixel_percent"] == old["max_different_pixel_percent"] == 2.0
    assert config["max_largest_region_percent"] == old["max_largest_region_percent"] == 1.0
    assert config["viewports"] == old["viewports"]
    assert config["exemptions"][:-2] == old["exemptions"]
    assert config["exemptions"][-2:] == [
        {"id": "q5-settled-speaker-labels", "reference_selector": ".legend-chip",
         "candidate_selector": ".legend-chip"},
        {"id": "q5-transcript-cards", "reference_selector": ".utt",
         "candidate_selector": ".transcript-card"},
    ]
    assert config["require_masked_card_content"] is True


def test_q5_masked_cards_reject_wrong_label_and_passage_text():
    fixture = DIFF.load_json(ROOT / "tests/fixtures/reference_ui_screenshot_fixture.json")
    labels = ["Speaker 1", "Speaker 2", "Speaker 1"]
    cards = [
        {"speaker_label": label, "speaker_label_visible": True, "passages": [item["text"]],
         "segments": [{key: item[key] for key in ("start", "end", "text")}]}
        for label, item in zip(labels, fixture)
    ]
    chips = ["Speaker 1", "Speaker 2"]
    assert DIFF.validate_q5_card_content(cards, chips, fixture) == {"cards": 3, "passages": 3, "chips": 2}
    wrong_label = deepcopy(cards)
    wrong_label[1]["speaker_label"] = "Wrong Person XYZ"
    with pytest.raises(AssertionError, match="speaker label"):
        DIFF.validate_q5_card_content(wrong_label, chips, fixture)
    wrong_text = deepcopy(cards)
    wrong_text[2]["passages"] = ["Wrong passage"]
    with pytest.raises(AssertionError, match="passage text"):
        DIFF.validate_q5_card_content(wrong_text, chips, fixture)
    wrong_chip = ["Wrong Person XYZ", "Speaker 2"]
    with pytest.raises(AssertionError, match="legend chip"):
        DIFF.validate_q5_card_content(cards, wrong_chip, fixture)
    hidden_header = deepcopy(cards)
    hidden_header[0]["speaker_label_visible"] = False  # .utt-meta { display: none }
    with pytest.raises(AssertionError, match="speaker label is hidden"):
        DIFF.validate_q5_card_content(hidden_header, chips, fixture)


def test_q5_masked_cards_match_interleaved_named_speaker_segments_once():
    fixture = [
        {"start": 0.0, "end": 2.0, "text": "First remote turn", "speaker": "Alex"},
        {"start": 2.1, "end": 2.4, "text": "Short mic turn", "speaker": "S02"},
        {"start": 2.5, "end": 4.0, "text": "Second remote turn", "speaker": "Alex"},
    ]
    cards = [
        {"speaker_label": "Alex", "speaker_label_visible": True,
         "passages": ["First remote turn", "Second remote turn"],
         "segments": [{key: fixture[index][key] for key in ("start", "end", "text")}
                      for index in (0, 2)]},
        {"speaker_label": "Speaker 1", "speaker_label_visible": True,
         "passages": ["Short mic turn"],
         "segments": [{key: fixture[1][key] for key in ("start", "end", "text")}]},
    ]
    assert DIFF.validate_q5_card_content(cards, ["Alex", "Speaker 1"], fixture) == {
        "cards": 2, "passages": 3, "chips": 2,
    }
    duplicate = deepcopy(cards)
    duplicate[0]["segments"].append(duplicate[0]["segments"][0])
    with pytest.raises(AssertionError, match="more than once"):
        DIFF.validate_q5_card_content(duplicate, ["Alex", "Speaker 1"], fixture)


def test_q5_css_hidden_header_and_wrong_legend_fail_in_browser():
    fixture = [{"start": 0.0, "end": 1.0, "text": "Fixture speech", "speaker": "S01"}]
    html = (
        '<div class="legend-chip"><span class="legend-chip-name">Speaker 1</span></div>'
        '<article class="transcript-card" data-segments="'
        '[{&quot;start&quot;:0.0,&quot;end&quot;:1.0,&quot;text&quot;:&quot;Fixture speech&quot;}]">'
        '<div class="utt-meta"><span class="utt-speaker-label">Speaker 1</span></div>'
        '<div class="utt-content"><p class="utt-text">Fixture speech</p></div></article>'
    )
    with DIFF.sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(DIFF.chrome_executable(playwright)), headless=True
        )
        try:
            page = browser.new_page()
            page.set_content(html)
            def checked_content():
                return DIFF.validate_q5_card_content(
                    DIFF.capture_q5_card_content(page), DIFF.capture_q5_legend_content(page), fixture
                )
            assert checked_content() == {"cards": 1, "passages": 1, "chips": 1}
            page.add_style_tag(content=".transcript-card .utt-meta {display:none!important}")
            with pytest.raises(AssertionError, match="speaker label is hidden"):
                checked_content()
            page.add_style_tag(content=".transcript-card .utt-meta {display:block!important}")
            page.locator(".legend-chip-name").evaluate(
                "node => node.textContent = 'Wrong Person XYZ'"
            )
            with pytest.raises(AssertionError, match="legend chip"):
                checked_content()
        finally:
            browser.close()


def test_candidate_only_multiple_and_absent_exemptions():
    reference = Page({})
    candidate = Page({".d9": [(1, 1, 2, 2), (5, 1, 2, 2)]})
    difference = bytearray([1] * 400)
    evidence = DIFF.apply_exemptions(
        difference, 20, 20,
        [{"id": "d9", "reference_selector": None, "candidate_selector": ".d9"}],
        reference, candidate,
    )
    assert sum(difference) == 382  # two 3x3 boxes, including the comparator's +1 edge
    assert len(evidence[0]["masked_union_boxes"]) == 2
    absent = bytearray([1] * 400)
    DIFF.apply_exemptions(
        absent, 20, 20,
        [{"id": "d9", "reference_selector": None, "candidate_selector": ".d9"}],
        reference, Page({}),
    )
    assert sum(absent) == 400


def test_tools_union_only_when_review_banner_is_present():
    conditional = '#transcript-panel:has(.transcript-pane > .hint[role="status"]:has(> strong)) .tr-floating-tools'
    exemption = [{"id": "tools", "reference_selector": ".tr-floating-tools",
                  "candidate_selector": conditional, "candidate_optional": True}]
    reference = Page({".tr-floating-tools": [(5, 3, 4, 2)]})
    absent = bytearray([1] * 400)
    DIFF.apply_exemptions(absent, 20, 20, exemption, reference, Page({}))
    assert sum(absent) == 400
    present = bytearray([1] * 400)
    evidence = DIFF.apply_exemptions(
        present, 20, 20, exemption, reference, Page({conditional: [(5, 8, 4, 2)]})
    )
    assert evidence[0]["masked_union_boxes"] == [
        {"left": 5, "top": 3, "right": 10, "bottom": 11}
    ]
    assert sum(present) == 360


def test_existing_paired_exemption_still_requires_candidate():
    import pytest

    with pytest.raises(AssertionError, match="Required declared exemption selector"):
        DIFF.apply_exemptions(
            bytearray([1] * 400), 20, 20,
            [{"id": "toggle", "reference_selector": ".tr-legend-right",
              "candidate_selector": ".tr-legend-right"}],
            Page({".tr-legend-right": [(16, 16, 2, 2)]}), Page({}),
        )


def test_non_exempt_title_regression_still_fails(tmp_path):
    reference_path = tmp_path / "reference.png"
    candidate_path = tmp_path / "candidate.png"
    Image.new("RGB", (20, 20), "white").save(reference_path)
    candidate = Image.new("RGB", (20, 20), "white")
    for x in range(1, 5):
        for y in range(1, 5):
            candidate.putpixel((x, y), (0, 0, 0))
    candidate.save(candidate_path)
    config = DIFF.load_json(ROOT / "tests/fixtures/reference_ui_screenshot_diff.json")
    reference_page = Page({".tr-legend-right": [(16, 16, 2, 2)],
                           ".tr-floating-tools": [(15, 10, 3, 2)]})
    candidate_page = Page({".tr-legend-right": [(16, 16, 2, 2)]})
    result = DIFF.compare_viewport(
        reference_path, candidate_path, tmp_path / "mask.png", config, [],
        reference_page, candidate_page,
    )
    assert result["different_pixel_percent"] == 4.0
    assert result["largest_four_connected_region_percent"] == 4.0
    assert result["passed"] is False
