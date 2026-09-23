"""G10 fixture controls through the production screenshot comparator."""

import importlib.util
from pathlib import Path

from PIL import Image


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
        "d9-reassign-passage",
        "d7-shifted-transcript-tools",
    ]


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
