"""Prevent aggregate speaker scores from concealing missing people."""
import pytest
from tools.qualify.speaker_quality import score_speakers


@pytest.mark.parametrize('label', ['', 'S00', 'UNKNOWN', 'Speaker uncertain', 'speaker-0000', 'unassigned'])
def test_unassigned_cannot_be_matched_to_a_reference_person(label):
    refs = [dict(start=0, end=10, speaker='person')]
    score = score_speakers(refs, [dict(start=0, end=10, speaker=label)])
    assert score['speaker_correctness']['person'] == 0
    assert score['diarization_error_rate'] == 1
    assert score['unassigned_segment_seconds'] == 10
    assert score['participant_presence_witness'] == 'FAIL'


def test_minority_failure_survives_high_aggregate_score():
    refs = [dict(start=0, end=99, speaker='Alice'), dict(start=99, end=100, speaker='Bob')]
    score = score_speakers(refs, [dict(start=0, end=100, speaker='one')])
    assert score['speaker_accuracy'] == .99
    assert score['zero_correct_reference_speakers'] == ['Bob']
    assert score['reference_seconds_by_speaker'] == {'Alice': 99, 'Bob': 1}
    assert score['participant_presence_witness'] == 'FAIL'


def test_sample_based_snapshot_and_second_based_reference_agree():
    refs = [dict(start=0, end=2, speaker='Alice'), dict(start=2, end=3, speaker='Bob')]
    score = score_speakers(refs, [
        dict(start_sample=0, end_sample=32000, canonical_speaker='speaker-0002'),
        dict(start_sample=32000, end_sample=48000, canonical_speaker='speaker-0001')])
    assert score['speaker_accuracy'] == 1
    assert score['two_sided_mapping']
    assert score['participant_presence_witness'] == 'PASS'
