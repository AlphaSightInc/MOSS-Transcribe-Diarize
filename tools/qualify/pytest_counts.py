"""Count actual pytest reports; never retain assertion bodies or fixture content."""
import json
import os
from pathlib import Path

state = dict(collected=0, executed=0, passed=0, failed=0, skipped=0, errors=0,
             deselected=0, failure_names=[], subtests=0)
seen = set()
outcomes = {}


def pytest_collection_finish(session):
    state['collected'] = len(session.items)


def pytest_deselected(items):
    state['deselected'] += len(items)


def pytest_collectreport(report):
    if report.failed:
        state['errors'] += 1
        state['failure_names'].append(report.nodeid)


def pytest_runtest_logreport(report):
    if hasattr(report, 'context'):
        state['subtests'] += 1
        if report.failed:
            outcomes[report.nodeid] = 'failed'
        return
    seen.add(report.nodeid)
    if report.failed:
        outcomes[report.nodeid] = 'failed'
    elif report.skipped and outcomes.get(report.nodeid) != 'failed':
        outcomes[report.nodeid] = 'skipped'
    elif report.when == 'call' and report.passed and report.nodeid not in outcomes:
        outcomes[report.nodeid] = 'passed'


def pytest_sessionfinish(session, exitstatus):
    state['reported'] = len(seen)
    state['executed'] = len(seen) - sum(value == 'skipped' for value in outcomes.values())
    for status in ('passed', 'failed', 'skipped'):
        state[status] = sum(value == status for value in outcomes.values())
    state['failure_names'] += sorted(k for k, v in outcomes.items() if v == 'failed')
    state['exit_code'] = int(exitstatus)
    Path(os.environ['MOSS_QUALIFY_COUNTS']).write_text(json.dumps(state, indent=2)+'\n')
