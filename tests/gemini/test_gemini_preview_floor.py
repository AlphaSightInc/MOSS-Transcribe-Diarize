"""R5B-A6: C1 count continuity, with D16's accepted rewrite loss explicit."""
import asyncio

import pytest

from moss_transcribe_diarize.app import gemini_live_runtime as rt
from test_gemini_preview_duplication import _runtime, _commit, COMMITTED, FRESH, R
from test_gemini_preview_snapshots import TimePreview, establish, preview


def _seed(runtime, lane='system'):
    # Solid omits a long old passage: clock proof establishes the full old cut.
    establish(runtime, lane=lane)
    assert preview(runtime, COMMITTED+' '+FRESH, 20, lane=lane)==FRESH
    return len(rt._preview_units(COMMITTED))


def _rewrite():
    # Alter the head and omit the frontier; neither current proof can recover N.
    return ' '.join(['rewritten']*len(rt._preview_units(COMMITTED)))+' '+FRESH


def _active_floor(runtime, lane='system'):
    n=_seed(runtime,lane)
    assert preview(runtime,_rewrite(),21,lane=lane)==FRESH
    values=runtime.engine_diagnostics('one')['preview'][lane]
    assert values['floor_hidden_units']==n
    assert values['floor_publications']==1
    assert values['time_hidden_last']==0
    assert all(isinstance(v,(int,float)) for v in values.values())
    return n


@pytest.mark.parametrize('lane',['system','microphone'])
def test_floor_c6s_shape_keeps_cut_when_current_text_and_clock_fail(tmp_path,lane):
    runtime=_runtime(tmp_path,lanes=True)
    n=_active_floor(runtime,lane)
    assert preview(runtime,_rewrite(),22,lane=lane)==FRESH
    values=runtime.engine_diagnostics('one')['preview'][lane]
    assert values['floor_hidden_units']==2*n and values['floor_publications']==2


def test_floor_retreating_confirmed_point_discards_count(tmp_path):
    runtime=_runtime(tmp_path)
    preview(runtime,COMMITTED,14)
    runtime.publish_update('one',rt.GeminiBase(40*R,(
        rt.GeminiSegment(0,40*R,COMMITTED,source_lane='system'),),degraded=True))
    assert preview(runtime,COMMITTED+' '+FRESH,45)==FRESH
    assert preview(runtime,_rewrite(),46)==FRESH
    runtime.publish_update('one',rt.GeminiRolling(0,40*R,(
        rt.GeminiSegment(0,10*R,'unrelated replacement','speaker-0001','system'),),
        revision_lanes=('system',)))
    assert preview(runtime,_rewrite(),47)==_rewrite()
    assert runtime.engine_diagnostics('one')['preview']['system']['floor_publications']==1


def test_floor_shrink_below_count_discards_it_permanently(tmp_path):
    runtime=_runtime(tmp_path)
    _active_floor(runtime)
    assert preview(runtime,'new short phrase',22)=='new short phrase'
    assert preview(runtime,_rewrite(),23)==_rewrite()


@pytest.mark.parametrize('reset',['final','removed','reopen','stop_new_meeting'])
def test_floor_existing_lifecycle_clears_count(tmp_path,reset):
    runtime=_runtime(tmp_path)
    _active_floor(runtime)
    state=runtime._sessions['one'].preview_snapshots
    if reset=='final':
        assert preview(runtime,_rewrite(),22,finished=True)==FRESH
        assert not state.turns
        assert preview(runtime,_rewrite(),23)==_rewrite()
    elif reset=='removed':
        runtime.publish_update('one',TimePreview(22*R,(),lane_end_samples=(('system',22*R),)))
        assert not state.turns
        assert preview(runtime,_rewrite(),23)==_rewrite()
    elif reset=='reopen':
        runtime.record_engine_call('one',kind='system_live_preview')
        assert not state.turns
        assert preview(runtime,_rewrite(),23)==_rewrite()
    else:
        asyncio.run(runtime.stop('one',1))
        assert not state.turns and not state.clocks and not state.frontiers
        runtime.create(session_id='two')
        assert not runtime._sessions['two'].preview_snapshots.turns


@pytest.mark.parametrize('other',['lane','turn'])
def test_floor_other_lane_or_new_turn_never_borrows_count(tmp_path,other):
    runtime=_runtime(tmp_path,lanes=True)
    _active_floor(runtime)
    kwargs={'lane':'microphone'} if other=='lane' else {'turn':16}
    assert preview(runtime,_rewrite(),25,**kwargs)==_rewrite()


@pytest.mark.parametrize('ambiguous',['duplicate_key','merged_origin'])
def test_floor_ambiguous_origin_abstains(tmp_path,ambiguous):
    runtime=_runtime(tmp_path)
    _active_floor(runtime)
    raw=_rewrite()
    row=rt.GeminiSegment(15*R,22*R,raw,source_lane='system')
    origins=(rt.GeminiSegment(0,22*R,raw,source_lane='system'),
             rt.GeminiSegment(0 if ambiguous=='duplicate_key' else R,22*R,
                              'other source turn' if ambiguous=='duplicate_key' else raw,
                              source_lane='system'))
    runtime.publish_update('one',TimePreview(22*R,(row,),origins,(('system',22*R),)))
    assert ' '.join(r['text'] for r in runtime.snapshot('one').session.provisional.segments)==raw


def test_floor_fault_uses_text_rows_and_keeps_meeting_active(tmp_path,monkeypatch):
    runtime=_runtime(tmp_path)
    _seed(runtime)
    state=runtime._sessions['one']
    raw=_rewrite()
    row=rt.GeminiSegment(15*R,22*R,raw,source_lane='system')
    expected=rt._trim_committed_preview((row,),runtime.snapshot('one').session.effective_transcript,
                                       list(state.preview_cuts))
    def explode(*args):
        raise RuntimeError('injected floor fault')
    monkeypatch.setattr(state.preview_snapshots,'floor_cuts',explode,raising=False)
    assert preview(runtime,raw,22)==' '.join(r.text for r in expected)
    assert runtime.snapshot('one').session.status=='active' and state.terminal_failure is None
    assert not state.preview_snapshots.turns
    assert runtime.engine_diagnostics('one')['preview_snapshot_errors']==1


def test_floor_D16_accepted_limit_head_deletion_append_hides_fresh_head_count(tmp_path):
    runtime=_runtime(tmp_path)
    old=' '.join(u for u,_,_ in rt._preview_units(COMMITTED)[:60])
    fresh='现在新讲话必须继续完整显示出来这是真的啊'
    assert len(rt._preview_units(old))==60 and len(rt._preview_units(fresh))==20
    preview(runtime,old,14)
    _commit(runtime,old,through_s=15)
    assert preview(runtime,old,16)==''  # N60, including fully hidden rows.
    raw=' '.join(old.split()[15:])+' '+fresh
    shown=preview(runtime,raw,20)
    assert shown==fresh[15:]  # D16: fifteen fresh units wait until solid.
    values=runtime.engine_diagnostics('one')['preview']['system']
    assert values['floor_hidden_units']==15 and values['floor_publications']==1
    assert values['text_hidden_last']==45 and values['time_hidden_last']==0


def test_floor_operator_diagnostics_carries_numeric_counts(tmp_path,caplog):
    import json
    from moss_transcribe_diarize.app.phase2_operator import LOGGER, serialize_operator_payload
    runtime=_runtime(tmp_path)
    n=_seed(runtime)
    preview(runtime,_rewrite(),21)
    with caplog.at_level('INFO',logger=LOGGER.name):
        asyncio.run(runtime.stop('one',1))
        asyncio.run(runtime.wait_terminal('one'))
    events=[json.loads(r.message) for r in caplog.records if 'meeting_engine_diagnostics' in r.message]
    assert len(events)==1
    values=events[0]['context']['engine_diagnostics']['preview']['system']
    assert values['floor_hidden_units']==n and values['floor_publications']==1
    assert all(isinstance(v,(int,float)) for v in values.values())
    assert _rewrite() not in json.dumps(events[0])
    assert serialize_operator_payload('event',events[0])==events[0]
