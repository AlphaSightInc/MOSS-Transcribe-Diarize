import asyncio
import json
import subprocess
from pathlib import Path
import pytest
from tests.e2e.export_oracle import compare_export
from tests.e2e.verify_workspace import Harness

MEETING={'transcript':{'segments':[dict(id='s1',start=1.125,end=3.75,speaker='Named speaker',speaker_entity_id='speaker-0001',text='Actual meeting words.') ]}}
FORMATS=('md','txt','json','srt','vtt')

@pytest.fixture(scope='module')
def real_exports():
    # Invoke the production TypeScript serializer, not a Python imitation.
    script='''import { serializeTranscriptExport } from './frontend/src/lib/transcriptExport.ts';
const turn = {start:1.125,end:3.75,speaker:'speaker-0001',speaker_entity_id:'speaker-0001',display_name:'Named speaker',state:'final',text:'Actual meeting words.',segment_ids:['s1'],target_segment_keys:['s1'],provisional_stale:false};
console.log(JSON.stringify(Object.fromEntries(['md','txt','json','srt','vtt'].map(f => [f,serializeTranscriptExport(f,[turn],()=> 'Named speaker',{sessionId:'meeting',exportedAt:new Date(0)}).content]))));'''
    return json.loads(subprocess.check_output(['node','--experimental-strip-types','--input-type=module','-e',script],text=True))

@pytest.mark.parametrize('fmt', FORMATS)
def test_real_exports_match_api(fmt,real_exports):
    assert compare_export(fmt,real_exports[fmt],MEETING)['ok']

@pytest.mark.parametrize('fmt', FORMATS)
@pytest.mark.parametrize('mutation', ['words','label','time'])
def test_download_corruptions_fail(fmt,mutation,real_exports):
    text=real_exports[fmt]
    if mutation=='words': text=text.replace('Actual meeting words.','Unrelated invented transcript.')
    if mutation=='label': text=text.replace('Named speaker','Wrong speaker')
    if mutation=='time':
        text=text.replace('1.125','8.125').replace('00:00:01','00:00:08')
    assert not compare_export(fmt,text,MEETING)['ok']

@pytest.mark.parametrize('corrupt',[True,False])
def test_harness_all_five_downloads(tmp_path,real_exports,corrupt):
    class Downloads:
        state={'meetings':{'file':'controlled'}}
        async def select(self, ident): pass
        async def api(self,path):
            assert path=='/api/meetings/controlled'
            return {'body':MEETING}
        async def export(self,fmt):
            p=tmp_path/('download.'+fmt)
            p.write_text(real_exports[fmt].replace('Actual meeting words.','Fabricated unrelated content.') if corrupt else real_exports[fmt])
            return p
    result=asyncio.run(Harness.exports(Downloads()))
    assert sum(bool(r['ok']) for r in result['formats'].values())==(0 if corrupt else 5)
    assert result['ok'] is not corrupt
