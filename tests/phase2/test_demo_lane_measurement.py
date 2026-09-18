import pytest
from tests.e2e.verify_demo_lanes import reference_inputs, run_case

@pytest.mark.parametrize('case', ['alternation','overlap'])
@pytest.mark.parametrize('missing', [None, 'pre_terminal', 'final', 'reopened'])
def test_lane_checks_reach_both_surfaces_and_reopen(case,missing):
    inputs=reference_inputs(1)
    rows=[dict(start=0 if lane=='system' or case=='overlap' else 29,
               end=29 if lane=='system' else 25 if case=='overlap' else 54,
               speaker=lane,source_lane=lane,text=data['reference']) for lane,data in inputs.items()]
    class Client:
        frames=0;heartbeats=0;stopped=False;snapshots=0;reads=0
        def call(self,method,path,body=None):
            if path.endswith('bootstrap'): return {}
            if path.endswith('descriptor'): return {'descriptor':dict(frame_samples=8000,sample_rate=16000,source_revision='fixture')}
            if path=='/api/live/sessions': return {'id':'test'}
            if path.endswith('heartbeat'): self.heartbeats+=1;return {}
            if path.endswith('frames'):
                assert len(body)==9 and body['sample_count']==8000
                self.frames+=1;return {}
            if path.endswith('stop'): self.stopped=True;assert body=={'deadline':30};return {}
            if path.endswith('snapshot'):
                name='final' if self.stopped else 'pre_terminal'
                self.snapshots+=1
                return {'snapshot':{'session':{'finalization_status':'final' if self.stopped else 'running','effective_transcript':rows[:1] if missing==name else rows}}}
            if path.startswith('/api/meetings/'):
                self.reads+=1
                return {'status':'completed','transcript':{'segments':rows[:1] if missing=='reopened' and self.reads==2 else rows}}
            raise AssertionError(path)
    client=Client()
    result=run_case('https://local.test',None,case,1,client=client,realtime=False)
    assert result['passed'] is (missing is None)
    assert client.frames==2*client.heartbeats and client.snapshots==2 and client.reads==2
    assert result['expected_failure'] is False


def test_neither_interruption_nor_quality_failure_is_accepted():
    from tests.e2e.verify_demo_lanes import accepted_case
    assert not accepted_case(dict(status='interrupted',finalization_status='failed',passed=False,expected_failure=True))
    assert not accepted_case(dict(status='completed',finalization_status='final',passed=False,expected_failure=True))
    assert accepted_case(dict(status='completed',finalization_status='final',passed=True,expected_failure=False))
