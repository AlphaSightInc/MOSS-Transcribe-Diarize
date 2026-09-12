"""The optional G9 tests must skip before starting a probe on browserless hosts."""
import pytest

from tests.phase2 import browser_support, test_summary_provider_paths as paths


@pytest.mark.parametrize('entrypoint', [
    paths.test_deployed_predicate_selects_external_when_relay_is_default,
    paths.test_real_browser_external_and_relay_paths_with_fake_upstreams,
    paths.test_deterministic_probe_selection_with_relay_models_present,
])
def test_summary_entrypoints_skip_before_probe_when_browser_missing(monkeypatch, tmp_path, entrypoint):
    missing = '/missing/ms-playwright/chrome-headless-shell'

    def unavailable(playwright=None):
        raise browser_support.BrowserExecutableMissing(
            'Missing supported Chrome/Chromium executable; checked: ' + missing)

    def unexpected_probe(*args, **kwargs):
        pytest.fail('Browserless test reached probe/server setup')

    monkeypatch.setattr(browser_support, 'browser_executable', unavailable)
    monkeypatch.setattr(paths.probe, 'run', unexpected_probe)
    monkeypatch.setattr(paths.probe.bench, 'running', unexpected_probe)
    with pytest.raises(pytest.skip.Exception, match=missing):
        entrypoint(tmp_path)
