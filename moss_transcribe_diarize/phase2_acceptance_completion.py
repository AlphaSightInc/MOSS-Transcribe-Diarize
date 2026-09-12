"""Concrete completion-wave measurements; no caller-authored pass reports."""
from __future__ import annotations

from .phase2_acceptance_replay import ACCEPTANCE_STOP_DEADLINE_SECONDS

import json
import math
import subprocess
import sys
from pathlib import Path

VOICEPRINT_CHECKS = {
    "private_initial_bank", "manual_enrollment", "compatible_profile", "recognized_new_meeting",
    "no_automatic_enrollment", "active_bank_rename", "same_workspace_convergence",
    "stopped_history_frozen", "foreign_routes_refused", "exact_delete", "recorded_names_preserved",
    "duplicate_label_isolation",
}
SUMMARY_CHECKS = {
    "trusted_tls", "real_cors_preflight", "owner_payloads_only", "no_settings_to_moss",
    "no_ambient_credentials", "history_does_not_infer", "foreign_routes_refused",
    "durable_results", "manual_title_preserved", "serial_worker", "cancel_late_result",
    "four_identical_deliveries", "retry_intervals", "invalid_output_no_repair", "cancel_retry_wait",
    "load_overlaps_provider", "speech_capacity_unchanged",
    "lifecycle_events", "relay_path_qualified",
}


RELAY_SUMMARY_CHECKS = {
    "same_origin_request", "configured_model", "token_floor", "owner_transcript_only",
    "no_ambient_credentials", "durable_result",
}


def validate_relay_summary_observation(raw):
    return (isinstance(raw, dict) and raw.get("upstream_requests") == 1
        and isinstance(raw.get("checks"), dict) and set(raw["checks"]) == RELAY_SUMMARY_CHECKS
        and all(value is True for value in raw["checks"].values()))


def validate_completion_observation(predicate_id: str, raw: object) -> bool:
    if not isinstance(raw, dict): return False
    if predicate_id == "voiceprint_production_rule":
        if raw.get("fresh_embeddings") is not True or raw.get("production_rule") is not True: return False
        if raw.get("model_sha256") != "5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8": return False
        expected = {"causal": (470, 441, 29), "terminal_truth_aligned": (14, 14, 0)}
        results = raw.get("results")
        if not isinstance(results, dict) or set(results) != set(expected): return False
        for name, (total, correct, abstain) in expected.items():
            surface = results[name]
            if not isinstance(surface, dict): return False
            rows = surface.get("observations")
            if not isinstance(rows, list) or len(rows) != total or any(not isinstance(row, dict) for row in rows): return False
            if any(not {"id", "truth", "known", "unknown", "seconds"} <= set(row) or not isinstance(row["id"], str) for row in rows): return False
            if len({row.get("id") for row in rows}) != total: return False
            if any(not isinstance(row.get("truth"), str) or not row["truth"] for row in rows): return False
            if sum(row.get("known") == row["truth"] for row in rows) != correct: return False
            if sum(row.get("known") is None for row in rows) != abstain: return False
            if any(row.get("unknown") is not None for row in rows): return False
            counts = {"total": total, "known_correct": correct, "known_abstain": abstain, "known_wrong": 0, "unknown_abstain": total, "unknown_false": 0}
            if surface.get("counts") != counts: return False
        return raw.get("profiles") == 5 and raw.get("enrollment_samples") == 14
    expected = VOICEPRINT_CHECKS if predicate_id == "voiceprint_workspace_behavior" else SUMMARY_CHECKS if predicate_id == "browser_final_summary" else None
    if expected is None or not isinstance(raw.get("checks"), dict): return False
    if set(raw["checks"]) != expected or not all(value is True for value in raw["checks"].values()): return False
    if predicate_id == "browser_final_summary":
        if not validate_relay_summary_observation(raw.get("relay")): return False
        from .phase2_acceptance import _validate_capacity
        if not isinstance(raw.get("capacity"), dict) or not _validate_capacity({"raw": raw["capacity"]}): return False
        deliveries = raw.get("retry_deliveries")
        if not isinstance(deliveries, list) or len(deliveries) != 4: return False
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in deliveries): return False
        # Times come from the fake provider's monotonic clock, not browser claims.
        if any(deliveries[i + 1] - deliveries[i] < delay for i, delay in enumerate((60, 120, 240))): return False
        events = raw.get("events")
        if not isinstance(events, list) or len(events) != 2 or any(not isinstance(group, list) for group in events): return False
        flattened = [item for group in events for item in group if isinstance(item, dict)]
        if not {"queued", "generating", "retry_wait", "failed", "cancelled", "current"} <= {row.get("state") for row in flattened if row.get("type") == "llm_status"}: return False
        if not any(row.get("type") == "llm_summary_update" and row.get("state") == "current" for row in flattened): return False
    return True


def measure_voiceprint_rule(campaign):
    repo = Path(campaign._text("repo_root"))
    output = campaign.artifact_root / "fresh-voiceprint-rule.json"
    if output.exists(): raise RuntimeError("Voiceprint measurement output already exists")
    completed = subprocess.run([sys.executable, str(repo / "prototypes/streaming-diarization/voice-profile-matching/measure_production_rule.py"),
        "--assets", campaign._text("voiceprint_assets"), "--output", str(output)], cwd=repo, capture_output=True, timeout=1800)
    if completed.returncode: raise RuntimeError("Fresh production voiceprint measurement failed")
    raw = json.loads(output.read_text())
    if not validate_completion_observation("voiceprint_production_rule", raw): raise RuntimeError("Accepted production rule did not reproduce")
    # The report explicitly retains its truth-aligned/development-corpus limitation.
    return raw


def measure_voiceprint_workspace(campaign):
    a, b, peer = campaign.a, campaign.b, campaign.a_peer
    checks = {}
    initial, _ = a.json("GET", "/api/voiceprints", 200)
    initial_b, _ = b.json("GET", "/api/voiceprints", 200)
    checks["private_initial_bank"] = initial["voiceprints"] == initial_b["voiceprints"] == []
    if not checks["private_initial_bank"]: raise RuntimeError("Qualification requires fresh voiceprint workspaces")
    created = []
    profiles_created = []
    def live(clip_index=0):
        value, _ = a.json("POST", "/api/live/sessions", 201, json={"echo_mode": "speakers"})
        created.append(value["id"])
        campaign._seed_live_transcript("a", value["id"], clip_index)
        meeting, _ = a.json("GET", f"/api/meetings/{value['id']}", 200)
        # The display-name map is empty before enrollment. Canonical IDs belong
        # to attributed transcript rows, independently of optional names.
        speaker = next(row["speaker_entity_id"] for row in meeting["transcript"]["segments"] if row.get("speaker_entity_id"))
        return value["id"], speaker
    try:
        first, speaker = live()
        enrolled, _ = a.json("PUT", f"/api/meetings/{first}/speakers/{speaker}/name", 200, json={"label": "Qualification speaker"})
        profile = enrolled.get("voiceprint_id")
        checks["manual_enrollment"] = enrolled.get("enrollment") == "enrolled" and isinstance(profile, str)
        if not checks["manual_enrollment"]: raise RuntimeError("Real Live evidence did not enroll a profile")
        profiles_created.append(profile)
        bank, _ = a.json("GET", "/api/voiceprints", 200)
        checks["compatible_profile"] = len(bank["voiceprints"]) == 1 and bank["voiceprints"][0].get("compatibility") == "compatible"
        samples = bank["voiceprints"][0]["sample_count"]
        second, second_speaker = live()
        snapshot, _ = a.json("GET", f"/api/live/sessions/{second}/snapshot", 200)
        checks["recognized_new_meeting"] = snapshot["speaker_labels"].get(second_speaker) == "Qualification speaker"
        bank, _ = a.json("GET", "/api/voiceprints", 200)
        checks["no_automatic_enrollment"] = len(bank["voiceprints"]) == 1 and bank["voiceprints"][0]["sample_count"] == samples
        duplicate_meeting, duplicate_speaker = live(1)
        duplicate, _ = a.json("PUT", f"/api/meetings/{duplicate_meeting}/speakers/{duplicate_speaker}/name", 200, json={"label": "Qualification speaker"})
        duplicate_id = duplicate.get("voiceprint_id")
        if not isinstance(duplicate_id, str) or duplicate_id == profile:
            raise RuntimeError("Distinct real speakers did not retain separate same-label profiles")
        profiles_created.append(duplicate_id)
        bank, _ = a.json("GET", "/api/voiceprints", 200)
        duplicate_row = next(row for row in bank["voiceprints"] if row["id"] == duplicate_id)
        a.json("POST", f"/api/live/sessions/{first}/stop", 200, json={"deadline": ACCEPTANCE_STOP_DEADLINE_SECONDS})
        frozen, _ = a.json("GET", f"/api/meetings/{first}", 200)
        campaign._summary_voiceprint_meeting = first
        a.json("PUT", f"/api/voiceprints/{profile}/name", 200, json={"label": "Renamed qualification speaker"})
        active, _ = a.json("GET", f"/api/live/sessions/{second}/snapshot", 200)
        checks["active_bank_rename"] = active["speaker_labels"].get(second_speaker) == "Renamed qualification speaker"
        bank, _ = a.json("GET", "/api/voiceprints", 200)
        duplicate_after = next(row for row in bank["voiceprints"] if row["id"] == duplicate_id)
        checks["duplicate_label_isolation"] = duplicate_after == duplicate_row and len(bank["voiceprints"]) == 2
        peer_view, _ = peer.json("GET", f"/api/meetings/{second}", 200)
        owner_view, _ = a.json("GET", f"/api/meetings/{second}", 200)
        checks["same_workspace_convergence"] = peer_view == owner_view
        stopped, _ = a.json("GET", f"/api/meetings/{first}", 200)
        checks["stopped_history_frozen"] = stopped == frozen
        statuses = [b.request("PUT", f"/api/voiceprints/{profile}/name", json={"label": "Foreign"}).status_code,
                    b.request("DELETE", f"/api/voiceprints/{profile}").status_code,
                    b.request("PUT", f"/api/meetings/{second}/speakers/{second_speaker}/name", json={"label": "Foreign"}).status_code]
        foreign, _ = b.json("GET", "/api/voiceprints", 200)
        checks["foreign_routes_refused"] = statuses == [404, 404, 404] and foreign["voiceprints"] == []
        a.json("DELETE", f"/api/voiceprints/{profile}", 200)
        bank, _ = a.json("GET", "/api/voiceprints", 200)
        checks["exact_delete"] = bank["voiceprints"] == [duplicate_row] and a.request("DELETE", f"/api/voiceprints/{profile}").status_code == 404
        after, _ = a.json("GET", f"/api/meetings/{second}", 200)
        stopped, _ = a.json("GET", f"/api/meetings/{first}", 200)
        checks["recorded_names_preserved"] = after == owner_view and stopped == frozen
    finally:
        for meeting in created:
            response = a.request("POST", f"/api/live/sessions/{meeting}/abort", json={})
            if response.status_code not in {200, 409}: raise RuntimeError("Voiceprint qualification cleanup failed")
        for profile in profiles_created:
            response = a.request("DELETE", f"/api/voiceprints/{profile}")
            if response.status_code not in {200, 404}: raise RuntimeError("Voiceprint profile cleanup failed")
    raw = {"checks": checks, "live_meetings": len(created), "foreign_statuses": statuses}
    if not validate_completion_observation("voiceprint_workspace_behavior", raw): raise RuntimeError("Live voiceprint workspace behavior failed")
    return raw
