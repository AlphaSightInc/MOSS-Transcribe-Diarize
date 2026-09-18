"""Accepted Stop transfers outcome authority from helper to server."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('wp15_stop_bench', Path(__file__).resolve().parents[2] / 'prototypes/stop-lease/run.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

@pytest.mark.parametrize('stage', ['drain', 'terminal'])
@pytest.mark.parametrize('case', ['continue', 'depart', 'deadline', 'outage', 'failure', 'disconnect'])
def test_accepted_stop_outlives_capture_lease(tmp_path, case, stage):
    measured = bench.exercise(tmp_path, case, delay=90, stage=stage, emit=lambda _: None)
    result = measured['result']
    assert result['case_pass'], result
    assert result['restart_status'] == 'completed'
    assert result['restart_document_equal']
    assert result['restart_words'] == result['saved_words']
    assert result['accepted_samples'] == result['accounted_samples']
    prefix = measured['trace'][0]
    assert prefix['saved_words'] > 0
    if case == 'failure':
        assert result['saved_words'] >= prefix['saved_words']
    if case == 'deadline':
        expired = next(r for r in measured['trace'] if r['action']=='caller_wait_expired')
        assert (expired['http_status'],expired['code']) == (202,'stop_in_progress')
