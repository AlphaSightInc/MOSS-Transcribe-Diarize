"""A4: time additions belong only to a dated, unchanged original-turn snapshot."""
import asyncio
from dataclasses import dataclass

import pytest

from moss_transcribe_diarize.app import gemini_live_runtime as rt
from test_gemini_preview_duplication import _runtime, _commit, COMMITTED, FRESH, R


@dataclass(frozen=True, slots=True)
class TimePreview(rt.GeminiPreview):
    origins: tuple = ()
    lane_end_samples: tuple = ()
    finished_turns: tuple = ()


def preview(runtime, text, clock, *, lane='system', turn=0, finished=False):
    start = runtime.snapshot('one').session.committed_samples
    origin = rt.GeminiSegment(turn*R, clock*R, text, source_lane=lane)
    runtime.publish_update('one', TimePreview(clock*R, (
        rt.GeminiSegment(max(start,turn*R),clock*R,text,source_lane=lane),),
        (origin,),((lane,clock*R),),((lane,turn*R),) if finished else ()))
    return ' '.join(r['text'] for r in runtime.snapshot('one').session.provisional.segments)


def establish(runtime, old=COMMITTED, *, lane='system', solid=None):
    preview(runtime,old,14,lane=lane)
    words=old.split()
    _commit(runtime,solid if solid is not None else ' '.join(words[:15]+words[37:]),
            through_s=15,lane=lane)


@pytest.mark.parametrize('lane',['system','microphone'])
def test_time_snapshot_removes_solid_omission_but_keeps_fresh_suffix(tmp_path,lane):
    runtime=_runtime(tmp_path,lanes=True)
    establish(runtime,lane=lane)
    assert preview(runtime,COMMITTED+' '+FRESH,20,lane=lane)==FRESH


def test_time_snapshot_removes_preview_insertion_but_keeps_fresh_suffix(tmp_path):
    runtime=_runtime(tmp_path)
    words=COMMITTED.split()
    old=' '.join(words[:30])+ ' these eleven injected unheard words belong exclusively to this omitted passage '+ ' '.join(words[30:])
    establish(runtime,old,solid=COMMITTED)
    assert preview(runtime,old+' '+FRESH,20)==FRESH


def test_time_snapshot_removes_long_unspaced_insertion(tmp_path):
    runtime=_runtime(tmp_path)
    solid='这是之前的讲话内容大家需要讨论整个项目目前的进展以及接下来如何安排'
    old=solid[:12]+'这段被确认模型遗漏的旧话必须在确认之后从灰色预览中消失'*6+solid[12:]
    fresh='现在新讲话必须继续完整显示出来'
    establish(runtime,old,solid=solid)
    assert preview(runtime,old+fresh,20)==fresh


def test_time_snapshot_prefix_shrinks_on_rewrite(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime)
    first=COMMITTED.split()[0]
    assert preview(runtime,first+' revised earlier words '+FRESH,20)=='revised earlier words '+FRESH


def test_time_snapshot_uses_last_eligible_publication_not_first(tmp_path):
    runtime=_runtime(tmp_path)
    preview(runtime,COMMITTED[:80],10)
    establish(runtime)
    assert preview(runtime,COMMITTED+' '+FRESH,20)==FRESH


def test_frontier_without_new_publication_uses_existing_snapshot(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime)
    runtime.publish_update('one',rt.GeminiBase(30*R,()))
    runtime.publish_update('one',rt.GeminiRolling(15*R,30*R,(),revision_lanes=('system',)))
    assert preview(runtime,COMMITTED+' '+FRESH,35)==FRESH


def test_source_restart_same_turn_key_discards_snapshot(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime)
    runtime.record_engine_call('one',kind='system_live_preview')
    raw=COMMITTED+' '+FRESH
    row=rt.GeminiSegment(15*R,20*R,raw,source_lane='system')
    expected=' '.join(r.text for r in rt._trim_committed_preview((row,),runtime.snapshot('one').session.effective_transcript))
    assert preview(runtime,raw,20)==expected
    assert runtime.engine_diagnostics('one')['preview']['system']['time_hidden_last']==0


@pytest.mark.parametrize('turn',[16,5,20])
def test_new_split_merged_or_restated_turn_never_borrows_snapshot(tmp_path,turn):
    runtime=_runtime(tmp_path)
    establish(runtime)
    raw=COMMITTED+' '+FRESH
    row=rt.GeminiSegment(max(15,turn)*R,25*R,raw,source_lane='system')
    expected=' '.join(r.text for r in rt._trim_committed_preview((row,),runtime.snapshot('one').session.effective_transcript))
    assert preview(runtime,raw,25,turn=turn)==expected
    assert runtime.engine_diagnostics('one')['preview']['system']['time_hidden_last']==0


def test_snapshot_lane_isolation(tmp_path):
    runtime=_runtime(tmp_path,lanes=True)
    establish(runtime)
    raw=COMMITTED+' '+FRESH
    assert preview(runtime,raw,20,lane='microphone')==raw
    assert runtime.engine_diagnostics('one')['preview']['microphone']['time_hidden_last']==0


def test_stale_lane_clock_cannot_date_new_units(tmp_path):
    runtime=_runtime(tmp_path,lanes=True)
    establish(runtime,solid='entirely unrelated solid words')
    raw=COMMITTED+' '+FRESH
    row=rt.GeminiSegment(15*R,20*R,raw,source_lane='system')
    origin=rt.GeminiSegment(0,20*R,raw,source_lane='system')
    runtime.publish_update('one',TimePreview(20*R,(row,),(origin,),
                         (('system',14*R),('microphone',20*R))))
    shown=' '.join(r['text'] for r in runtime.snapshot('one').session.provisional.segments)
    assert shown==FRESH
    assert runtime._sessions['one'].preview_snapshots.clocks['system']==14*R


def test_final_clears_snapshot_after_rendering(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime)
    assert preview(runtime,COMMITTED+' '+FRESH,20,finished=True)==FRESH
    assert not runtime._sessions['one'].preview_snapshots.turns


def test_nominal_rolling_frontier_without_solid_does_not_own_preview(tmp_path):
    runtime=_runtime(tmp_path)
    _commit(runtime,'unrelated older solid speech',through_s=10)
    preview(runtime,COMMITTED,20)
    runtime.publish_update('one',rt.GeminiBase(30*R,()))
    runtime.publish_update('one',rt.GeminiRolling(10*R,30*R,(
        rt.GeminiSegment(10*R,15*R,'different confirmed words','speaker-0001','system'),),revision_lanes=('system',)))
    assert preview(runtime,COMMITTED+' '+FRESH,35)==COMMITTED+' '+FRESH
    assert runtime.engine_diagnostics('one')['preview']['system']['confirmed_sample']==15*R


def test_degraded_replacement_keeps_61_words_and_fresh_suffix(tmp_path):
    runtime=_runtime(tmp_path)
    _commit(runtime,'earlier settled words',through_s=15)
    preview(runtime,COMMITTED,55,turn=15)
    runtime.publish_update('one',rt.GeminiBase(21*R,(
        rt.GeminiSegment(15*R,21*R,COMMITTED,source_lane='system'),),degraded=True))
    runtime.publish_update('one',rt.GeminiBase(30*R,()))
    runtime.publish_update('one',rt.GeminiRolling(15*R,30*R,(
        rt.GeminiSegment(15*R,30*R,' '.join(COMMITTED.split()[:20]),'speaker-0001','system'),),revision_lanes=('system',)))
    shown=preview(runtime,COMMITTED+' '+FRESH,60,turn=15)
    assert shown==' '.join(COMMITTED.split()[20:])+' '+FRESH
    assert runtime.engine_diagnostics('one')['preview']['system']['time_hidden_last']==0


def test_retreating_solid_frontier_discards_snapshot_ahead_of_it(tmp_path):
    runtime=_runtime(tmp_path)
    preview(runtime,COMMITTED,14)
    runtime.publish_update('one',rt.GeminiBase(40*R,(
        rt.GeminiSegment(0,40*R,COMMITTED,source_lane='system'),),degraded=True))
    runtime.publish_update('one',rt.GeminiRolling(0,40*R,(
        rt.GeminiSegment(0,10*R,'unrelated replacement','speaker-0001','system'),),revision_lanes=('system',)))
    assert preview(runtime,COMMITTED+' '+FRESH,45)==COMMITTED+' '+FRESH


def test_stop_new_meeting_clear_snapshot_history(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime)
    preview(runtime,COMMITTED+' '+FRESH,20)
    asyncio.run(runtime.stop('one',1))
    state=runtime._sessions['one'].preview_snapshots
    assert not state.turns and not state.clocks and not state.frontiers
    runtime.create(session_id='two')
    assert not runtime._sessions['two'].preview_snapshots.turns


def test_preview_diagnostics_numbers_show_only_additional_time_cut(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime)
    preview(runtime,COMMITTED+' '+FRESH,20)
    diagnostics=runtime.engine_diagnostics('one')
    assert 'preview' in diagnostics
    values=diagnostics['preview']['system']
    assert values['time_hidden_last']>0
    assert values['raw_units_last']==values['shown_units_last']+values['text_hidden_last']+values['time_hidden_last']
    assert values['lane_publications']==2
    assert all(isinstance(v,(int,float)) for v in values.values())


def test_ambiguous_original_turn_key_abstains(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime,solid='entirely unrelated solid words')
    raw=COMMITTED+' '+FRESH
    row=rt.GeminiSegment(15*R,20*R,raw,source_lane='system')
    origins=(rt.GeminiSegment(0,20*R,raw,source_lane='system'),
             rt.GeminiSegment(0,20*R,'another source turn',source_lane='system'))
    runtime.publish_update('one',TimePreview(20*R,(row,),origins,(('system',20*R),)))
    assert ' '.join(r['text'] for r in runtime.snapshot('one').session.provisional.segments)==raw


def test_already_confirmed_final_clears_history_without_republishing(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime)
    before=runtime.snapshot('one').session.version
    runtime.publish_update('one',TimePreview(14*R,(),finished_turns=(('system',0),)))
    assert not runtime._sessions['one'].preview_snapshots.turns
    assert runtime.snapshot('one').session.version==before
