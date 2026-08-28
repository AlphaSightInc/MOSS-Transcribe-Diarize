from __future__ import annotations

import json

import pytest

from moss_transcribe_diarize import phase2_g7_canary as g7


def _candidate():
    return {"git_sha": "a" * 40, "git_tree": "b" * 40, "uv_lock_sha256": "c" * 64}


def _scenario(scenario: str, surface: str):
    return {
        "id": scenario,
        "session_id": f"meeting-{scenario}",
        "source_revision": "a" * 40,
        "display_surface": surface,
        "display_audio_tracks": 1,
        "meter_nonzero_samples": {"microphone": 1, "system": 1},
        "frames": {
            lane: {
                "accepted_frames": 2,
                "first_sequence": 0,
                "last_sequence": 1,
                "sequence_gaps": 0,
                "geometry_mismatches": 0,
            }
            for lane in ("microphone", "system")
        },
        "distinct_speakers": 2,
        "meeting_status": "completed",
        "audio_state": "available",
        "owner_download_status": 200,
        "audio_probe": {
            "codec": "mp3",
            "sample_rate_hz": 16_000,
            "channels": 1,
            "bit_rate_bps": 48_000,
            "byte_count": 100,
        },
    }


def test_frame_summary_derives_geometry_and_sequence_gaps_from_raw_posts():
    descriptor = {"frame_samples": 8_000, "sample_rate": 16_000}
    frames = []
    for lane in ("microphone", "system"):
        for sequence in (0, 2):
            frames.append(
                {
                    "lane": lane,
                    "sequence": sequence,
                    "capture_timestamp_ns": sequence * 500_000_000,
                    "device_epoch": 0,
                    "pcm_base64": "AA==",
                    "sample_count": 8_000,
                    "sample_rate": 16_000,
                    "silent": False,
                    "discontinuity": False,
                }
            )
    summary = g7._frame_summary(frames, descriptor)
    assert summary["microphone"]["accepted_frames"] == 2
    assert summary["microphone"]["sequence_gaps"] == 1
    frames[0]["sample_count"] = 4_000
    assert g7._frame_summary(frames, descriptor)["microphone"]["geometry_mismatches"] == 1


def test_attended_meter_checkpoint_accepts_delayed_signal_and_refuses_all_zero(monkeypatch):
    class Page:
        waits = 0

        def wait_for_timeout(self, _milliseconds):
            self.waits += 1

    class Locator:
        def __init__(self, value):
            self.value = value

        def get_attribute(self, _name):
            return self.value

    class MeterPage:
        def __init__(self, value):
            self.value = value

        def locator(self, _selector):
            return Locator(self.value)

    assert g7._meter_level(MeterPage("Microphone level 37%"), "Microphone") == 37
    assert g7._meter_level(MeterPage("Microphone level invalid%"), "Microphone") == 0
    assert g7._meter_level(MeterPage(None), "Microphone") == 0

    page = Page()
    levels = iter((0, 0, 4, 0, 0, 9))
    monkeypatch.setattr(g7, "_meter_level", lambda _page, _label: next(levels))
    assert g7._observe_nonzero_meters(page) == {"microphone": 1, "system": 1}
    assert page.waits == 2

    monkeypatch.setattr(g7, "_meter_level", lambda _page, _label: 0)
    with pytest.raises(g7.AttendedCanaryError, match="both audio meters"):
        g7._observe_nonzero_meters(Page())


def test_candidate_owned_runner_reads_only_prerequisites_and_builds_fixed_evidence(
    monkeypatch, tmp_path
):
    chrome = tmp_path / "chrome"
    chrome.write_bytes(b"chrome")
    browser_profile = tmp_path / "profile"
    browser_profile.mkdir()
    profile = tmp_path / "acceptance.json"
    profile.write_text(
        json.dumps(
            {
                "measurements": {
                    "pre_admission": {
                        "https_origin": "https://moss.example",
                        "chrome_binary": str(chrome),
                        "allowed_google_browser_profile": str(browser_profile),
                        "caller_authored_result": "ignored",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    profile.chmod(0o600)

    class Browser:
        version = "Chrome/real"

    class Context:
        browser = Browser()

        def add_init_script(self, _script):
            pass

        def close(self):
            pass

    class Chromium:
        def launch_persistent_context(self, *_args, **_kwargs):
            return Context()

    class Playwright:
        chromium = Chromium()

    class Manager:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(g7, "sync_playwright", Manager)
    monkeypatch.setattr(
        g7,
        "_run_scenario",
        lambda _context, *, scenario, expected_surface, **_kwargs: _scenario(
            scenario, expected_surface
        ),
    )
    evidence = g7.run_attended_g7_canary(
        acceptance_profile=profile,
        candidate=_candidate(),
        confirm=lambda _prompt: "",
    )
    assert evidence["source"] == g7.G7_EVIDENCE_SOURCE
    assert evidence["candidate"] == _candidate()
    assert evidence["origin"] == "https://moss.example"
    assert {row["id"] for row in evidence["scenarios"]} == set(g7.G7_SCENARIOS)
    assert "caller_authored_result" not in evidence


def test_attended_runner_refuses_noninteractive_or_incomplete_prerequisites(monkeypatch, tmp_path):
    profile = tmp_path / "acceptance.json"
    profile.write_text(json.dumps({"measurements": {"pre_admission": {}}}), encoding="utf-8")
    profile.chmod(0o600)
    monkeypatch.setattr(g7.sys.stdin, "isatty", lambda: False)
    with pytest.raises(g7.AttendedCanaryError, match="interactive terminal"):
        g7.run_attended_g7_canary(acceptance_profile=profile, candidate=_candidate())
