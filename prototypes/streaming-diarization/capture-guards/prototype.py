"""THROWAWAY signal experiment; no production policy. Run with --offline or --decode.
Question: can a delayed scalar playback estimate distinguish leakage from quiet speech?
Hypothesis: explained energy separates the cases. Falsifier: any near speech skipped.
Primitives: aligned PCM, delay, fitted gain, unexplained energy. No sample modification.
Unknown: physical AEC/nonlinear rooms. A synthetic result cannot establish those.
"""
import argparse, json, re, time, wave
from pathlib import Path
import numpy as np
from scipy.signal import correlate

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'evidence/live-policy-sweep-20260825/corpus'
SR = 16000

def read(name):
    with wave.open(str(CORPUS / name / 'audio.wav')) as f:
        assert f.getframerate() == SR
        return np.frombuffer(f.readframes(SR*60), dtype='<i2').astype(float) / 32768

def pcm(x):
    return np.clip(np.rint(x*32768), -32768, 32767).astype('<i2').tobytes()

def statistic(system, mic):
    energy = float(mic @ mic)
    if energy == 0:
        return dict(decision='skip-zero', explained=0., delay_samples=0, gain=0.)
    c = correlate(mic, system, mode='full', method='fft')[len(system)-1:len(system)+960]
    e = np.cumsum(system**2)[len(system)-1-np.arange(len(c))]
    scores = c*c / np.maximum(e*energy, 1e-30)
    d = int(np.argmax(scores)); gain = float(c[d]/max(e[d], 1e-30))
    score = min(1., float(scores[d]))
    # Experimental candidate only: 99% explained energy. Must survive falsifiers.
    return dict(decision='leak-suspect' if score >= .99 else 'decode', explained=score, delay_samples=d, gain=gain)

def words(s): return re.findall(r'[a-z0-9]+', s.lower())
def metrics(ref, hyp):
    r, h = words(ref), words(hyp); prev = list(range(len(h)+1))
    for i,a in enumerate(r,1):
        cur=[i]
        for j,b in enumerate(h,1): cur.append(min(cur[-1]+1,prev[j]+1,prev[j-1]+(a!=b)))
        prev=cur
    return dict(reference_words=len(r), emitted_words=len(h), edit_distance=prev[-1], wer=prev[-1]/max(1,len(r)), unique_retained=len(set(r)&set(h)), unique_reference=len(set(r)))
def reference(name):
    return ' '.join(json.loads(s)['text'] for s in (CORPUS/name/'reference.jsonl').read_text().splitlines())
def cases(s,n):
    rng=np.random.default_rng(3)
    yield 'zero',np.zeros_like(s),False
    for noise in [-45,-60]: yield f'noise{noise}',rng.normal(size=len(s))*10**(noise/20),False
    for near in [None,-10,-15,-20]:
        for bleed in [-10,-30,-50,-70]:
            for delay in [5,30,60]:
                for noise in [None,-45,-60]:
                    d=SR*delay//1000
                    x=np.r_[np.zeros(d),s[:-d]]*10**(bleed/20)
                    if near is not None: x=x+n*10**(near/20)
                    if noise is not None: x=x+rng.normal(size=len(s))*10**(noise/20)
                    yield f'near{near}_bleed{bleed}_delay{delay}_noise{noise}', x, near is not None

def main():
    p=argparse.ArgumentParser();p.add_argument('--decode',action='store_true');p.add_argument('--offline',action='store_true');a=p.parse_args()
    s=read('interview_bill_ackman_60s');n=read('interview_keyu_jin_60s')
    rows=[]; samples=[]
    for name,x,near in cases(s,n):
        x=np.frombuffer(pcm(x),dtype='<i2').astype(float)/32768
        row=dict(name=name, near=near, **statistic(s,x));rows.append(row);print(json.dumps(row),flush=True)
        samples.append((name,x,near,row))
    (ROOT/'evidence/mvpfix/wp3/offline.json').write_text(json.dumps(rows,indent=2))
    if not a.decode:return
    from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference
    from moss_transcribe_diarize.app.live_session import FrozenSpan
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    from moss_transcribe_diarize.transcript_parser import parse_transcript
    dec=RunnerBoundedWavInference(VllmRunner(base_url='http://127.0.0.1:18103/v1',model='OpenMOSS-Team/MOSS-Transcribe-Diarize',timeout=600),max_samples=len(s),scratch_dir=ROOT/'evidence/mvpfix/wp3')
    refs={False:reference('interview_bill_ackman_60s'),True:reference('interview_keyu_jin_60s')}
    baselines={};results=[]
    # 3 quiet baselines + 3 empty/noise + 12 echo + 27 mixed = 45 sequential calls.
    selected=[(f'baseline{level}',n*10**(level/20),True,dict(decision='decode')) for level in [-10,-15,-20]]
    selected += [v for v in samples if v[0] in ['zero','noise-45','noise-60'] or (not v[2] and 'delay30' in v[0]) or (v[2] and 'bleed-10_' in v[0])]
    for i,(name,x,near,row) in enumerate(selected):
        started=time.monotonic();out=dec.transcribe_pcm(span=FrozenSpan(id=i,epoch=1,start_sample=0,end_sample=len(x),reason='end_silence'),pcm=pcm(x))
        parsed=parse_transcript(out.transcript); text=' '.join(seg.text for seg in parsed)
        result=dict(name=name,decision=row['decision'],seconds=time.monotonic()-started,vs_reference=metrics(refs[near],text))
        if name.startswith('baseline'):baselines[int(name[8:])]=text
        elif near:
            level=int(name.split('_')[0][4:]);result['vs_lane_alone']=metrics(baselines[level],text)
            result['guard_vs_lane_alone']=metrics(baselines[level],'' if row['decision']!='decode' else text)
        result['vs_playback']=metrics(refs[False],text)
        results.append(result);print(json.dumps(result),flush=True)
        (ROOT/'evidence/mvpfix/wp3/decoder.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':main()
