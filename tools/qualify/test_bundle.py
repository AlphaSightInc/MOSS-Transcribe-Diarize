"""Qualification orchestration tests: real local HTTP, no GPU dispatch."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import runpy
from types import SimpleNamespace
import threading
import pytest
from tools.qualify import run as qualify_run
from tools.qualify.decoder import Decoder
from tools.qualify.run import compare, counts, score_ladder


FEATURE_ROW = qualify_run.ROOT / "prototypes/feature-rows/run.py"
S17_ROW = qualify_run.ROOT / "prototypes/s17-identity-rerun/run.py"


def test_summary_only_row_plans_three_decoder_and_six_provider_calls():
    feature_row = runpy.run_path(str(FEATURE_ROW))
    plan = feature_row["summary_plan"]()
    assert [clip["planned_decoder"] for clip in plan["clips"]] == [1, 2]
    assert plan["planned_decoder"] == 3
    assert plan["planned_provider"] == 6
    assert plan["provider_cap"] == {
        "already_spent": 2,
        "this_row": 6,
        "cumulative": 8,
        "cap": 10,
    }
    assert plan["capacity_2x1800"] == "REQUIRED-NOT-RUN"


def test_s17_missing_raw_capture_is_incomplete_not_pass():
    s17_row = runpy.run_path(str(S17_ROW))
    receipt = s17_row["incomplete_capture_receipt"](
        "gap", "capture emitted no terminal rows for gap; receipt falsified"
    )
    assert receipt == {
        "schema": "moss-r4-s17-identity-partition-receipt.v3",
        "case": "gap",
        "status": "INCOMPLETE",
        "reason": "capture emitted no terminal rows for gap; receipt falsified",
    }


def test_s17_partition_receipt_rejects_missing_raw_stream():
    s17_row = runpy.run_path(str(S17_ROW))
    with pytest.raises(RuntimeError, match="lacks one or more required streams"):
        s17_row["partition_receipt"]("gap", [])


def test_summary_row_counter_mismatch_is_incomplete():
    feature_row = runpy.run_path(str(FEATURE_ROW))
    counters = feature_row["ProxyCounters"]
    accounting = feature_row["decoder_accounting"]
    before = counters(accepted=8, completed=8, rejected=1, event_count=17)
    healthy = counters(
        accepted=11,
        completed=11,
        rejected=1,
        peak_in_flight=2,
        event_count=23,
        row_attempted=3,
        row_completed=3,
        distinct_attempt_ids=3,
        distinct_completed_attempt_ids=3,
        row_owners=("summaries",),
    )
    violating = counters(
        accepted=12,
        completed=11,
        rejected=1,
        peak_in_flight=2,
        event_count=24,
        row_attempted=4,
        row_completed=3,
        distinct_attempt_ids=4,
        distinct_completed_attempt_ids=3,
        row_owners=("summaries",),
    )
    receipt, matches = accounting(before, healthy, planned_decoder=3)
    assert receipt["decoder_proxy_counter_deltas"] == {
        "accepted": 3,
        "completed": 3,
        "upstream_failed": 0,
        "client_write_failed": 0,
        "rejected": 0,
        "peak_in_flight": 2,
        "distinct_attempt_ids": 3,
        "distinct_completed_attempt_ids": 3,
        "distinct_client_request_ids": 0,
        "duplicate_attempts": 0,
        "unowned_events": 0,
        "missing_client_request_ids": 0,
        "wrong_row_events": 0,
        "row_owners": ["summaries"],
        "reconciled": True,
    }
    assert matches is True
    _, matches = accounting(before, violating, planned_decoder=3)
    assert matches is False


def test_summary_row_reads_rejections_and_row_local_peak(tmp_path):
    feature_row = runpy.run_path(str(FEATURE_ROW))
    log = tmp_path / "decoder.jsonl"
    events = [
        {"kind": "start", "active": 1},
        {"kind": "end", "active": 0},
        {"kind": "start", "active": 1},
        {"kind": "start", "active": 2},
        {"kind": "end", "active": 1},
        {"kind": "end", "active": 0},
        {"kind": "reject", "active": 0},
    ]
    log.write_text("".join(json.dumps(event) + "\n" for event in events))
    counters = feature_row["proxy_counters"](log, peak_since=2)
    assert (counters.accepted, counters.completed, counters.rejected) == (3, 3, 1)
    assert counters.peak_in_flight == 2


def test_missing_is_not_pass():
    assert counts(['PASS','FAIL','UNRUNNABLE','SKIP']) == dict(
        expected=4, executed=2, passed=1, failed=1, skipped=1, unrunnable=1)


def test_request_plan_uses_selected_gate_population_and_retains_provenance():
    default = qualify_run.request_plan(long=False)
    assert default['measured_rate'] == .51
    assert default['measured_rate_unit'] == 'requests_per_lane_second'
    assert default['source_receipt'] == 'evidence/mvpfix/wp30/20260918-055122-1r-4x600/requests.jsonl'
    assert default['headroom'] == 1.25
    assert default['headroom_provenance'] == {
        'status': 'UNMEASURED',
        'source': 'planner_policy',
        'source_receipt': None,
        'calculation': '1.25 policy multiplier; no receipt-derived arithmetic',
        'reason': 'no retained receipt isolates planner error after the lane-second rate correction',
    }
    population = default['population']
    assert set(population['live_benches']) == {
        'workspace', 'demo_lanes', 'lifecycle', 'reshare',
        'identity_stress', 'level_ladder', 'browser_stress_all',
        'capacity_2x300',
    }
    assert population['live_benches']['capacity_2x300']['session_seconds'] == [300, 300]
    assert population['live_benches']['capacity_2x300']['lanes_per_session'] == [2, 2]
    assert population['live_benches']['level_ladder']['lanes_per_session'] == [2] * 6
    assert population['live_benches']['lifecycle']['lanes_per_session'] == [2, 2, 2, 0, 1, 1]
    assert population['live_sessions'] == 41
    assert population['live_session_seconds'] == 1729
    assert population['live_lane_seconds'] == 3457
    assert population['file_seconds'] == [50, 50, 360, 180, 180, 180]
    assert population['file_windows'] == 11
    assert population['window_seconds'] == 150
    assert population['stride_seconds'] == 120
    assert population['browser_cases'] == list(range(1, 17))
    assert default['request_derivation'] == {
        'live_lane_requests': 1763.07,
        'file_window_requests': 11,
        'browser_case_requests': 16,
        'unadjusted_requests': 1790.07,
        'calculation': 'ceil((3457 lane_seconds * 0.51 requests_per_lane_second + 11 file_window_requests + 16 browser_case_requests) * 1.25 headroom)',
    }
    assert default['planned_requests'] == 2238

    long = qualify_run.request_plan(long=True)
    assert 'capacity_2x300' not in long['population']['live_benches']
    assert long['population']['live_benches']['capacity_2x1800']['session_seconds'] == [1800, 1800]
    assert long['population']['live_benches']['capacity_2x1800']['lanes_per_session'] == [2, 2]
    assert long['population']['live_sessions'] == 41
    assert long['population']['live_session_seconds'] == 4729
    assert long['population']['live_lane_seconds'] == 9457
    assert long['population']['file_windows'] == 26
    assert long['planned_requests'] == 6082


def test_measured_request_rate_recomputes_from_each_retained_receipt():
    plan = qualify_run.request_plan(long=False)
    assert plan['source_receipt'] == plan['measured_rate_evidence'][0]['source_receipt']
    for evidence in plan['measured_rate_evidence']:
        receipt = qualify_run.ROOT / evidence['source_receipt']
        rows = [json.loads(line) for line in receipt.read_text().splitlines()]
        result = json.loads((receipt.parent / 'result.json').read_text())
        unique_requests = {row['request'] for row in rows}
        assert len(rows) == len(unique_requests) == evidence['unique_request_ids']
        assert result['sessions'] == evidence['sessions']
        assert result['seconds'] == evidence['seconds_per_session']
        rate = len(unique_requests) / (
            evidence['sessions'] * evidence['lanes_per_session'] * evidence['seconds_per_session']
        )
        assert round(rate, 2) == plan['measured_rate'] == evidence['rounded_rate']


def test_bundle_summary_records_unmeasured_headroom_provenance(monkeypatch, tmp_path):
    plan = qualify_run.request_plan(long=False)
    monkeypatch.setattr(qualify_run, 'ROOT', tmp_path)
    args = SimpleNamespace(
        decoder_upstream_port=18125,
        out=tmp_path / 'out',
        budget=plan['planned_requests'],
        long=False,
    )

    bundle = qualify_run.Bundle(args, plan)
    bundle.flush()

    summary = json.loads((bundle.out / 'summary.json').read_text())
    assert summary['headroom_provenance'] == plan['headroom_provenance']
    markdown = (bundle.out / 'summary.md').read_text()
    assert 'Headroom: 1.25.' in markdown
    assert '"status":"UNMEASURED"' in markdown
    assert '"source_receipt":null' in markdown


def test_unfunded_plan_refuses_before_bundle_or_decoder_start(monkeypatch, capsys):
    def forbidden_start(*args, **kwargs):
        raise AssertionError('bundle started before budget admission')

    monkeypatch.setattr(qualify_run, 'Bundle', forbidden_start)
    assert qualify_run.main(['--budget', '2237']) == 2
    error = capsys.readouterr().err
    assert 'planned_requests=2238' in error
    assert 'shortfall=1' in error


def test_default_budget_funds_default_but_not_long_population(monkeypatch, capsys):
    class DefaultPlanReached(Exception):
        pass

    def capture_default(args, plan):
        assert args.budget == plan['planned_requests'] == 2238
        raise DefaultPlanReached

    monkeypatch.setattr(qualify_run, 'Bundle', capture_default)
    with pytest.raises(DefaultPlanReached):
        qualify_run.main([])
    assert qualify_run.main(['--long']) == 2
    assert 'planned_requests=6082 budget=2238 shortfall=3844' in capsys.readouterr().err


@pytest.mark.parametrize(('long', 'name', 'seconds'), [
    (False, 'capacity_2x300', '300'),
    (True, 'capacity_2x1800', '1800'),
])
def test_capacity_row_matches_selected_population(monkeypatch, tmp_path, long, name, seconds):
    monkeypatch.setattr(qualify_run, 'ROOT', tmp_path)
    bundle = object.__new__(qualify_run.Bundle)
    bundle.args = SimpleNamespace(long=long)
    bundle.work = tmp_path / 'work'
    bundle.work.mkdir()
    bundle.manifest = tmp_path / 'manifest.json'
    commands = []
    gates = []

    def command(command_name, argv, timeout):
        commands.append((command_name, argv, timeout))
        output = bundle.work / 'capacity'
        output.mkdir()
        (output / 'result.json').write_text(json.dumps({
            'clean': True,
            'session_results': [{'clean': True}, {'clean': True}],
        }))
        return 0, 1.0, None

    bundle.command = command
    bundle.gate = lambda gate_name, status, *args, **kwargs: gates.append((gate_name, status, args, kwargs))
    bundle.capacity(ready=True)

    assert len(commands) == 1
    command_name, argv, timeout = commands[0]
    assert command_name == name
    assert argv[argv.index('--sessions') + 1] == '2'
    assert argv[argv.index('--seconds') + 1] == seconds
    assert timeout == 3600
    assert [(gate_name, status) for gate_name, status, _, _ in gates][:1] == [(name, 'PASS')]
    if long:
        assert len(gates) == 1
    else:
        assert [(gate_name, status) for gate_name, status, _, _ in gates][1:] == [
            ('capacity_2x1800', 'REQUIRED-NOT-RUN'),
        ]


def test_default_summary_retains_required_long_capacity_when_stack_is_unavailable():
    bundle = object.__new__(qualify_run.Bundle)
    bundle.args = SimpleNamespace(long=False)
    gates = []
    bundle.gate = lambda name, status, *args, **kwargs: gates.append((name, status, args))

    bundle.capacity(ready=False)

    assert [(name, status) for name, status, _ in gates] == [
        ('capacity_2x300', 'UNRUNNABLE'),
        ('capacity_2x1800', 'REQUIRED-NOT-RUN'),
    ]
    assert gates[1][2][0] == {
        'expected': 2, 'executed': 0, 'passed': 0,
        'failed': 0, 'skipped': 2, 'unrunnable': 0,
    }


@pytest.mark.parametrize(('row10_status', 'workspace_status', 'verdict'), [
    ('BEST_EFFORT_FAIL', 'PASS', 'PASS'),
    ('FAIL', 'FAIL', 'FAIL'),
])
def test_workspace_row10_best_effort_is_visible_but_only_plain_fail_blocks_bundle(
    tmp_path, row10_status, workspace_status, verdict,
):
    bundle = object.__new__(qualify_run.Bundle)
    bundle.work, bundle.has_summary_key = tmp_path, True
    gates = []
    bundle.gate = lambda name, status, *args, **kwargs: gates.append(
        {'name': name, 'status': status, **kwargs}
    )

    class StopAfterWorkspace(Exception):
        pass

    def command(name, *_args, **_kwargs):
        if name != 'workspace':
            raise StopAfterWorkspace
        output = tmp_path / 'workspace'
        output.mkdir()
        rows = {str(index): {'status': 'PASS'} for index in range(1, 15)}
        rows['10'] = {
            'status': row10_status,
            'reason_code': 'all_five_recognition_attempts_missed_bound'
            if row10_status == 'BEST_EFFORT_FAIL' else 'bank_missing_name',
        }
        (output / 'results.json').write_text(json.dumps({'rows': rows}))
        return 0, 0, None

    bundle.command = command
    with pytest.raises(StopAfterWorkspace):
        bundle.benches(True)

    workspace = next(gate for gate in gates if gate['name'] == 'workspace')
    row10 = next(gate for gate in gates if gate['name'] == 'workspace_row_10')
    assert workspace['status'] == workspace_status
    assert row10['status'] == row10_status
    assert row10.get('required', True) is (row10_status != 'BEST_EFFORT_FAIL')
    assert qualify_run.bundle_verdict(gates) == verdict


def test_determinism_detects_added_removed_and_changed_gates():
    before={'gates':[{'name':'a','status':'PASS'},{'name':'b','status':'FAIL'}]}
    after={'gates':[{'name':'a','status':'FAIL'},{'name':'c','status':'PASS'}]}
    assert compare(before,after)==[
        {'name':'a','before':'PASS','after':'FAIL'},
        {'name':'b','before':'FAIL','after':None},
        {'name':'c','before':None,'after':'PASS'}]


def test_ladder_unique_denominators_exclude_shared_and_content():
    rows=[dict(case=case,_tokens_by_speaker={'s':tokens}) for case,tokens in [
        ('system@1',['shared','alpha','beta']),('mic@1',['shared','gamma']),
        ('overlap@1',['shared','alpha','gamma'])]]
    result=score_ladder(rows)
    assert result[-1]['retention_vs_alone']['system']==dict(retained=1,alone_unique=2,fraction=.5)
    assert result[-1]['retention_vs_alone']['microphone']==dict(retained=1,alone_unique=1,fraction=1)
    assert 'alpha' not in json.dumps(result)
    assert '_tokens_by_speaker' not in json.dumps(result)


def test_proxy_caps_real_dispatch_and_records_no_body(tmp_path):
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=upstream.serve_forever,daemon=True); thread.start()
    proxy=Decoder(0,upstream.server_port,2,tmp_path/'requests.jsonl'); proxy.start()
    try:
        statuses=[]
        for _ in range(3):
            conn=http.client.HTTPConnection('127.0.0.1',proxy.server.server_port)
            conn.request('POST','/v1/audio/transcriptions',b'PRIVATE AUDIO PAYLOAD')
            response=conn.getresponse(); statuses.append(response.status); response.read(); conn.close()
        assert statuses==[200,200,429]
        assert (len(received), proxy.sent, proxy.completed, proxy.rejected, proxy.peak) == (2, 2, 2, 1, 1)
        assert proxy.active==0
        log=(tmp_path/'requests.jsonl').read_text()
        assert 'PRIVATE' not in log
        assert [json.loads(line)['kind'] for line in log.splitlines()]==[
            'start', 'end', 'start', 'end', 'reject'
        ]
    finally:
        proxy.close(); upstream.shutdown(); upstream.server_close(); thread.join()


def test_readiness_bootstraps_authenticated_workspace():
    from tools.qualify.run import ready_descriptor
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            calls.append(self.path)
            self.send_response(200); self.send_header('Set-Cookie','workspace=test'); self.end_headers()
            self.wfile.write(b'{}')
        def do_GET(self):
            calls.append(self.path)
            if self.headers.get('Cookie') != 'workspace=test':
                self.send_error(401); return
            self.send_response(200); self.end_headers()
            self.wfile.write(b'{"descriptor":{"source_revision":"test"}}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        assert ready_descriptor(f'http://127.0.0.1:{server.server_port}')=={'source_revision':'test'}
        assert calls==['/api/workspace/bootstrap','/api/live/descriptor']
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_identity_rejects_speaker_collapse_and_switching():
    from tools.qualify.run import identity_passed
    row=dict(status='completed',finalization='final',failure=None,
             score=dict(ids_by_truth={'A':{'one':8},'B':{'two':9}},id_switches={'A':0,'B':0},unresolved_segments=0))
    assert identity_passed(row)
    row['score']['ids_by_truth']['B']={'one':9}
    assert not identity_passed(row)
    row['score']['ids_by_truth']['B']={'two':9}
    row['score']['id_switches']['A']=1
    assert not identity_passed(row)
    assert not identity_passed({})


def test_identity_cannot_pass_by_omitting_one_reference_voice():
    from tools.qualify.run import identity_passed
    row=dict(status='completed',finalization='final',failure=None,
             score=dict(ids_by_truth={'A':{'one':8}},id_switches={'A':0},unresolved_segments=0))
    assert identity_passed(row,expected_voices=1)
    assert not identity_passed(row,expected_voices=2)


def test_file_gate_preserves_failure_and_export_bars():
    from tools.qualify.run import file_passed
    row=dict(foreign_read_status=404,history_reason=True,header_reason=True,reason_content_free=True,
             status='failed',reload_status='failed',failure_code='acquisition_http_404')
    assert file_passed(row,'missing')
    row['failure_code']='acquisition_failed'
    assert not file_passed(row,'missing')
    row.update(status='completed',reload_status='completed',mp3_link=True,mp3_bytes=10,
               exports={fmt:{'ok':True} for fmt in ('md','txt')})
    assert file_passed(row,'six.wav')
    row['exports'].pop('txt')
    assert not file_passed(row,'six.wav')


def test_unrunnable_bench_is_never_green_or_invented_failure():
    from tools.qualify.run import aggregate
    assert aggregate(['UNRUNNABLE']*16,1)=='UNRUNNABLE'
    assert aggregate(['PASS','UNRUNNABLE'],1)=='UNRUNNABLE'
    assert aggregate(['PASS','FAIL'],1)=='FAIL'
    assert aggregate(['PASS']*16,0)=='PASS'
