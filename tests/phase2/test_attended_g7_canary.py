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


def test_a_silent_lane_is_named_with_what_the_other_lane_reached(monkeypatch):
    """A bare "both meters" failure costs an entire attempt to diagnose."""

    class Page:
        def wait_for_timeout(self, _ms):
            pass

    levels = {"Microphone": 0, "Shared audio": 62}
    monkeypatch.setattr(g7, "_meter_level", lambda _page, label: levels[label])
    with pytest.raises(g7.AttendedCanaryError) as caught:
        g7._observe_nonzero_meters(Page())
    message = str(caught.value)
    assert "Microphone stayed silent" in message
    assert "Shared audio peaked at 62%" in message
    assert "Microphone peaked at 0%" in message
    assert "BEFORE pressing Enter" in message


def test_both_lanes_silent_are_both_named(monkeypatch):
    class Page:
        def wait_for_timeout(self, _ms):
            pass

    monkeypatch.setattr(g7, "_meter_level", lambda _page, _label: 0)
    with pytest.raises(g7.AttendedCanaryError) as caught:
        g7._observe_nonzero_meters(Page())
    assert "Microphone and Shared audio stayed silent" in str(caught.value)


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

    profile = _profile_with(
        tmp_path, chrome_cdp_endpoint="ws://127.0.0.1:9222/devtools/browser/abc"
    )
    observed: dict[str, object] = {}

    class Context:
        def add_init_script(self, _script):
            observed["init_script"] = True

        def clear_cookies(self, **filters):
            observed["cleared"] = filters

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
    assert observed["endpoint"] == "ws://127.0.0.1:9222/devtools/browser/abc"
    assert observed["context"] is attached
    assert observed["init_script"] is True
    assert observed["disconnected"] is True
    # Only the production origin's session is reset, never the whole profile.
    assert observed["cleared"] == {"domain": "ga0-alienware-rtx4070ti.tailnet.aisight.us"}
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
    profile = _profile_with(
        tmp_path, chrome_cdp_endpoint="ws://127.0.0.1:9222/devtools/browser/abc"
    )

    class Context:
        def add_init_script(self, _script):
            pass

        def clear_cookies(self, **_filters):
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
        # Two URL parsers must not be able to read one string as two different hosts.
        # Python's urlsplit reads the host below as 127.0.0.1; the WHATWG parser the
        # driver uses reads evil.example, because it treats the backslash as a slash.
        "http://evil.example\\@127.0.0.1:9222",
        "ws://evil.example\\@127.0.0.1:9222/devtools/browser/abc",
        "http://evil.example@127.0.0.1:9222",
        "http://127.0.0.1@evil.example:9222",
        "http://0.0.0.0:9222",
        "http://127.0.0.2:9222",
        "http://2130706433:9222",
        "http://0177.0.0.1:9222",
        "http://localhost.:9222",
        "http://localhost:bad",
        "http://local\nhost:9222",
        "\x01http://localhost:9222",
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


def test_devtools_discovery_is_resolved_here_and_bounded_to_the_forward(monkeypatch):
    """Whatever answers the endpoint must not get to nominate an off-loopback websocket."""

    class Response:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode()

        def read(self, *_args):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    nominated = {}

    def opener_for(payload):
        class Opener:
            def open(self, url, timeout=None):
                nominated["url"] = url
                return Response(payload)

        return Opener()

    monkeypatch.setattr(
        g7.urllib.request,
        "build_opener",
        lambda *_a: opener_for({"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/ok"}),
    )
    assert (
        g7._attended_devtools_target("http://127.0.0.1:9222")
        == "ws://127.0.0.1:9222/devtools/browser/ok"
    )
    assert nominated["url"] == "http://127.0.0.1:9222/json/version"

    monkeypatch.setattr(
        g7.urllib.request,
        "build_opener",
        lambda *_a: opener_for({"webSocketDebuggerUrl": "ws://evil.example:9222/devtools/browser/x"}),
    )
    with pytest.raises(g7.AttendedCanaryError, match="DevTools target"):
        g7._attended_devtools_target("http://127.0.0.1:9222")


def test_a_websocket_endpoint_needs_no_discovery():
    target = "ws://127.0.0.1:9222/devtools/browser/abc"
    assert g7._attended_devtools_target(target) == target


def test_every_automatic_capture_selection_switch_is_refused():
    """The audit list must cover Chromium's auto-selection switches, not a subset."""

    for switch in (
        "auto-select-desktop-capture-source",
        "auto-select-screen-capture-source",
        "auto-select-tab-capture-source-by-title",
        "auto-accept-this-tab-capture",
        "auto-accept-camera-and-microphone-capture",
        "auto-grant-captured-surface-control",
    ):
        assert switch in g7.FORBIDDEN_ATTENDED_SWITCHES


def test_attended_runner_refuses_a_browser_whose_session_cannot_be_reset(monkeypatch, tmp_path):
    """A stale session silently defeats the gate, so failing to clear it must stop the run."""

    class Context:
        def add_init_script(self, _script):
            pass

        def clear_cookies(self, **_filters):
            raise RuntimeError("CDP refused")

    session = _CommandLineSession(["--enable-automation"])
    run = _attach_runner(monkeypatch, tmp_path, session, contexts=[Context()])
    with pytest.raises(g7.AttendedCanaryError, match="could not be reset"):
        run()


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


@pytest.mark.parametrize(
    "target,phase,readiness,message",
    [
        ("ready", "configuring", "Next: speak into your microphone. Shared audio is receiving sound.",
         "Microphone connected. Share a browser tab, window, or screen with audio."),
        ("ready", "error", None, "microphone: microphone_track_ended"),
        ("active", "error", None, "system: display_track_ended"),
    ],
)
def test_scenario_timeout_reports_only_capture_status_and_selects_headphones(
    monkeypatch, target, phase, readiness, message
):
    from types import SimpleNamespace
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    from tests.phase2.browser_support import require_browser

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(require_browser(playwright)))
        try:
            raw = browser.new_page()
            raw.route("https://fixture.test/", lambda route: route.fulfill(
                content_type="text/html", body='''
                <main data-auth-state="signed-in" data-boot="ready">
                  <section data-capture-phase="ready">
                    <select aria-label="Listening setup">
                      <option value="speakers">Speakers</option>
                      <option value="headphones">Headphones</option>
                    </select>
                    <button onclick="window.routeAtMicrophone = document.querySelector('select').value">Enable microphone</button>
                    <button>Share audio</button><button>Start capture</button>
                    <p data-capture-readiness></p>
                    <p class="capture-status" role="status"></p>
                  </section>
                  <p role="status">PRIVATE TRANSCRIPT STATUS</p>
                  <article>PRIVATE TRANSCRIPT</article>
                  <input value="PRIVATE SECRET">
                </main>
                <script>window.__mossAttendedDisplay = {surface: 'browser', audio_tracks: 1};</script>
                '''))
            closed = []
            original_timeout = []

            class Page:
                def __getattr__(self, name):
                    return getattr(raw, name)

                def wait_for_selector(self, selector, **kwargs):
                    if selector == f'[data-capture-phase="{target}"]':
                        assert kwargs == {"timeout": 120_000}
                        raw.evaluate('''({phase, readiness, message}) => {
                            document.querySelector('[data-capture-phase]').setAttribute('data-capture-phase', phase);
                            const hint = document.querySelector('[data-capture-readiness]');
                            if (readiness === null) hint.remove(); else hint.textContent = readiness;
                            document.querySelector('.capture-status').textContent = message;
                        }''', dict(phase=phase, readiness=readiness, message=message))
                        try:
                            return raw.wait_for_selector(selector, timeout=100)
                        except PlaywrightTimeout as exc:
                            original_timeout.append(exc)
                            raise
                    return raw.wait_for_selector(selector, **kwargs)

                def close(self):
                    closed.append(True)  # Keep fixture readable for post-scenario assertions.

            context = SimpleNamespace(
                new_page=lambda: Page(),
                request=SimpleNamespace(get=lambda _: SimpleNamespace(
                    status=200, json=lambda: {"descriptor": {}}
                )),
            )
            monkeypatch.setattr(g7, "_observe_nonzero_meters", lambda _: {
                "microphone": 1, "system": 1,
            })
            with pytest.raises(g7.AttendedCanaryError) as caught:
                g7._run_scenario(context, origin="https://fixture.test",
                                 scenario="microphone_meeting_tab", expected_surface="browser",
                                 confirm=lambda _: "")
            detail = str(caught.value)
            assert target in detail and "microphone_meeting_tab" in detail
            assert f'"phase": "{phase}"' in detail
            assert message in detail
            if readiness is None:
                assert '"readiness": null' in detail
            else:
                assert readiness in detail
            assert "PRIVATE" not in detail
            assert caught.value.__cause__ is original_timeout[0]
            assert raw.evaluate("window.routeAtMicrophone") == "headphones"
            assert closed == [True]
        finally:
            browser.close()
