"""D17 (O2): the end of the lane's latest solid row, found in the grey turn, places the cut."""
from moss_transcribe_diarize.app import gemini_live_runtime as rt
from test_gemini_preview_duplication import _runtime, _commit, COMMITTED, FRESH, R
from test_gemini_preview_snapshots import establish, preview

WORDS = COMMITTED.split()


def _values(runtime, lane='system'):
    return runtime.engine_diagnostics('one')['preview'][lane]


def test_anchor_places_cut_where_text_match_and_snapshot_both_fail(tmp_path):
    # Solid lacks a 22-word passage, so the head-to-frontier text match breaks (the c6s shape).
    runtime=_runtime(tmp_path)
    establish(runtime)
    raw=COMMITTED+' '+FRESH
    row=rt.GeminiSegment(16*R,25*R,raw,source_lane='system')
    assert rt._trim_committed_preview((row,),runtime.snapshot('one').session.effective_transcript)[0].text==raw
    assert preview(runtime,raw,25,turn=16)==FRESH
    values=_values(runtime)
    assert values['anchor_hidden_units']==len(rt._preview_units(COMMITTED))
    assert values['anchor_publications']==1 and values['time_hidden_units']==0
    assert all(isinstance(value,(int,float)) for value in values.values())


def test_anchor_miss_leaves_the_retained_count_in_force(tmp_path):
    runtime=_runtime(tmp_path)
    establish(runtime)
    assert preview(runtime,COMMITTED+' '+FRESH,20)==FRESH
    hidden=len(rt._preview_units(COMMITTED))
    rewritten=' '.join(['rewritten']*hidden)+' '+FRESH      # the solid ending is gone from grey
    assert preview(runtime,rewritten,21)==FRESH
    assert _values(runtime)['floor_publications']>=1


def test_anchor_needs_five_words_of_solid_ending(tmp_path):
    runtime=_runtime(tmp_path)
    preview(runtime,'alpha beta gamma delta',14)
    _commit(runtime,'gamma delta',through_s=15)             # two words: no anchor
    raw='unrelated opening words then gamma delta and fresh speech follows here today'
    assert preview(runtime,raw,25,turn=16)==raw
    assert _values(runtime)['anchor_publications']==0


def test_anchor_never_reads_the_other_lane(tmp_path):
    runtime=_runtime(tmp_path,lanes=True)
    establish(runtime)                                       # solid on the system lane only
    raw=COMMITTED+' '+FRESH
    assert preview(runtime,raw,20,lane='microphone')==raw
    assert 'microphone' not in runtime._sessions['one'].preview_snapshots.anchored


def test_anchor_D17_accepted_limit_missing_old_ending_and_later_repeat_hides_fresh_words(tmp_path):
    # Accepted by the user (D17 = O2): solid's ending is absent from grey at its own place and the
    # same five words are said again later, so the cut lands after the later copy.
    runtime=_runtime(tmp_path)
    establish(runtime)
    ending=' '.join(WORDS[-5:])
    fresh='entirely new speech nobody has confirmed yet and then '+ending
    raw=' '.join(WORDS[:15])+' '+fresh+' and a new tail'
    assert preview(runtime,raw,25,turn=16)=='and a new tail'
