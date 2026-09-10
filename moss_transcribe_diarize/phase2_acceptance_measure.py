"""Candidate-owned external measurement orchestration for Phase-2 qualification.

The operator profile supplies data endpoints and secret-file locations only.  It never supplies an
executable, a report, raw predicate state, or a pass/fail claim.  This module exclusively creates a
fresh raw-observation directory and records which committed measurement family ran or why it was
not reachable.  A typed UNMEASURED observation is deliberately non-qualifying.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .phase2_acceptance import EXTERNAL_REQUIREMENTS, _write_all
from .phase2_acceptance_collect import RAW_SCHEMA, _artifact_name
from .phase2_acceptance_external import ExternalMeasurementError, FixedAccountCampaign


MEASUREMENT_SCHEMA = "moss-phase2-fixed-measurement.v1"


@dataclass(frozen=True, slots=True)
class MeasurementPrerequisite:
    key: str
    description: str


# These families are the only external programs the driver is permitted to execute.  They name
# committed product paths, not caller-selected commands.  The same family may satisfy multiple
# predicates, but every predicate keeps its own raw denominator.
PREDICATE_FAMILY: Mapping[str, str] = {
    "installed_candidate_identity": "account-http-uds",
    "zero_work_end": "account-http-uds",
    "cross_owner_matrix": "account-http-uds",
    "sentinel_absence": "account-browser-uds",
    "same_account_convergence": "account-browser",
    "browser_workspace_identity": "account-browser-workspace",
    "revocation_lifecycle": "account-browser-uds",
    "meeting_modes_history_restart": "account-browser-http",
    "crash_recovery": "account-host-restart",
    "four_session_capacity": "account-live-capacity",
    "eight_session_overload": "account-live-capacity",
    "quality_corpus": "account-live-quality",
    "audio_durability_download": "account-browser-http",
    "operator_control": "account-uds",
    "account_product_regression": "account-browser",
    "transcript_pane_fidelity": "account-browser",
}

PREDICATE_PREREQUISITES: Mapping[str, tuple[MeasurementPrerequisite, ...]] = {
    "installed_candidate_identity": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("candidate_manifest", "staged candidate manifest"),
        MeasurementPrerequisite("chrome_binary", "exact Chrome executable"),
        MeasurementPrerequisite("file_fixture", "fixed File input"),
        MeasurementPrerequisite("url_fixture", "fixed URL input"),
    ),
    "zero_work_end": (
        MeasurementPrerequisite("operator_socket", "service-owned operator socket"),
    ),
    "cross_owner_matrix": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_b_cookie_file", "Account B Sign-in session cookie"),
        MeasurementPrerequisite("account_b_peer_cookie_file", "revocable Account B peer session"),
        MeasurementPrerequisite(
            "account_revoked_probe_cookie_file", "disposable revoked-session probe"
        ),
        MeasurementPrerequisite("account_a_sentinel_file", "Account A sentinel"),
    ),
    "sentinel_absence": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_b_cookie_file", "Account B Sign-in session cookie"),
        MeasurementPrerequisite("operator_socket", "service-owned operator socket"),
        MeasurementPrerequisite("account_a_sentinel_file", "Account A sentinel"),
        MeasurementPrerequisite("account_b_sentinel_file", "Account B sentinel"),
        MeasurementPrerequisite("operator_journal", "content-free operator journal"),
        MeasurementPrerequisite("server_log", "server log"),
        MeasurementPrerequisite("llm_prompt_log", "LLM prompt log"),
        MeasurementPrerequisite("chrome_binary", "Chrome executable"),
    ),
    "same_account_convergence": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_a_peer_cookie_file", "second Account A Sign-in session"),
    ),
    "browser_workspace_identity": (
        MeasurementPrerequisite("file_fixture", "real speech for nonempty saved browser history"),
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("operator_socket", "service-owned operator socket"),
        MeasurementPrerequisite("chrome_binary", "Chrome executable"),
    ),
    "meeting_modes_history_restart": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_b_cookie_file", "Account B Sign-in session cookie"),
        MeasurementPrerequisite("account_a_peer_cookie_file", "second Account A Sign-in session"),
        MeasurementPrerequisite("file_fixture", "real File Meeting input"),
        MeasurementPrerequisite("url_fixture", "real URL Meeting input"),
        MeasurementPrerequisite("chrome_binary", "Chrome executable"),
    ),
    "crash_recovery": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("web_unit", "fixed Account web service unit"),
        MeasurementPrerequisite("operator_socket", "service-owned operator socket"),
        MeasurementPrerequisite("quality_corpus", "frozen real-human-speech corpus"),
    ),
    "four_session_capacity": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_b_cookie_file", "Account B Sign-in session cookie"),
        MeasurementPrerequisite("operator_socket", "service-owned operator socket"),
        MeasurementPrerequisite("quality_corpus", "frozen real-human-speech corpus"),
        MeasurementPrerequisite("vllm_metrics_url", "host-local vLLM metrics"),
        MeasurementPrerequisite("account_a_sentinel_file", "Account A sentinel"),
        MeasurementPrerequisite("account_b_sentinel_file", "Account B sentinel"),
        MeasurementPrerequisite("server_log", "Account server log"),
        MeasurementPrerequisite("vllm_log", "vLLM log"),
    ),
    "eight_session_overload": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_b_cookie_file", "Account B Sign-in session cookie"),
        MeasurementPrerequisite("operator_socket", "service-owned operator socket"),
        MeasurementPrerequisite("quality_corpus", "frozen real-human-speech corpus"),
        MeasurementPrerequisite("account_a_sentinel_file", "Account A sentinel"),
        MeasurementPrerequisite("account_b_sentinel_file", "Account B sentinel"),
        MeasurementPrerequisite("server_log", "Account server log"),
        MeasurementPrerequisite("vllm_log", "vLLM log"),
    ),
    "quality_corpus": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_b_cookie_file", "Account B Sign-in session cookie"),
        MeasurementPrerequisite("quality_corpus", "frozen six-case corpus"),
    ),
    "audio_durability_download": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_b_cookie_file", "Account B Sign-in session cookie"),
        MeasurementPrerequisite("file_fixture", "real File Meeting input"),
        MeasurementPrerequisite("meeting_audio_root", "Account Meeting audio root"),
    ),
    "operator_control": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("operator_socket", "service-owned operator socket"),
        MeasurementPrerequisite("operator_journal", "content-free operator journal"),
        MeasurementPrerequisite("quality_corpus", "frozen real-human-speech corpus"),
    ),
    "revocation_lifecycle": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("account_a_peer_cookie_file", "second Account A Sign-in session"),
        MeasurementPrerequisite("account_b_cookie_file", "Account B Sign-in session cookie"),
        MeasurementPrerequisite("account_b_peer_cookie_file", "second Account B Sign-in session"),
        MeasurementPrerequisite("cutover_restore_plan", "same-candidate disposable state inventory"),
        MeasurementPrerequisite("file_fixture", "real File Meeting input"),
        MeasurementPrerequisite("chrome_binary", "Chrome executable"),
        MeasurementPrerequisite("operator_socket", "service-owned operator socket"),
    ),
    "account_product_regression": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("chrome_binary", "Chrome executable"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("file_fixture", "real File Meeting input"),
    ),
    "transcript_pane_fidelity": (
        MeasurementPrerequisite("https_origin", "deployed trusted HTTPS Account origin"),
        MeasurementPrerequisite("chrome_binary", "Chrome executable"),
        MeasurementPrerequisite("live_transcribe_reference", "LiveTranscribe reference origin"),
        MeasurementPrerequisite("account_a_cookie_file", "Account A Sign-in session cookie"),
        MeasurementPrerequisite("file_fixture", "real File Meeting input"),
    ),
}


def _write_json_once(path: Path, payload: object) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _snapshot_campaign_artifacts(
    campaign: FixedAccountCampaign | None, raw_dir: Path
) -> tuple[str, ...]:
    """Retain only artifacts explicitly produced as content-free evidence.

    The campaign work directory also contains speech, transcripts, screenshots, and logs.  It is
    deliberately not an evidence source: the candidate-owned producer must first reduce a
    load-bearing observation to an allowlisted JSON artifact and register that exact path.
    """

    if campaign is None:
        return ()
    relative_paths = campaign.safe_artifacts
    if not relative_paths:
        return ()
    source_root = campaign.artifact_root
    destination_root = raw_dir / "artifacts"
    os.mkdir(destination_root, mode=0o700)
    copied: list[str] = []
    for relative in relative_paths:
        source = source_root / relative
        if source.is_symlink():
            raise ValueError("campaign artifact must not be a symlink")
        destination = destination_root / relative
        if not source.is_file():
            raise ValueError("campaign artifact must be a regular file")
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with source.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    _write_all(descriptor, chunk)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        copied.append(relative.as_posix())
    return tuple(copied)


def _missing_prerequisites(
    predicate_id: str, config: Mapping[str, object]
) -> tuple[str, ...]:
    missing: list[str] = []
    for requirement in PREDICATE_PREREQUISITES[predicate_id]:
        value = config.get(requirement.key)
        if not isinstance(value, str) or not value:
            missing.append(requirement.key)
    return tuple(missing)


def _unmeasured_observation(
    *, layer: str, candidate_sha: str, gate: str, predicate_id: str,
    family: str, reasons: tuple[str, ...]
) -> dict[str, object]:
    return {
        "schema": RAW_SCHEMA,
        "measurement_schema": MEASUREMENT_SCHEMA,
        "layer": layer,
        "candidate_sha": candidate_sha,
        "gate": gate,
        "id": predicate_id,
        "producer": {"family": family, "implementation": "candidate-owned"},
        "samples": [
            {
                "id": f"{predicate_id}-unmeasured",
                "executed": False,
                "passed": False,
                "state": "UNMEASURED",
            }
        ],
        "raw": {
            "measurement_state": "UNMEASURED",
            "reason_codes": list(reasons),
        },
    }


def measure_layer(
    *,
    layer: str,
    candidate_sha: str,
    config: Mapping[str, object] | None,
    raw_dir: Path,
) -> dict[str, object]:
    """Create one fresh raw directory; never consume caller-authored observations.

    Measurement families remain non-qualifying until their concrete prerequisites are supplied and
    their committed campaign implementation executes.  Absence is explicit and the return state is
    retained even though the command exits nonzero.
    """

    if layer not in EXTERNAL_REQUIREMENTS:
        raise ValueError(f"unsupported observation layer: {layer}")
    raw_dir = raw_dir.resolve()
    os.mkdir(raw_dir.parent, mode=0o700)
    os.mkdir(raw_dir, mode=0o700)
    layer_config: Mapping[str, object] = config if isinstance(config, Mapping) else {}
    campaign: FixedAccountCampaign | None = None
    campaign_error: str | None = None
    try:
        campaign = FixedAccountCampaign(
            candidate_sha=candidate_sha,
            config=layer_config,
        )
    except (ExternalMeasurementError, OSError, ValueError, json.JSONDecodeError) as exc:
        campaign_error = f"campaign_start:{type(exc).__name__}"
    predicates: list[dict[str, object]] = []
    required = [
        (gate, predicate_id)
        for gate, predicate_ids in EXTERNAL_REQUIREMENTS[layer].items()
        for predicate_id in predicate_ids
        if predicate_id not in {"zero_work_end", "revocation_lifecycle"}
    ]
    for gate, predicate_ids in EXTERNAL_REQUIREMENTS[layer].items():
        if "revocation_lifecycle" in predicate_ids:
            required.append((gate, "revocation_lifecycle"))
    required.append(("G0", "zero_work_end"))
    cleanup_error: str | None = None
    try:
        for gate, predicate_id in required:
            if predicate_id == "zero_work_end" and campaign is not None:
                try:
                    campaign.cleanup()
                except Exception as exc:
                    cleanup_error = f"campaign_cleanup:{type(exc).__name__}"
            family = PREDICATE_FAMILY[predicate_id]
            missing = _missing_prerequisites(predicate_id, layer_config)
            method = getattr(campaign, predicate_id, None) if campaign is not None else None
            reasons = tuple(f"missing:{item}" for item in missing)
            if campaign_error is not None and not reasons:
                reasons = (campaign_error,)
            if cleanup_error is not None and predicate_id == "zero_work_end" and not reasons:
                reasons = (cleanup_error,)
            if method is None and not reasons:
                reasons = (f"campaign_not_executed:{family}",)
            if reasons:
                payload = _unmeasured_observation(
                    layer=layer,
                    candidate_sha=candidate_sha,
                    gate=gate,
                    predicate_id=predicate_id,
                    family=family,
                    reasons=reasons,
                )
                state_name = "UNMEASURED"
            else:
                try:
                    raw = method()
                    payload = {
                        "schema": RAW_SCHEMA,
                        "measurement_schema": MEASUREMENT_SCHEMA,
                        "layer": layer,
                        "candidate_sha": candidate_sha,
                        "gate": gate,
                        "id": predicate_id,
                        "producer": {"family": family, "implementation": "candidate-owned"},
                        "samples": [
                            {
                                "id": f"{predicate_id}-1",
                                "executed": True,
                                "passed": True,
                                "state": "PASS",
                            }
                        ],
                        "raw": raw,
                    }
                    state_name = "PASS"
                except Exception as exc:
                    payload = {
                        "schema": RAW_SCHEMA,
                        "measurement_schema": MEASUREMENT_SCHEMA,
                        "layer": layer,
                        "candidate_sha": candidate_sha,
                        "gate": gate,
                        "id": predicate_id,
                        "producer": {"family": family, "implementation": "candidate-owned"},
                        "samples": [
                            {
                                "id": f"{predicate_id}-1",
                                "executed": True,
                                "passed": False,
                                "state": "FAIL",
                            }
                        ],
                        "raw": {
                            "measurement_state": "FAIL",
                            "failure_code": type(exc).__name__,
                        },
                    }
                    state_name = "FAIL"
            _write_json_once(raw_dir / _artifact_name(layer, gate, predicate_id), payload)
            predicates.append(
                {
                    "gate": gate,
                    "id": predicate_id,
                    "family": family,
                    "state": state_name,
                    "reason_codes": list(reasons),
                }
            )
    finally:
        if campaign is not None:
            campaign.close()
    campaign_artifacts = _snapshot_campaign_artifacts(campaign, raw_dir)
    counts = {
        name: sum(item["state"] == name for item in predicates)
        for name in ("PASS", "FAIL", "UNMEASURED")
    }
    state = {
        "schema": MEASUREMENT_SCHEMA,
        "layer": layer,
        "candidate_sha": candidate_sha,
        "qualified": counts["PASS"] == len(predicates),
        "counts": {
            "required": len(predicates),
            "executed": counts["PASS"] + counts["FAIL"],
            "passed": counts["PASS"],
            "failed": counts["FAIL"],
            "unmeasured": counts["UNMEASURED"],
        },
        "predicates": predicates,
        "campaign_artifacts": list(campaign_artifacts),
    }
    _write_json_once(raw_dir / "measurement-state.json", state)
    return state
