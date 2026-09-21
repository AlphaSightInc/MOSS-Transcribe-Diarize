"""Required SKIP must remain visible and cannot grant CLI or bundle acceptance."""
import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from tests.e2e.verify_workspace import (
    Harness,
    required_rows_verdict,
    retained_metadata,
    target_speaker_labels_updated,
    verdict_exit_code,
)
from tools.qualify.run import Bundle, bundle_verdict
from moss_transcribe_diarize import phase2_acceptance as acceptance
from tests.phase2.test_wave1_qualification import _capacity_raw


def _two_meeting_capacity_raw():
    raw = _capacity_raw()
    raw["sessions"] = 2
    raw["session_observations"] = raw["session_observations"][:2]
    raw["wrong_owner_observations"] = [
        item
        for item in raw["wrong_owner_observations"]
        if item["session_ordinal"] <= 2
    ]
    raw["transcript_lag_seconds"] = {
        key: value
        for key, value in raw["transcript_lag_seconds"].items()
        if key in {"s0", "s1"}
    }
    events = sorted(
        (
            {
                "session_id": str(session["session_ordinal"]),
                "kind": event["kind"],
                "payload": {
                    key: value for key, value in event.items() if key != "kind"
                },
            }
            for session in raw["session_observations"]
            for event in session["events"]
            if event["kind"].startswith("canonical_")
        ),
        key=lambda event: event["payload"]["runtime_monotonic_ns"],
    )
    raw["fairness_observation"] = acceptance.canonical_lifecycle_fairness(
        events, {"1", "2"}, maximum_skew=1
    )
    return raw


def test_two_meeting_capacity_is_the_supported_population():
    assert acceptance._validate_capacity({"raw": _two_meeting_capacity_raw()})


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_peer",
        "wrong_owner",
        "missing_owner_probe",
        "sample_accounting_loss",
        "lag_violation",
        "false_fairness",
        "false_real_time_factor",
        "missing_event_time",
    ],
)
def test_two_meeting_capacity_retains_all_eight_violating_controls(mutation):
    raw = copy.deepcopy(_two_meeting_capacity_raw())
    if mutation == "missing_peer":
        raw["session_observations"].pop()
    elif mutation == "wrong_owner":
        raw["wrong_owner_observations"][0]["foreign_matches"] = 1
    elif mutation == "missing_owner_probe":
        raw["wrong_owner_observations"].pop()
    elif mutation == "sample_accounting_loss":
        raw["session_observations"][0]["accounted_samples"] -= 1
    elif mutation == "lag_violation":
        raw["session_observations"][0]["lags"] = [11.0, 11.0]
    elif mutation == "false_fairness":
        raw["fairness_observation"]["passes"] = False
    elif mutation == "false_real_time_factor":
        raw["prestop_inference_rtf"] = 0.1
    else:
        del raw["session_observations"][0]["events"][0]["runtime_monotonic_ns"]

    assert not acceptance._validate_capacity({"raw": raw})


@pytest.mark.parametrize('statuses,verdict,code', [
    (['PASS'], 'PASS', 0), (['SKIP'], 'INCOMPLETE', 2),
    (['PASS', 'SKIP'], 'INCOMPLETE', 2), (['FAIL', 'SKIP'], 'FAIL', 1),
    ([], 'INCOMPLETE', 2),
])
def test_required_workspace_rows(statuses, verdict, code):
    rows = {str(i): {'status': status} for i, status in enumerate(statuses)}
    assert required_rows_verdict(rows) == verdict
    assert verdict_exit_code(verdict) == code
    assert retained_metadata({'verdict': verdict}) == {'verdict': verdict}


def test_rename_oracle_scopes_equal_display_names_to_acknowledged_id():
    rendered = [
        ('speaker-a', 'E2E Morgan'),
        ('speaker-a', 'E2E Morgan'),
        ('speaker-b', 'E2E Rowan'),
        ('speaker-b', 'E2E Rowan'),
    ]
    labels = [label for _, label in rendered]
    assert not ('E2E Morgan' in labels and 'E2E Rowan' not in labels)
    assert target_speaker_labels_updated(rendered, 'speaker-a', 'E2E Morgan')


def test_rename_oracle_rejects_any_stale_label_for_acknowledged_id():
    rendered = [
        ('speaker-a', 'E2E Morgan'),
        ('speaker-a', 'E2E Rowan'),
        ('speaker-b', 'E2E Rowan'),
    ]
    assert not target_speaker_labels_updated(rendered, 'speaker-a', 'E2E Morgan')


def test_missing_relay_runs_real_summary_check_and_retains_skip(tmp_path):
    h = object.__new__(Harness)
    h.out, h.row, h.state = tmp_path, None, {'rows': {}}
    async def api(*args): return {'body': {'data': []}}
    async def snapshot(*args): return None
    h.api, h.snapshot = api, snapshot
    asyncio.run(h.check(9, h.summaries))
    assert h.state['rows']['9']['status'] == 'SKIP'
    assert json.loads((tmp_path/'results.json').read_text())['rows']['9']['status'] == 'SKIP'
    assert verdict_exit_code(required_rows_verdict(h.state['rows'])) == 2


@pytest.mark.parametrize('gates,verdict', [
    ([{'status': 'PASS'}, {'status': 'SKIP'}], 'INCOMPLETE'),
    ([{'status': 'PASS'}, {'status': 'SKIP', 'required': False}], 'PASS'),
    ([{'status': 'UNRUNNABLE'}], 'INCOMPLETE'),
    ([{'status': 'FAIL'}, {'status': 'SKIP'}], 'FAIL'),
])
def test_bundle_required_and_optional(gates, verdict):
    assert bundle_verdict(gates) == verdict


def test_bundle_workspace_cannot_accept_missing_key(tmp_path):
    b = object.__new__(Bundle)
    b.work, b.has_summary_key = tmp_path, False
    gates = []
    b.gate = lambda name, status, *a, **kw: gates.append({'name': name, 'status': status, **kw})
    class StopAfterWorkspace(Exception): pass
    def command(name, *args, **kwargs):
        if name != 'workspace': raise StopAfterWorkspace
        output = tmp_path/'workspace'
        output.mkdir()
        (output/'results.json').write_text(json.dumps({'rows': {
            str(i): {'status': 'PASS'} for i in range(1,15) if i != 9}}))
        return 0, 0, None
    b.command = command
    with pytest.raises(StopAfterWorkspace): b.benches(True)
    assert gates[0]['status'] == 'INCOMPLETE'
    assert next(g for g in gates if g['name'] == 'workspace_row_9')['status'] == 'SKIP'
    assert bundle_verdict(gates) == 'INCOMPLETE'


def test_shell_preserves_incomplete_exit(tmp_path):
    fake_python = tmp_path/'incomplete-python'
    fake_python.write_text('#!/bin/sh\nexit 2\n')
    fake_python.chmod(0o755)
    result = subprocess.run(['bash', 'scripts/mvpfix-qualify.sh'],
        env={**os.environ, 'MOSS_QUALIFY_PYTHON': str(fake_python)})
    assert result.returncode == 2


@pytest.mark.parametrize('status,verdict', [('PASS', 'PASS'), ('SKIP', 'INCOMPLETE'), ('FAIL', 'FAIL')])
def test_real_bundle_cleanup_records_overall_verdict(tmp_path, status, verdict, monkeypatch):
    import tools.qualify.run as module
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    b = object.__new__(Bundle)
    b.processes, b.handles, b.proxy, b.monitor = [], [], None, None
    b.monitor_stop = SimpleNamespace(set=lambda: None)
    b.args = SimpleNamespace(budget=1, compare=None)
    b.out = tmp_path/'bundle'
    b.data = {'gates': [{'name': 'summary', 'status': status}]}
    b.gate = lambda name, status, **kw: b.data['gates'].append({'name': name, 'status': status})
    b.flush = lambda: None
    b.cleanup()
    assert b.data['verdict'] == verdict
    assert b.data['qualified'] is (verdict == 'PASS')


def test_budget_rejection_censors_quality_verdict_and_retains_request_counts(tmp_path, monkeypatch):
    """A refused decoder request means quality was not fully observed, not that it failed."""
    import tools.qualify.run as module
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    b = object.__new__(Bundle)
    b.processes, b.handles, b.monitor = [], [], None
    b.monitor_stop = SimpleNamespace(set=lambda: None)
    proxy_log = tmp_path / 'decoder.jsonl'
    proxy_log.write_text(''.join(json.dumps(event) + '\n' for event in (
        {'kind': 'start', 'row': 'quality', 'request_id': 'request-1', 'active': 1},
        {'kind': 'end', 'row': 'quality', 'request_id': 'request-1', 'active': 0},
        {'kind': 'start', 'row': 'quality', 'request_id': 'request-2', 'active': 1},
        {'kind': 'end', 'row': 'quality', 'request_id': 'request-2', 'active': 0},
        {'kind': 'reject', 'row': 'quality', 'request_id': 'request-3', 'active': 0},
    )))
    b.proxy = SimpleNamespace(
        sent=2,
        completed=2,
        upstream_failed=0,
        rejected=1,
        peak=1,
        active=0,
        log=proxy_log,
        close=lambda: None,
    )
    b.args = SimpleNamespace(budget=2, compare=None)
    b.out = tmp_path/'bundle'
    b.data = {'gates': [{'name': 'quality', 'status': 'FAIL'}]}
    b.gate = lambda name, status, **kw: b.data['gates'].append({'name': name, 'status': status})
    b.flush = lambda: None

    b.cleanup()

    assert b.data['decoder']['accepted_requests'] == 2
    assert b.data['decoder']['completed_requests'] == 2
    assert b.data['decoder']['rejected_by_budget'] == 1
    assert b.data['budget_censored'] is True
    assert b.data['verdict'] == 'INCOMPLETE'
    assert b.data['qualified'] is False
