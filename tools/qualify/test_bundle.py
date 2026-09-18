"""Qualification orchestration tests: real local HTTP, no GPU dispatch."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from tools.qualify.decoder import Decoder
from tools.qualify.run import compare, counts, score_ladder


def test_missing_is_not_pass():
    assert counts(['PASS','FAIL','UNRUNNABLE','SKIP']) == dict(
        expected=4, executed=2, passed=1, failed=1, skipped=1, unrunnable=1)


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
        assert len(received)==2 and proxy.sent==2 and proxy.rejected==1 and proxy.peak==1
        assert proxy.active==0
        log=(tmp_path/'requests.jsonl').read_text()
        assert 'PRIVATE' not in log
        assert [json.loads(line)['kind'] for line in log.splitlines()]==['start','end','start','end']
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
               exports={fmt:{'ok':True} for fmt in ('md','txt','json','srt','vtt')})
    assert file_passed(row,'six.wav')
    row['exports'].pop('vtt')
    assert not file_passed(row,'six.wav')


def test_unrunnable_bench_is_never_green_or_invented_failure():
    from tools.qualify.run import aggregate
    assert aggregate(['UNRUNNABLE']*16,1)=='UNRUNNABLE'
    assert aggregate(['PASS','UNRUNNABLE'],1)=='UNRUNNABLE'
    assert aggregate(['PASS','FAIL'],1)=='FAIL'
    assert aggregate(['PASS']*16,0)=='PASS'
