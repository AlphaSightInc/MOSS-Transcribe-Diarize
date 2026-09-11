from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import SESSION_COOKIE, create_phase2_app
from moss_transcribe_diarize import phase2_acceptance_setup as setup
from moss_transcribe_diarize.phase2_acceptance import REQUIRED_CONTENT_BOUNDARY_ROLES, _load_forbidden_values
from moss_transcribe_diarize.phase2_cutover import RESTORE_PLAN_SCHEMA


def inputs(root):
    attempt = root / "attempt"
    source = root / "source.json"
    template = Path(__file__).resolve().parents[2] / "scripts/phase2-acceptance/profile.example.json"
    source.write_text(template.read_text().replace(
        "/home/USER/.local/share/moss-transcribe-diarize/qualification-attempt", str(attempt),
    ))
    source.chmod(0o600)
    attempt.mkdir()
    (attempt / "restore-plan.json").write_text(json.dumps({
        "schema": RESTORE_PLAN_SCHEMA, "candidate_sha": "a" * 40,
    }))
    return source, attempt


def test_shipped_template_declares_every_measurement_content_boundary(tmp_path):
    source, _ = inputs(tmp_path)
    profile = json.loads(source.read_text())
    forbidden = profile.get("forbidden_files")
    assert isinstance(forbidden, dict)
    assert set(forbidden) == {
        prefix + role
        for prefix in ("", "pre_admission_")
        for role in REQUIRED_CONTENT_BOUNDARY_ROLES
    }
    assert len(set(forbidden.values())) == 10
    for layer, config in profile["measurements"].items():
        prefix = "" if layer == "deployed" else "pre_admission_"
        for role in ("a", "b", "revoked_probe"):
            assert config[f"account_{role}_cookie_file"] == forbidden[f"{prefix}account_{role}_session_cookie"]
            if role != "revoked_probe":
                assert config[f"account_{role}_peer_cookie_file"] == config[f"account_{role}_cookie_file"]
                assert config[f"account_{role}_sentinel_file"] == forbidden[f"{prefix}account_{role}_sentinel"]
        assert all(value in forbidden.values() for key, value in config.items()
                   if key.endswith(("_cookie_file", "_sentinel_file")))


def test_attempt_setup_uses_real_bootstrap_private_files_and_shared_peer_cookies(monkeypatch, tmp_path):
    source, attempt = inputs(tmp_path)
    app = create_phase2_app(database_path=tmp_path / "app.sqlite3")
    calls = []
    def client(**kwargs):
        calls.append(kwargs)
        return TestClient(app, base_url=setup.G7_PRODUCTION_ORIGIN)
    monkeypatch.setattr(setup.httpx, "Client", client)
    path = setup.prepare_acceptance_profile(source=source, attempt=attempt, candidate_sha="a" * 40)
    assert path.stat().st_mode & 0o777 == 0o600
    profile = json.loads(path.read_text())
    declared = json.loads(source.read_text())
    assert profile["forbidden_files"] == declared["forbidden_files"]
    values, _, errors = _load_forbidden_values(profile)
    assert errors == []
    assert len(values) == 10  # six distinct credentials and four title sentinels
    owners = set()
    with TestClient(app, base_url=setup.G7_PRODUCTION_ORIGIN) as browser:
        for config in profile["measurements"].values():
            assert config["cutover_restore_plan"] == str(attempt / "restore-plan.json")
            for role in ("a", "b", "revoked_probe"):
                cookie_file = Path(config[f"account_{role}_cookie_file"])
                assert cookie_file.stat().st_mode & 0o777 == 0o600
                cookie = cookie_file.read_text()
                browser.cookies.clear()
                result = browser.get("/api/auth/session", headers={"Cookie": f"{SESSION_COOKIE}={cookie}"})
                assert result.status_code == 200
                owners.add(result.json()["workspace_id"])
                if role != "revoked_probe":
                    assert config[f"account_{role}_peer_cookie_file"] == str(cookie_file)
    assert len(owners) == 6
    assert calls == [{"base_url": setup.G7_PRODUCTION_ORIGIN, "timeout": 30, "follow_redirects": False}] * 2
    assert not any(value.decode() in path.read_text() for value in values)
    with pytest.raises(FileExistsError):
        setup.prepare_acceptance_profile(source=source, attempt=attempt, candidate_sha="a" * 40)
    # Aliasing independent owners, or inventing a separate peer credential, is refused.
    config = profile["measurements"]["deployed"]
    config["account_a_peer_cookie_file"] = config["account_b_cookie_file"]
    assert "measurement_peer_cookie_not_shared:deployed:a" in _load_forbidden_values(profile)[2]
    config["account_a_peer_cookie_file"] = config["account_a_cookie_file"]
    config["account_b_cookie_file"] = config["account_a_cookie_file"]
    assert "measurement_owner_cookie_files_not_distinct" in _load_forbidden_values(profile)[2]


@pytest.mark.parametrize("fault", ["candidate", "origin", "tls"])
def test_attempt_setup_refuses_wrong_candidate_origin_or_tls_before_credentials(monkeypatch, tmp_path, fault):
    source, attempt = inputs(tmp_path)
    sha = "b" * 40 if fault == "candidate" else "a" * 40
    if fault == "origin":
        profile = json.loads(source.read_text())
        profile["measurements"]["deployed"]["https_origin"] = "http://moss.test"
        source.write_text(json.dumps(profile))
    def unavailable(**kwargs):
        raise setup.httpx.ConnectError("TLS trust failure")
    monkeypatch.setattr(setup.httpx, "Client", unavailable)
    expected = setup.httpx.ConnectError if fault == "tls" else setup.QualificationSetupError
    with pytest.raises(expected):
        setup.prepare_acceptance_profile(source=source, attempt=attempt, candidate_sha=sha)
    assert list(attempt.rglob("*.cookie")) == []
