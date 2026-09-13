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
    profile = tmp_path / "acceptance.json"
    profile.write_text(
        json.dumps(
            {
                "measurements": {
                    "pre_admission": {
                        "https_origin": g7.G7_PRODUCTION_ORIGIN,
                        "chrome_binary": str(chrome),
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

    monkeypatch.setattr(g7, "_playwright_manager", Manager)
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
    assert evidence["origin"] == g7.G7_PRODUCTION_ORIGIN
    assert {row["id"] for row in evidence["scenarios"]} == set(g7.G7_SCENARIOS)
    assert "caller_authored_result" not in evidence
    assert evidence["attended_browser"] == "host_chrome"


def _profile_with(tmp_path, **prerequisites):
    profile = tmp_path / "acceptance.json"
    payload = {"https_origin": g7.G7_PRODUCTION_ORIGIN}
    payload.update(prerequisites)
    profile.write_text(
        json.dumps({"measurements": {"pre_admission": payload}}), encoding="utf-8"
    )
    profile.chmod(0o600)
    return profile


def test_attended_runner_attaches_to_the_operator_loopback_browser(monkeypatch, tmp_path):
    """The attended client may run on the operator's machine, not the server."""

    profile = _profile_with(tmp_path, chrome_cdp_endpoint="http://127.0.0.1:9222")
    observed: dict[str, object] = {}

    class Context:
        def add_init_script(self, _script):
            observed["init_script"] = True

    attached = Context()

    class Browser:
        version = "Chrome/operator"
        contexts = [attached]

        def close(self):
            observed["disconnected"] = True

        def new_browser_cdp_session(self):
            return _CommandLineSession(["--enable-automation", "--remote-debugging-port=9222"])

        def new_context(self):  # pragma: no cover - only reached without an open context
            raise AssertionError("the operator's existing context must be reused")

    class Chromium:
        def connect_over_cdp(self, endpoint):
            observed["endpoint"] = endpoint
            return Browser()

        def launch_persistent_context(self, *_args, **_kwargs):
            raise AssertionError("a remote attended browser must never be launched on the host")

    class Playwright:
        chromium = Chromium()

    class Manager:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(g7, "_playwright_manager", Manager)
    monkeypatch.setattr(
        g7,
        "_run_scenario",
        lambda context, *, scenario, expected_surface, **_kwargs: (
            observed.setdefault("context", context),
            _scenario(scenario, expected_surface),
        )[1],
    )
    evidence = g7.run_attended_g7_canary(
        acceptance_profile=profile,
        candidate=_candidate(),
        confirm=lambda _prompt: "",
    )
    assert observed["endpoint"] == "http://127.0.0.1:9222"
    assert observed["context"] is attached
    assert observed["init_script"] is True
    assert observed["disconnected"] is True
    assert evidence["attended_browser"] == "operator_devtools"
    assert evidence["chrome_version"] == "Chrome/operator"
    g7.validate_attended_g7(evidence, candidate=_candidate())


class _CommandLineSession:
    """Stands in for Chrome's Browser.getBrowserCommandLine CDP session."""

    def __init__(self, arguments, *, refuse=False):
        self._arguments = arguments
        self._refuse = refuse
        self.detached = False

    def send(self, method):
        assert method == "Browser.getBrowserCommandLine"
        if self._refuse:
            raise RuntimeError("Command line not returned because --enable-automation not set.")
        return {"arguments": list(self._arguments)}

    def detach(self):
        self.detached = True


def _attach_runner(monkeypatch, tmp_path, session, *, contexts=None):
    profile = _profile_with(tmp_path, chrome_cdp_endpoint="http://127.0.0.1:9222")

    class Context:
        def add_init_script(self, _script):
            pass

    open_contexts = [Context()] if contexts is None else contexts

    class Browser:
        version = "Chrome/operator"
        contexts = open_contexts

        def close(self):
            pass

        def new_browser_cdp_session(self):
            return session

    class Chromium:
        def connect_over_cdp(self, _endpoint):
            return Browser()

        def launch_persistent_context(self, *_args, **_kwargs):
            raise AssertionError("must not launch on the host")

    class Playwright:
        chromium = Chromium()

    class Manager:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(g7, "_playwright_manager", Manager)
    monkeypatch.setattr(
        g7,
        "_run_scenario",
        lambda _context, *, scenario, expected_surface, **_kwargs: _scenario(
            scenario, expected_surface
        ),
    )
    return lambda: g7.run_attended_g7_canary(
        acceptance_profile=profile, candidate=_candidate(), confirm=lambda _p: ""
    )


@pytest.mark.parametrize(
    "switch",
    (
        "--use-fake-device-for-media-stream",
        "--use-file-for-fake-audio-capture=/tmp/speech.wav",
        "--use-fake-ui-for-media-stream",
        "--auto-select-desktop-capture-source=Entire screen",
        "--auto-accept-this-tab-capture",
    ),
)
def test_attended_runner_refuses_a_browser_that_can_manufacture_capture(
    switch, monkeypatch, tmp_path
):
    """Synthetic capture devices and auto-answered prompts are not attendance."""

    session = _CommandLineSession(["--enable-automation", switch])
    run = _attach_runner(monkeypatch, tmp_path, session)
    with pytest.raises(g7.AttendedCanaryError, match="synthetic-capture or auto-accept"):
        run()


def test_attended_runner_refuses_a_browser_whose_command_line_cannot_be_audited(
    monkeypatch, tmp_path
):
    """A command line that cannot be read cannot be cleared."""

    session = _CommandLineSession([], refuse=True)
    run = _attach_runner(monkeypatch, tmp_path, session)
    with pytest.raises(g7.AttendedCanaryError, match="--enable-automation"):
        run()


def test_attended_runner_records_the_switches_it_cleared(monkeypatch, tmp_path):
    session = _CommandLineSession(["--enable-automation", "--remote-debugging-port=9222"])
    evidence = _attach_runner(monkeypatch, tmp_path, session)()
    assert evidence["audited_absent_switches"] == sorted(g7.FORBIDDEN_ATTENDED_SWITCHES)
    assert session.detached is True
    g7.validate_attended_g7(evidence, candidate=_candidate())


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://ga0-m4mbp.tailnet.aisight.us:9222",
        "http://10.0.0.4:9222",
        "https://127.0.0.1:9222",
        "file:///tmp/devtools",
        "   ",
        "",
    ),
)
def test_attended_runner_refuses_a_devtools_endpoint_off_loopback(endpoint, monkeypatch, tmp_path):
    """DevTools control of the attended browser must not be reachable from the network."""

    profile = _profile_with(tmp_path, chrome_cdp_endpoint=endpoint)
    monkeypatch.setattr(
        g7, "_playwright_manager", lambda: (_ for _ in ()).throw(AssertionError("refuse first"))
    )
    with pytest.raises(g7.AttendedCanaryError, match="DevTools endpoint"):
        g7.run_attended_g7_canary(
            acceptance_profile=profile,
            candidate=_candidate(),
            confirm=lambda _prompt: "",
        )


def test_attended_runner_refuses_noninteractive_or_incomplete_prerequisites(monkeypatch, tmp_path):
    profile = tmp_path / "acceptance.json"
    profile.write_text(json.dumps({"measurements": {"pre_admission": {}}}), encoding="utf-8")
    profile.chmod(0o600)
    monkeypatch.setattr(g7.sys.stdin, "isatty", lambda: False)
    with pytest.raises(g7.AttendedCanaryError, match="interactive terminal"):
        g7.run_attended_g7_canary(acceptance_profile=profile, candidate=_candidate())


@pytest.mark.parametrize(
    "origin",
    (
        "https://not-production.invalid:444",
        "https://ga0-alienware-rtx4070ti.tailnet.aisight.us",
        "https://ga0-alienware-rtx4070ti.tailnet.aisight.us:444",
    ),
)
def test_attended_evidence_rejects_every_wrong_production_host_or_port(
    origin, monkeypatch, tmp_path
):
    payload = {
        "schema": g7.G7_EVIDENCE_SCHEMA,
        "source": g7.G7_EVIDENCE_SOURCE,
        "production_origin": True,
        "operator_attended": True,
        "admitted": False,
        "origin": origin,
        "candidate": _candidate(),
        "chrome_version": "Chrome/real",
        "scenarios": [
            _scenario(scenario, surface)
            for scenario, surface in g7.G7_SCENARIOS.items()
        ],
    }
    with pytest.raises(g7.AttendedCanaryError, match="identity"):
        g7.validate_attended_g7(payload, candidate=_candidate())

    profile = tmp_path / "acceptance.json"
    profile.write_text(
        json.dumps(
            {"measurements": {"pre_admission": {"https_origin": origin}}}
        ),
        encoding="utf-8",
    )
    profile.chmod(0o600)
    monkeypatch.setattr(g7.sys.stdin, "isatty", lambda: True)
    with pytest.raises(g7.AttendedCanaryError, match="exact production HTTPS origin"):
        g7.run_attended_g7_canary(
            acceptance_profile=profile, candidate=_candidate()
        )
