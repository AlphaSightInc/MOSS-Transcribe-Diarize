import pytest
from tests.e2e import verify_demo_lanes as demo
from tests.e2e.verify_demo_lanes import reference_inputs, run_case

@pytest.mark.parametrize('case', ['alternation','overlap'])
@pytest.mark.parametrize('missing', [None, 'pre_terminal', 'final', 'reopened'])
def test_lane_checks_reach_both_surfaces_and_reopen(case,missing,monkeypatch):
    old_score=demo.score_lanes
    def healthy_score(*args,**kwargs):
        score=old_score(*args,**kwargs)
        return {**score,'identity_unqualified':False,
                'unattributed_segment_count':0,'unattributed_word_count':0}
    monkeypatch.setattr(demo,'score_lanes',healthy_score)
    inputs=reference_inputs(1)
    rows=[dict(start=0 if lane=='system' or case=='overlap' else 29,
               end=len(data['pcm']) / (16000 * 2) if lane=='system' else 25 if case=='overlap' else 54,
               start_sample=0,end_sample=2_000_000,
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
                return {'snapshot':{'pending_work_items':0,'session':{
                    'status':'completed' if self.stopped else 'active',
                    'finalization_status':'final' if self.stopped else 'not_started',
                    'pending_span_ids':[],'committed_samples':2_000_000,
                    'effective_transcript':rows[:1] if missing==name else rows}}}
            if path.endswith('events?since_seq=-1'):
                return {'events':[
                    {'seq':1,'kind':'span_frozen','payload':{'span_id':1,'start_sample':0,'end_sample':2_000_000,'reason':'end_silence'}},
                    {'seq':2,'kind':'canonical_queued','payload':{'item_id':1}},
                    {'seq':3,'kind':'canonical_processed','payload':{'item_id':1,'span_id':1}},
                ]}
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
    healthy_surface={'identity_unqualified':False,
                     'unattributed_segment_count':0,'unattributed_word_count':0}
    assert accepted_case(dict(status='completed',finalization_status='final',passed=True,expected_failure=False,
                              identity_telemetry_missing=False,
                              surfaces={name:dict(healthy_surface)
                                        for name in ('pre_terminal','final','reopened')}))


def test_microphone_window_includes_source_sentence_tail_and_still_scores_additions():
    from moss_transcribe_diarize.lane_word_oracle import words, distance
    row = reference_inputs(1)['microphone']
    assert len(row['pcm']) == 25 * 16000 * 2
    assert row['reference'].startswith('Kind of the same thing.')
    assert len(words(row['reference'])) == 53
    assert distance(words(row['reference']), words(row['reference'] + ' invented words'))['additions'] == 2
