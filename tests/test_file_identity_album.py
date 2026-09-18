from dataclasses import replace
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
from moss_transcribe_diarize.app.live_identity_album import ALBUM_MIN_MATCH_SCORE, ALBUM_MIN_MATCH_MARGIN
from moss_transcribe_diarize.app.windowed_transcription import plan_windows, _stitch_segments
from moss_transcribe_diarize.transcript_parser import TranscriptSegment


class Encoder:
    descriptor = {'provider': 'test'}
    def embed(self, path, intervals):
        return path[int(intervals[0][0] // 20) - 1]


def resolver():
    return AlbumIdentityResolver(config=SimpleNamespace(
        identity_config=dict(max_speakers=16,min_match_score=ALBUM_MIN_MATCH_SCORE,min_match_margin=ALBUM_MIN_MATCH_MARGIN),
        identity_provider=dict(min_segment_samples=8000),
    ), encoder=Encoder())


def segment(speaker='S01', start=20, duration=5):
    return TranscriptSegment(start,start+duration,speaker,'exact words')


def run(groups, vectors):
    windows=plan_windows(120*len(groups),window_seconds=150,stride_seconds=120)
    result=resolver().resolve(windows,groups,window_audio_paths=vectors)
    assert [[(s.start,s.end,s.text) for s in g] for g in result.relabeled_results] == [[(s.start,s.end,s.text) for s in g] for g in groups]
    return result


@pytest.mark.parametrize('voices',[1,2])
def test_perfect_repeated_voices_have_one_canonical_identity_each(voices):
    groups=[[segment()]+([segment('S02',40)] if voices==2 else []) for _ in range(3)]
    result=run(groups,[[[1.,0.],[0.,1.]]]*3)
    assert len({s.speaker for g in result.relabeled_results for s in g}) == voices
    assert all(g==result.relabeled_results[0] for g in result.relabeled_results)
    windows=plan_windows(360,window_seconds=150,stride_seconds=120)
    assert len(_stitch_segments(windows,result.relabeled_results)) == 3*voices


def test_returning_voice_keeps_identity_across_gap_and_unknown_short_abstains():
    result=run([[segment()],[segment()],[segment(),segment('S02',40,.6)]],
               [[[1,0,0]],[[0,1,0]],[[1,0,0],[0,0,1]]])
    assert [[s.speaker for s in g] for g in result.relabeled_results] == [['S01'],['S02'],['S01','S00']]


def test_short_known_voice_matches_without_entering_album():
    result=run([[segment()],[segment(duration=.6)]],[[[1,0]],[[1,0]]])
    assert result.relabeled_results[1][0].speaker == 'S01'
    assert result.diagnostics['windows'][1]['admissions'] == {'S01':'rejected_below_admission'}


def test_retrospective_sweep_labels_early_abstention_after_later_admission():
    result=run([[segment(duration=.6)],[segment()]],[[[1,0]],[[1,0]]])
    assert result.diagnostics['windows'][0]['mapping'] == {}
    assert result.relabeled_results[0][0].speaker == result.relabeled_results[1][0].speaker == 'S01'
    assert result.diagnostics['sweep']['corrections'][0]['reason'] == 'labelled'


def test_provisional_reference_retires_when_admitted_evidence_arrives():
    result=run([[segment(duration=1.5)],[segment()]],[[[1,0]],[[1,0]]])
    assert result.diagnostics['windows'][0]['admissions']['S01'] == 'provisional'
    assert result.diagnostics['windows'][1]['album']['S01'] == dict(exemplars=1,provisional=False)


def test_ambiguous_voice_abstains_without_polluting_either_album():
    result=run([[segment(),segment('S02',40)],[segment()]],
               [[[1,0],[0,1]],[[1,1]]])
    assert result.diagnostics['windows'][1]['reason'] == 'ambiguous_identity'
    assert result.relabeled_results[1][0].speaker == 'S00'
    assert result.diagnostics['windows'][1]['admissions'] == {}


def test_same_window_conflicting_local_voices_abstain_as_live():
    result=run([[segment()],[segment(),segment('S02',40)]],
               [[[1,0]],[[1,0],[1,0]]])
    assert result.diagnostics['windows'][1]['reason'] == 'same_span_cannot_link_conflict'
    assert [s.speaker for s in result.relabeled_results[1]] == ['S00','S00']


def test_resolver_state_does_not_leak_between_file_meetings():
    r=resolver(); windows=plan_windows(120,window_seconds=150,stride_seconds=120)
    for vector in ([1,0],[0,1]):
        result=r.resolve(windows,[[segment()]],window_audio_paths=[[vector]])
        assert result.relabeled_results[0][0].speaker == 'S01'


def test_embedding_failure_preserves_words_and_abstains_as_live():
    r=resolver()
    class Failed:
        descriptor={}
        def embed(self,*args): raise RuntimeError('provider unavailable')
    r._encoder=Failed()
    windows=plan_windows(120)
    original=segment()
    result=r.resolve(windows,[[original]],window_audio_paths=['unused'])
    assert result.relabeled_results==[[replace(original,speaker='S00')]]
    assert result.diagnostics['windows'][0]['reason']=='evidence_provider_failed:RuntimeError'
