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
    assert sum(r['reference_words'] for r in result['lanes'].values())==154

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
