"""Known different-voice lane acceptance, before Stop and after saved/reopened output.

Run: python tests/e2e/verify_demo_lanes.py --allow-local-self-signed --case both
Alternation and overlap must both pass on the integrated per-lane decoder.
Counts-only evidence can never satisfy either oracle.
No transcript text is printed or retained. Thresholds use existing QUALITY_BOUNDS.
"""
from __future__ import annotations
import argparse
import array
import base64
import json
import ssl
import sys
import time
import urllib.request
import wave
from pathlib import Path
from urllib.parse import urlsplit
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from moss_transcribe_diarize.lane_word_oracle import score_lanes
from moss_transcribe_diarize.phase2_acceptance import QUALITY_BOUNDS
CORPUS = REPO / 'evidence/live-policy-sweep-20260825/corpus'
SHARED_TAB_VOICE = CORPUS / 'interview_bill_ackman_60s/audio.wav'
MICROPHONE_VOICE = CORPUS / 'interview_keyu_jin_60s/audio.wav'
SYSTEM_LADDER_REFERENCE = REPO / 'tests/e2e/fixtures/lane-system-ladder-reference.json'
DEFAULT_MIC_GAIN = 0.03

class Client:
    """Cookie-carrying JSON client. One bootstrap per run: each call creates a workspace."""

    def __init__(self, base: str, context: ssl.SSLContext | None):
        self._base, self._context, self._jar = base.rstrip('/'), context, {}

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {'Content-Type': 'application/json'}
        if self._jar:
            headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in self._jar.items())
        request = urllib.request.Request(self._base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, context=self._context, timeout=60) as response:
            for header in response.headers.get_all('Set-Cookie') or []:
                name, _, value = header.partition('=')
                self._jar[name] = value.split(';')[0]
            return json.loads(response.read() or b'{}')


def lane_pcm(path: Path, seconds: float, gain: float = 1.0) -> bytes:
    with wave.open(str(path)) as source:
        pcm = source.readframes(min(source.getnframes(), int(source.getframerate() * seconds)))
    if gain == 1.0:
        return pcm
    samples = array.array('h')
    samples.frombytes(pcm)
    for index in range(len(samples)):
        samples[index] = int(samples[index] * gain)
    return samples.tobytes()


def reference_inputs(mic_gain, *, system_reference: Path | None = None):
    """Use complete reference intervals, never proportional word guesses for clips."""
    result={}
    for lane,path in [('system',SHARED_TAB_VOICE),('microphone',MICROPHONE_VOICE)]:
        reference_path = system_reference if lane == 'system' and system_reference else path.with_name('reference.jsonl')
        first=json.loads(reference_path.read_text().splitlines()[0])
        if lane == 'microphone':
            # The corpus row omits an audible sentence tail inside this exact window.
            first=json.loads((REPO/'tests/e2e/fixtures/lane-microphone-reference.json').read_text())
        with wave.open(str(path)) as source:
            assert source.getframerate()==16000 and source.getnchannels()==1 and source.getsampwidth()==2
            source.setpos(round(first['start']*16000))
            pcm=source.readframes(round((first['end']-first['start'])*16000))
        samples=array.array('h');samples.frombytes(pcm)
        if lane=='microphone':
            for i in range(len(samples)): samples[i]=int(samples[i]*mic_gain)
        result[lane]={'pcm':samples.tobytes(),'reference':first['text']}
    return result


def snapshot_segments(envelope):
    session=(envelope.get('snapshot') or {}).get('session') or {}
    rows=session.get('effective_transcript') or session.get('committed') or []
    return rows.get('segments',[]) if isinstance(rows,dict) else rows


def run_case(base, context, case, mic_gain=DEFAULT_MIC_GAIN, *, client=None, realtime=True):
    client=client or Client(base,context)
    client.call('POST','/api/workspace/bootstrap')
    descriptor=client.call('GET','/api/live/descriptor')['descriptor']
    size,rate=descriptor['frame_samples'],descriptor['sample_rate']
    assert rate==16000
    inputs=reference_inputs(mic_gain)
    refs={lane:row['reference'] for lane,row in inputs.items()}
    frame_bytes=size*2
    frames={lane:(len(row['pcm'])+frame_bytes-1)//frame_bytes for lane,row in inputs.items()}
    offsets={'system':0,'microphone':frames['system'] if case=='alternation' else 0}
    total=max(offsets[lane]+frames[lane] for lane in inputs)
    created=client.call('POST','/api/live/sessions',{'source_revision':descriptor['source_revision']})
    ident=created.get('id') or created['session_id']
    epoch=time.time_ns(); started=time.monotonic(); pre=None
    try:
        for sequence in range(total):
            health=dict(state='capturing',device_epoch=epoch,dropped_frames=0,discontinuities=0,failure_code=None)
            client.call('POST',f'/api/live/sessions/{ident}/heartbeat',dict(
                schema='moss-live-helper-health.v1',instance_id='wp4-reference-replay',sequence=sequence,
                sent_monotonic_ns=time.monotonic_ns(),helper_version='reference-oracle',state='capturing',
                lanes={'system':health,'microphone':dict(health)}))
            for lane,row in inputs.items():
                index=sequence-offsets[lane]
                chunk=row['pcm'][index*frame_bytes:(index+1)*frame_bytes] if 0<=index<frames[lane] else b''
                chunk=chunk.ljust(frame_bytes,b'\0')
                client.call('POST',f'/api/live/sessions/{ident}/frames',dict(
                    lane=lane,sequence=sequence,capture_timestamp_ns=epoch+round(sequence*size/rate*1e9),
                    device_epoch=epoch,pcm_base64=base64.b64encode(chunk).decode(),sample_count=size,
                    sample_rate=rate,silent=not any(chunk),discontinuity=False))
            if realtime: time.sleep(max(0,(sequence+1)*size/rate-(time.monotonic()-started)))
        pre=client.call('GET',f'/api/live/sessions/{ident}/snapshot')
    finally:
        stopped=time.monotonic()
        client.call('POST',f'/api/live/sessions/{ident}/stop',{'deadline':30})
    deadline=time.monotonic()+240
    while True:
        saved=client.call('GET',f'/api/meetings/{ident}')
        if saved['status']!='active' or time.monotonic()>deadline: break
        time.sleep(.5)
    final=client.call('GET',f'/api/live/sessions/{ident}/snapshot')
    # A fresh GET is the reopened saved surface, independently of the live snapshot.
    reopened=client.call('GET',f'/api/meetings/{ident}')
    switches=(offsets['microphone']*size/rate,) if case=='alternation' else ()
    surfaces={
        'pre_terminal':score_lanes(snapshot_segments(pre),refs,max_wer=QUALITY_BOUNDS['immediate_wer'][1],lane_switches=switches),
        'final':score_lanes(snapshot_segments(final),refs,max_wer=QUALITY_BOUNDS['final_wer'][1],lane_switches=switches),
        'reopened':score_lanes((reopened.get('transcript') or {}).get('segments',[]),refs,max_wer=QUALITY_BOUNDS['final_wer'][1],lane_switches=switches),
    }
    # The file/URL bar is reported separately; it does not override live QUALITY_BOUNDS.
    file_url_bar = {name: all(v['wer'] is not None and v['wer'] <= .15 for v in result['lanes'].values())
                    for name, result in surfaces.items()}
    finalization=(final.get('snapshot') or {}).get('session',{}).get('finalization_status')
    passed=saved['status']=='completed' and finalization=='final' and all(s['passed'] for s in surfaces.values())
    return dict(case=case,meeting=ident,passed=passed,expected_failure=False,
                status=saved['status'],finalization_status=finalization,seconds=round(time.monotonic()-started,3),
                stop_seconds=round(time.monotonic()-stopped,3),frames_per_lane=total,
                microphone_gain=mic_gain,surfaces=surfaces,file_url_wer_bar=.15,file_url_wer_pass=file_url_bar)


def accepted_case(result):
    # Completion alone cannot hide a semantic failure on either supported lane case.
    return result['status']=='completed' and result['finalization_status']=='final' and result['passed']


def run_cases(base,context,case='both',mic_gain=DEFAULT_MIC_GAIN):
    cases=('alternation','overlap') if case=='both' else (case,)
    return [run_case(base,context,name,mic_gain) for name in cases]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='https://127.0.0.1:17861')
    parser.add_argument('--allow-local-self-signed',action='store_true')
    parser.add_argument('--case',choices=['alternation','overlap','both'],default='both')
    parser.add_argument('--mic-gain',type=float,default=DEFAULT_MIC_GAIN)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    context=None
    if args.allow_local_self_signed:
        if urlsplit(args.base).hostname not in {'127.0.0.1','::1','localhost'}: parser.error('TLS bypass is loopback-only')
        context=ssl._create_unverified_context()
    results=[]
    for case in ('alternation','overlap') if args.case=='both' else (args.case,):
        result=run_case(args.base,context,case,args.mic_gain)
        results.append(result)
        print(json.dumps(result),flush=True)
        if args.output: args.output.write_text(json.dumps(results,indent=2)+'\n')
    return int(not all(accepted_case(r) for r in results))

if __name__=='__main__': raise SystemExit(main())
