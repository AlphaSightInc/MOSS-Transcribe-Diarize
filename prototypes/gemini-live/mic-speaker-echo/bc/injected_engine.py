"""A/B controlled committed-word/cleanup injections inside the WHOLE production engine."""
import json
import subprocess
import sys
from pathlib import Path
import soundfile as sf
import compose
import probes
from compose import S

EV=probes.EV
F2EV=EV.parent/'f2'
F3EV=EV.parent/'f3'
HERE=Path(__file__).resolve().parent

def tup(w):
    return [w.text,w.speaker,w.start_sample,w.end_sample]


def run():
    fixtures=EV/'fixtures'
    fixtures.mkdir(exist_ok=True)
    jobs=[]
    windows=[json.loads(l) for l in (F2EV/'runs/final/short-aec40/gates.jsonl').read_text().splitlines()]
    kept=next(r['kept'] for r in windows if r['stage']=='f2_window' and r['kept'])
    reply=[[t,label,round(a*S),round(b*S)] for t,label,a,b in kept if 8*S<=round(a*S)<10*S]
    assert len(reply)==5,reply
    for below in (10,20):
        mic,tab=probes.a_audio(below)
        mic_path=fixtures/f'omitted-reply-{below}dB.wav'
        sf.write(mic_path,__import__('numpy').frombuffer(mic,dtype='<i2'),S,subtype='PCM_16')
        cleanup=[tup(probes.word(f'echo{i}',6.2+i*.4,6.2+i*.4+.1)) for i in range(5)]
        cleanup += [tup(probes.word(f'tab{i}',9.65+i*.4,9.65+i*.4+.1)) for i in range(20)]
        source=fixtures/f'omitted-reply-{below}dB.json'
        source.write_text(json.dumps({'kind':'controlled omission, echo neighbours retained by provider',
                                     'witness_source':'F2 final/short-aec40 f2_window kept (first public phrase)',
                                     'cleanup':cleanup,'witness':reply},ensure_ascii=False,indent=1))
        for w in (False,True):
            out=f'injected-w{int(w)}/omitted-reply-{below}dB'
            command=[sys.executable,str(HERE/'engine.py'),out,str(probes.RD/'fixtures/sys-zhlatin-en.wav'),str(mic_path),
                     '--f2','--donor','rp-short-aec40','--inject',str(source),'--rule','.15','--quiet']
            if w:command.append('--w')
            jobs.append((out,command,5))
    recorded=json.loads((F3EV/'runs/inv-events-rule/terminal.json').read_text())
    real=[w for w in recorded['microphone']['before_rule'] if 9*S<=w[2]<15*S]
    for kind,attack in [('round4-pattern',[tup(probes.word(t,16.5+i,16.8+i,'terminal-0001')) for i,t in enumerate(['是。','哦。','六。'])]),
                        ('noise-only',[tup(probes.word(t,22+i*.2,22+(i+1)*.2,'terminal-0001')) for i,t in enumerate(['Think','about','this'])])]:
        source=fixtures/f'{kind}.json'
        source.write_text(json.dumps({'kind':'controlled live-only witnesses beside recorded real turn',
                                     'witness_source':'F3 inv-events recorded turn plus deterministic attack witnesses',
                                     'cleanup':real,'witness':real+attack},ensure_ascii=False,indent=1))
        for w in (False,True):
            out=f'injected-w{int(w)}/{kind}'
            command=[sys.executable,str(HERE/'engine.py'),out,str(F3EV/'fixtures/sys-60.wav'),str(F3EV/'fixtures/mic-events.wav'),
                     '--prefix','0','--inject',str(source),'--rule','.15','--quiet']
            if w:command.append('--w')
            jobs.append((out,command,0))
    rows=[]
    for out,command,expected in jobs:
        folder=EV/'runs'/out
        folder.mkdir(parents=True,exist_ok=True)
        with (folder/'process.log').open('w') as log:
            result=subprocess.run(command,stdout=log,stderr=log)
        assert result.returncode==0,(folder/'process.log').read_text()[-3000:]
        terminal=json.loads((folder/'terminal.json').read_text())
        receipt=json.loads((folder/'receipt.json').read_text())
        mic=terminal['microphone']
        count=mic.get('restored_words',0)
        row={'cell':out,'expected_restored':expected,'restored':count,'final_mic_words':len(mic['final_words']),
             'finalization':receipt['finalization_status'],'replayed_calls':len(receipt['batch_calls']),
             'mic_admission':[(w[0],w[2],w[3]) for w in mic['final_words']]}
        assert count==expected and len(mic['final_words'])>=expected,row
        if expected==0:assert len(mic['final_words'])==24,row
        rows.append(row)
        (EV/'injected-engine.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1)+'\n')
        print(json.dumps(row,ensure_ascii=False),flush=True)
    for i in range(0,len(rows),2):assert rows[i]['mic_admission']==rows[i+1]['mic_admission']

if __name__=='__main__':run()
