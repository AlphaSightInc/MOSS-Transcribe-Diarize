import asyncio
import json
import subprocess
from pathlib import Path
import pytest
from tests.e2e.export_oracle import compare_export
from tests.e2e.verify_workspace import Harness

FORMATS=('md','txt','json','srt','vtt')

@pytest.fixture(scope='module', params=['legacy', 'overlap'])
def meeting(request):
    fixtures = json.loads((Path(__file__).resolve().parents[2] /
                           'evidence/mvpfix/wp2/fixtures.json').read_text())
    return {'transcript': fixtures[request.param]}


@pytest.fixture(scope='module')
def real_exports(meeting):
    # Production serializer; contiguous turns are supplied as the UI would group them.
    script = """import { serializeTranscriptExport } from './frontend/src/lib/transcriptExport.ts';
const doc = JSON.parse(process.argv[1]);
const turns = [];
for (const s of doc.transcript.segments) {
 const last = turns.at(-1);
 if (last && last.speaker_entity_id === s.speaker_entity_id && last.source_lane === s.source_lane) {
  last.end = s.end; last.text += ' ' + s.text; last.segment_ids.push(s.id); last.target_segment_keys.push(s.id);
 } else turns.push({...s,speaker:s.speaker_entity_id,display_name:s.speaker,state:'final',segment_ids:[s.id],target_segment_keys:[s.id],provisional_stale:false});
}
console.log(JSON.stringify(Object.fromEntries(['md','txt','json','srt','vtt'].map(f => [f,serializeTranscriptExport(f,turns,t=>t.display_name,{sessionId:'meeting',exportedAt:new Date(0)}).content]))));"""
    return json.loads(subprocess.check_output(
        ['node', '--experimental-strip-types', '--input-type=module', '-e', script, json.dumps(meeting)],
        text=True, cwd=Path(__file__).resolve().parents[2]))

@pytest.mark.parametrize('fmt', FORMATS)
def test_real_exports_match_api(fmt,real_exports,meeting):
    assert compare_export(fmt,real_exports[fmt],meeting)['ok']

@pytest.mark.parametrize('fmt', FORMATS)
@pytest.mark.parametrize('mutation', ['words','label','time'])
def test_download_corruptions_fail(fmt,mutation,real_exports,meeting):
    text=real_exports[fmt]
    if mutation=='words': text=text.replace('And the key','Unrelated invented transcript.')
    if mutation=='label': text=text.replace('Bill Ackman','Wrong speaker')
    if mutation=='time':
        if fmt=='json':
            body=json.loads(text);body['turns'][0]['start']=8.0;text=json.dumps(body)
        else: text=text.replace('00:00:00','00:00:08')
    assert not compare_export(fmt,text,meeting)['ok']

@pytest.mark.parametrize('corrupt',[True,False])
def test_harness_all_five_downloads(tmp_path,real_exports,corrupt,meeting):
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
    assert sum(bool(r['ok']) for r in result['formats'].values())==(0 if corrupt else 5)
    assert result['ok'] is not corrupt


@pytest.mark.parametrize('mutation', ['missing', 'wrong'])
def test_json_lane_corruption_fails(meeting, real_exports, mutation):
    if not any(s.get('source_lane') for s in meeting['transcript']['segments']):
        # Adding an invented lane to legacy output is also corruption.
        body = json.loads(real_exports['json'])
        body['turns'][0]['source_lane'] = 'system' if mutation == 'wrong' else 'microphone'
    else:
        body = json.loads(real_exports['json'])
        if mutation == 'missing':
            del body['turns'][0]['source_lane']
        else:
            body['turns'][0]['source_lane'] = 'microphone'
    result = compare_export('json', json.dumps(body), meeting)
    assert not result['ok']
    assert not result['lane']
    assert all(result[key] for key in ('words', 'labels', 'timing', 'identity'))


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
