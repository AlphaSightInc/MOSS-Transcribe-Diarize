from copy import deepcopy
import json
from pathlib import Path
import pytest
from moss_transcribe_diarize.lane_word_oracle import score_lanes

REF = {'system': 'Copper planets orbit distant stars', 'microphone': 'Violet gardens grow beside rivers'}
GOOD = [dict(source_lane=k, speaker=k, start=0, end=1, text=v) for k,v in REF.items()]

@pytest.mark.parametrize('legacy', [False, True])
def test_valid_lanes(legacy):
    rows = deepcopy(GOOD)
    if legacy:
        for row in rows: row.pop('source_lane')
    result=score_lanes(rows, REF)
    assert result['passed'] and result['duplication_count']==0


def test_healthy_identified_speakers_in_single_lanes_pass_without_unattributed_evidence():
    rows = [dict(source_lane=lane, canonical_speaker=f'person-{lane}', start=0, end=1, text=text)
            for lane, text in REF.items()]
    result = score_lanes(rows, REF)
    assert result['passed'] and result['speaker_lane_conflicts'] == 0
    assert result['unattributed_segment_count'] == result['unattributed_word_count'] == 0
    assert result['identity_unqualified'] is False


def test_f1_shaped_anonymous_fragments_retain_evidence_without_named_speaker_conflict():
    refs = {'system': 'one two three four five six', 'microphone': 'seven eight nine ten'}
    rows = [
        dict(canonical_speaker='person-system', source_lane='system', start=0, end=1, text='one'),
        dict(canonical_speaker=None, source_lane='system', start_sample=152480, end_sample=159680, text='two three'),
        dict(canonical_speaker=None, source_lane='system', start_sample=314560, end_sample=319680, text='four five six'),
        dict(canonical_speaker='person-microphone', source_lane='microphone', start=1, end=2, text='seven'),
        dict(canonical_speaker=None, source_lane='microphone', start_sample=471680, end_sample=479360, text='eight nine ten'),
    ]
    result = score_lanes(rows, refs)
    assert result['speaker_lane_conflicts'] == 0
    assert result['passed']
    assert result['unattributed_segment_count'] == 3
    assert result['unattributed_word_count'] == 8
    assert result['identity_unqualified'] is False


@pytest.mark.parametrize('abstention', [None, 'S00'])
def test_all_anonymous_explicit_lanes_pass_word_score_but_are_identity_unqualified(abstention):
    """Anonymous words can satisfy the word/lane oracle without an identity claim."""
    refs = {'system': 'one two three four five', 'microphone': 'six seven eight'}
    rows = [
        dict(canonical_speaker=abstention, source_lane='system', start_sample=152480, end_sample=159680, text='one two'),
        dict(canonical_speaker=abstention, source_lane='system', start_sample=314560, end_sample=319680, text='three four five'),
        dict(canonical_speaker=abstention, source_lane='microphone', start_sample=471680, end_sample=479360, text='six seven eight'),
    ]
    result = score_lanes(rows, refs)
    assert result['speaker_lane_conflicts'] == 0
    assert result['passed']
    assert result['unattributed_segment_count'] == 3
    assert result['unattributed_word_count'] == 8
    assert result['identity_unqualified'] is True


def test_identified_speaker_in_both_explicit_lanes_remains_a_conflict():
    rows = [dict(source_lane=lane, speaker_entity_id='person-verified', start=0, end=1, text=text)
            for lane, text in REF.items()]
    result = score_lanes(rows, REF)
    assert result['speaker_lane_conflicts'] == 1
    assert not result['passed']
    assert result['unattributed_segment_count'] == result['unattributed_word_count'] == 0
    assert result['identity_unqualified'] is False

@pytest.mark.parametrize('case', ['counts', 'missing', 'swap', 'duplicate', 'mixed_speaker'])
def test_corruption_fails(case):
    rows=deepcopy(GOOD)
    if case=='counts': rows=[]
    if case=='missing': rows=rows[:1]
    if case=='swap':
        for row in rows: row['source_lane']='microphone' if row['source_lane']=='system' else 'system'
    if case=='duplicate': rows.append(dict(rows[1], text=REF['system']))
    if case=='mixed_speaker': rows[1]['speaker']=rows[0]['speaker']
    result=score_lanes(rows, REF)
    assert not result['passed']
    if case=='duplicate': assert result['duplication_count']==5

def test_documented_overlap_does_not_count_shared_vocabulary_as_duplication():
    root=Path('evidence/live-policy-sweep-20260825/corpus')
    refs={lane: json.loads((root/name/'reference.jsonl').read_text().splitlines()[0]) for lane,name in
          [('system','interview_bill_ackman_60s'), ('microphone','interview_keyu_jin_60s')]}
    result=score_lanes([dict(r, source_lane=k, speaker=k) for k,r in refs.items()], {k:r['text'] for k,r in refs.items()})
    assert result['passed'] and result['duplication_count']==0
    assert sum(r['reference_words'] for r in result['lanes'].values())==157

def test_ordered_errors_are_not_unique_vocabulary():
    rows=deepcopy(GOOD);rows[0]['text']='stars distant orbit planets Copper'
    result=score_lanes(rows, REF)
    assert result['lanes']['system']['unique_retention']==1
    assert result['lanes']['system']['wer']>0 and not result['passed']


def test_switch_tolerance_is_only_for_straddling_legacy_segments():
    rows = [dict(speaker="tab", start=0, end=9, text=REF["system"]),
            dict(speaker="mic", start=9, end=11, text=REF["microphone"] + " Copper")]
    boundary = score_lanes(rows, REF, max_wer=1, lane_switches=(10,))
    assert boundary["passed"]
    assert boundary["boundary_attribution_words"] == 1
    rows[1]["start"] = 10
    inside = score_lanes(rows, REF, max_wer=1, lane_switches=(10,))
    assert not inside["passed"] and inside["attribution_errors"] == 1
    rows[1].update(start=9, source_lane="microphone")
    explicit = score_lanes(rows, REF, max_wer=1, lane_switches=(10,))
    assert not explicit["passed"] and explicit["attribution_errors"] == 1
