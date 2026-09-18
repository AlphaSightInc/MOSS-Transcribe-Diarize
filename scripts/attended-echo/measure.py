"""Attended kit: serve explicitly, then score saved physical capture. Never auto-capture.
python scripts/attended-echo/measure.py serve
python scripts/attended-echo/measure.py score capture.json --playback-text playback.txt --base http://127.0.0.1:18103/v1
"""
import argparse, base64, http.server, json, re, time
from pathlib import Path
import numpy as np
from moss_transcribe_diarize.app.live_capture_guard import observe_capture_span
from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference
from moss_transcribe_diarize.app.live_session import FrozenSpan
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.transcript_parser import parse_transcript
PHRASE='The quiet blue river passes seven old bridges while the morning train carries fresh oranges into town.'

def score(reference, text):
    r=re.findall('[a-z0-9]+',reference.lower()); h=re.findall('[a-z0-9]+',text.lower());row=list(range(len(h)+1))
    for i,a in enumerate(r,1):
        next_row=[i]
        for j,b in enumerate(h,1):next_row.append(min(next_row[-1]+1,row[j]+1,row[j-1]+(a!=b)))
        row=next_row
    return dict(reference_words=len(r),emitted_words=len(h),edits=row[-1],wer=row[-1]/max(1,len(r)),unique_reference=len(set(r)),unique_retained=len(set(r)&set(h)))

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=18733)
    s=sub.add_parser('score');s.add_argument('recording',type=Path);s.add_argument('--playback-text',type=Path,required=True);s.add_argument('--base',required=True)
    args=p.parse_args()
    if args.command=='serve':
        import functools
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(Path(__file__).parent))
        print(f'Open http://127.0.0.1:{args.port}/capture.html; Ctrl-C stops server.',flush=True)
        http.server.HTTPServer(('127.0.0.1',args.port),handler).serve_forever();return
    data=json.loads(args.recording.read_text());assert data['schema']=='moss-attended-echo-v1'
    assert data['sample_rate']==16000,'Capture at 16 kHz; do not reinterpret another rate.'
    assert data['settings']['physical_attended'] is True
    lane={k:np.frombuffer(base64.b64decode(v['pcm16_base64']),dtype='<i2').astype(float)/32768 for k,v in data['lanes'].items()}
    n=data['sample_count'];assert all(len(x)==n for x in lane.values())
    # Production mixer headroom and soft limiter for the same-recording mono comparison.
    mixed=(lane['system']+lane['microphone'])*10**(-6/20)
    mask=np.abs(mixed)>.98;mixed[mask]=np.sign(mixed[mask])*(.98+.02*np.tanh((np.abs(mixed[mask])-.98)/.02));lane['mono']=mixed
    decoder=RunnerBoundedWavInference(VllmRunner(base_url=args.base,model='OpenMOSS-Team/MOSS-Transcribe-Diarize'),max_samples=n,scratch_dir=args.recording.parent)
    result={'status':'ATTENDED_RECORDING_SCORED','settings':data['settings'],'sample_count':n,'decodes':{},'spans':[]}
    playback=args.playback_text.read_text()
    for name,x in lane.items():
        started=time.monotonic();pcm=np.clip(np.rint(x*32768),-32768,32767).astype('<i2').tobytes()
        out=decoder.transcribe_pcm(span=FrozenSpan(id=1,epoch=0,start_sample=0,end_sample=n,reason='end_silence'),pcm=pcm)
        text=' '.join(s.text for s in parse_transcript(out.transcript))
        result['decodes'][name]={'seconds':time.monotonic()-started,'vs_playback':score(playback,text),'vs_printed_phrase':score(PHRASE,text)}
    for start in range(0,n,8000):
        result['spans'].append(dict(start_sample=start,**observe_capture_span(lane['system'][start:start+8000],lane['microphone'][start:start+8000],sample_rate=16000)))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
