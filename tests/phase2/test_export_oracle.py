import asyncio
import copy
import json
import subprocess
from pathlib import Path
import pytest
from tests.e2e.export_oracle import (
    MARKDOWN_NEEDS_REVIEW_NOTICE, NEEDS_REVIEW_NOTICE, compare_export, expected_rows,
)
from tests.e2e.verify_workspace import Harness

FORMATS=('md','txt')

UNKNOWN_MEETING = {
    'needs_review': True,
    'transcript': {'segments': [
        {'id':'known-a','start':0.0,'end':1.0,'speaker':'Alex','speaker_entity_id':'person-a','text':'First known','source_lane':'system'},
        {'id':'unknown-a','start':1.0,'end':2.0,'speaker':'Speaker TBD','speaker_entity_id':'S00','text':'First unknown','source_lane':'microphone'},
        {'id':'unknown-b','start':2.0,'end':3.0,'speaker':'Speaker TBD','speaker_entity_id':'S00','text':'Second unknown','source_lane':'microphone'},
        {'id':'known-b1','start':3.0,'end':4.0,'speaker':'Blair','speaker_entity_id':'person-b','text':'Known part one','source_lane':'system'},
        {'id':'known-b2','start':4.0,'end':5.0,'speaker':'Blair','speaker_entity_id':'person-b','text':'Known part two','source_lane':'system'},
    ]}
}


def test_expected_rows_keep_unknown_passages_separate_and_known_turns_grouped():
    assert expected_rows(UNKNOWN_MEETING) == [
        {'start':0.0,'end':1.0,'label':'Alex','identity':'person-a','tokens':['first','known'],'lane':'system','segment_ids':['known-a']},
        {'start':1.0,'end':2.0,'label':'Speaker TBD','identity':'S00','tokens':['first','unknown'],'lane':'microphone','segment_ids':['unknown-a']},
        {'start':2.0,'end':3.0,'label':'Speaker TBD','identity':'S00','tokens':['second','unknown'],'lane':'microphone','segment_ids':['unknown-b']},
        {'start':3.0,'end':5.0,'label':'Blair','identity':'person-b','tokens':['known','part','one','known','part','two'],'lane':'system','segment_ids':['known-b1','known-b2']},
    ]

@pytest.fixture(scope='module', params=['legacy', 'overlap'])
def meeting(request):
    fixtures = json.loads((Path(__file__).resolve().parents[2] /
                           'evidence/mvpfix/wp2/fixtures.json').read_text())
    return {'transcript': fixtures[request.param]}


@pytest.fixture(scope='module')
def real_exports(meeting):
    return serialize_exports(meeting)


@pytest.fixture(scope='module')
def unknown_exports():
    return serialize_exports(UNKNOWN_MEETING)


def serialize_exports(meeting):
    # Production serializer; contiguous turns are supplied as the UI would group them.
    script = """import { serializeTranscriptExport } from './frontend/src/lib/transcriptExport.ts';
const doc = JSON.parse(process.argv[1]);
const turns = [];
for (const s of doc.transcript.segments) {
 const last = turns.at(-1);
 const identity = s.speaker_entity_id ?? s.speaker;
 if (last && !['S00','UNKNOWN'].includes(identity) && last.speaker_entity_id === identity &&
     last.source_lane === s.source_lane && last.display_name === s.speaker) {
  last.end = s.end; last.text += ' ' + s.text; last.segment_ids.push(s.id); last.target_segment_keys.push(s.id);
 } else turns.push({...s,speaker:identity,speaker_entity_id:identity,display_name:s.speaker,state:'final',segment_ids:[s.id],target_segment_keys:[s.id],provisional_stale:false});
}
console.log(JSON.stringify(Object.fromEntries(['md','txt'].map(f => [f,serializeTranscriptExport(f,turns,t=>t.display_name,{sessionId:'meeting',exportedAt:new Date(0)}).content]))));"""
    return json.loads(subprocess.check_output(
        ['node', '--experimental-strip-types', '--input-type=module', '-e', script, json.dumps(meeting)],
        text=True, cwd=Path(__file__).resolve().parents[2]))


@pytest.mark.parametrize('source_mode', ('live', 'file'))
@pytest.mark.parametrize('fmt', FORMATS)
def test_unknown_passage_exports_round_trip_without_review_notice(fmt, source_mode):
    meeting = copy.deepcopy(UNKNOWN_MEETING)
    meeting['mode'] = source_mode
    if source_mode == 'file':
        for segment in meeting['transcript']['segments']:
            segment.pop('source_lane', None)
    exported = serialize_exports(meeting)[fmt]
    result = compare_export(fmt, exported, meeting)
    assert result['ok']
    assert result['review'] is True  # the check passed: no "Needs review" notice in the file
    assert 'Needs review' not in exported
    assert 'S00' not in exported


@pytest.mark.parametrize('fmt', FORMATS)
@pytest.mark.parametrize('mutation,failed_check', [
    ('wrong_speaker','labels'),
    ('dropped_word','words'),
    ('changed_time','timing'),
    ('added_review','review'),
])
def test_unknown_passage_export_corruptions_fail(fmt, mutation, failed_check, unknown_exports):
    text=unknown_exports[fmt]
    if mutation=='wrong_speaker': text=text.replace('Speaker TBD','Wrong speaker')
    if mutation=='dropped_word': text=text.replace('Second unknown','Second')
    if mutation=='changed_time': text=text.replace('00:00:00','00:00:08',1)
    if mutation=='added_review':
        # A regression that writes the removed review notice back into the file must fail.
        text=(MARKDOWN_NEEDS_REVIEW_NOTICE if fmt=='md' else NEEDS_REVIEW_NOTICE)+'\n\n'+text
    result=compare_export(fmt,text,UNKNOWN_MEETING)
    assert not result['ok']
    assert result[failed_check] is False


@pytest.mark.parametrize('fmt', FORMATS)
def test_real_exports_match_api(fmt,real_exports,meeting):
    assert compare_export(fmt,real_exports[fmt],meeting)['ok']

@pytest.mark.parametrize('fmt', FORMATS)
@pytest.mark.parametrize('mutation', ['words','label','time'])
def test_download_corruptions_fail(fmt,mutation,real_exports,meeting):
    text=real_exports[fmt]
    if mutation=='words': text=text.replace('And the key','Unrelated invented transcript.')
    if mutation=='label': text=text.replace('Bill Ackman','Wrong speaker')
    if mutation=='time': text=text.replace('00:00:00','00:00:08')
    assert not compare_export(fmt,text,meeting)['ok']

@pytest.mark.parametrize('corrupt',[True,False])
def test_harness_all_transcript_downloads(tmp_path,real_exports,corrupt,meeting):
    class Downloads:
        state={'meetings':{'file':'controlled'}}
        async def select(self, ident): pass
        async def api(self,path):
            assert path=='/api/meetings/controlled'
            return {'body':meeting}
        async def export(self,fmt):
            p=tmp_path/('download.'+fmt)
            p.write_text(real_exports[fmt].replace('And the key','Fabricated unrelated content.') if corrupt else real_exports[fmt])
            return p
    result=asyncio.run(Harness.exports(Downloads()))
    assert sum(bool(r['ok']) for r in result['formats'].values())==(0 if corrupt else len(FORMATS))
    assert result['ok'] is not corrupt


@pytest.mark.parametrize('tagged', [True, False])
def test_terminal_document_preserves_lane_and_renamed_identity(tagged):
    from types import SimpleNamespace as N
    from moss_transcribe_diarize.app.phase2_live import _transcript_document
    from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment
    lanes = ['system', 'microphone'] if tagged else [None, None]
    segments = [EffectiveTranscriptSegment(start_sample=0,end_sample=16000,authority='terminal',canonical_speaker=f'speaker-{i:04d}',
                  source_lane=lane,text=f'Words {i}') for i,lane in enumerate(lanes,1)]
    snapshot = N(descriptor=N(sample_rate=16000),session=N(
        identity_snapshot=N(canonical_speakers=()),effective_transcript=segments))
    assert _transcript_document(snapshot,{'speaker-0001':'Renamed','speaker-0002':'Sam'}) == {
        'segments': [dict(id=f'seg_{i:04d}',start=0.0,end=1.0,
                          speaker_entity_id=f'speaker-{i:04d}',
                          speaker='Renamed' if i==1 else 'Sam',text=f'Words {i}',
                          **({'source_lane':lane} if lane is not None else {}))
                     for i,lane in enumerate(lanes,1)]}
