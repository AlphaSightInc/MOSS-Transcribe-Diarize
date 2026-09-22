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
TAIL_SETTLE_TIMEOUT_SECONDS = 5.0
_TAIL_ENDPOINT_REASONS = frozenset({'end_silence', 'hard_cap', 'stop_flush', 'none'})
_IDENTITY_TELEMETRY_KEYS = frozenset({
    'identity_unqualified', 'unattributed_segment_count', 'unattributed_word_count',
})

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
    rows=session.get('effective_transcript') or []
    return rows.get('segments',[]) if isinstance(rows,dict) else rows


def _last_non_silent_sample_end(pcm, sequence, frame_samples):
    samples=array.array('h'); samples.frombytes(pcm)
    for index in range(len(samples)-1,-1,-1):
        if samples[index]: return sequence*frame_samples+index+1
    return None


def _session_snapshot(envelope):
    snapshot=envelope.get('snapshot') or {}
    session=snapshot.get('session') or {}
    if not isinstance(session,dict): raise ValueError('live snapshot session is not an object')
    return snapshot,session


def _tail_endpoint_reason(events,last_speech_sample):
    candidates=[]
    for event in events:
        if not isinstance(event,dict) or event.get('kind')!='span_frozen': continue
        payload=event.get('payload') or {}
        try:
            start,end=int(payload['start_sample']),int(payload['end_sample'])
        except (KeyError,TypeError,ValueError): continue
        if start < last_speech_sample <= end:
            candidates.append((end,start,int(event.get('seq',-1)),payload.get('reason')))
    if not candidates:
        # Runtime emits the Stop-created endpoint partition as a public queued item
        # (`reason=stop`), while only frame-created partitions have `span_frozen`.
        if any(isinstance(event,dict) and event.get('kind')=='canonical_queued'
               and (event.get('payload') or {}).get('reason')=='stop' for event in events):
            return 'stop_flush'
        return 'none'
    reason=max(candidates)[3]
    return reason if reason in _TAIL_ENDPOINT_REASONS else 'none'


def _settle_facts(envelope,events,last_speech_sample):
    snapshot,session=_session_snapshot(envelope)
    queued={str((event.get('payload') or {}).get('item_id')) for event in events
            if isinstance(event,dict) and event.get('kind')=='canonical_queued'
            and (event.get('payload') or {}).get('item_id') is not None}
    processed={str((event.get('payload') or {}).get('item_id')) for event in events
               if isinstance(event,dict) and event.get('kind')=='canonical_processed'
               and (event.get('payload') or {}).get('item_id') is not None}
    effective_covers_last_speech=any(
        int(segment.get('start_sample',last_speech_sample)) < last_speech_sample <= int(segment.get('end_sample',0))
        for segment in snapshot_segments(envelope) if isinstance(segment,dict))
    stop_requested=any(isinstance(event,dict) and event.get('kind')=='stop_requested' for event in events)
    pending_work=snapshot.get('pending_work_items')
    committed_samples=session.get('committed_samples')
    settled=(session.get('status')=='active' and not stop_requested
             and not session.get('pending_span_ids') and pending_work==0
             and isinstance(committed_samples,int) and committed_samples>=last_speech_sample
             and not (queued-processed) and effective_covers_last_speech)
    return dict(settled=settled,status=session.get('status'),stop_requested=stop_requested,
                effective_covers_last_speech=effective_covers_last_speech,
                pending_canonical_item_count=len(queued-processed))


def _has_identity_telemetry(score):
    """Require scorer-owned attribution telemetry; older scorers cannot qualify a case."""
    if not isinstance(score,dict) or not _IDENTITY_TELEMETRY_KEYS <= score.keys(): return False
    return (isinstance(score['identity_unqualified'],bool)
            and all(isinstance(score[key],int) and not isinstance(score[key],bool)
                    and score[key]>=0
                    for key in ('unattributed_segment_count','unattributed_word_count')))


def run_case(base, context, case, mic_gain=DEFAULT_MIC_GAIN, *, client=None, realtime=True,
             _stream_tail_silence=True, _clock=time.monotonic):
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
    epoch=time.time_ns(); started=_clock(); pre=None
    last_speech_sample=None; last_speech_captured_at=None
    silence_frames_streamed=0; pre_events=[]; pre_facts=None; pre_observed_at=None; pre_settled_observed_at=None
    first_cover_observed_at=None; settle='TIMEOUT'
    post_stop_events=[]
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
                sample_end=_last_non_silent_sample_end(chunk,sequence,size)
                if sample_end is not None and (last_speech_sample is None or sample_end>=last_speech_sample):
                    last_speech_sample=sample_end
                    last_speech_captured_at=_clock()
            if realtime: time.sleep(max(0,(sequence+1)*size/rate-(time.monotonic()-started)))
        if last_speech_sample is None or last_speech_captured_at is None: raise AssertionError('no non-silent captured sample')
        settle_deadline=last_speech_captured_at+TAIL_SETTLE_TIMEOUT_SECONDS

        def poll_snapshot():
            nonlocal first_cover_observed_at
            candidate=client.call('GET',f'/api/live/sessions/{ident}/snapshot')
            # Deadline is defined by receipt of the snapshot, before a slow events read.
            observed_at=_clock()
            events=client.call('GET',f'/api/live/sessions/{ident}/events?since_seq=-1').get('events',[])
            facts=_settle_facts(candidate,events,last_speech_sample)
            settled_observed_at=_clock()
            if facts['effective_covers_last_speech'] and first_cover_observed_at is None:
                first_cover_observed_at=observed_at
            return candidate,events,facts,observed_at,settled_observed_at

        sequence=total
        while _stream_tail_silence and pre is None:
            health=dict(state='capturing',device_epoch=epoch,dropped_frames=0,discontinuities=0,failure_code=None)
            client.call('POST',f'/api/live/sessions/{ident}/heartbeat',dict(
                schema='moss-live-helper-health.v1',instance_id='wp4-reference-replay',sequence=sequence,
                sent_monotonic_ns=time.monotonic_ns(),helper_version='reference-oracle',state='capturing',
                lanes={'system':health,'microphone':dict(health)}))
            zero=b'\0'*frame_bytes
            for lane in inputs:
                client.call('POST',f'/api/live/sessions/{ident}/frames',dict(
                    lane=lane,sequence=sequence,capture_timestamp_ns=epoch+round(sequence*size/rate*1e9),
                    device_epoch=epoch,pcm_base64=base64.b64encode(zero).decode(),sample_count=size,
                    sample_rate=rate,silent=True,discontinuity=False))
            silence_frames_streamed+=1
            if realtime: time.sleep(max(0,(sequence+1)*size/rate-(time.monotonic()-started)))
            candidate,events,facts,observed_at,settled_observed_at=poll_snapshot()
            # A snapshot arriving at the deadline is already too late, even if settled.
            if observed_at >= settle_deadline:
                pre,pre_events,pre_facts,pre_observed_at,pre_settled_observed_at=(
                    candidate,events,facts,observed_at,settled_observed_at)
                settle='TIMEOUT'
            elif facts['settled']:
                pre,pre_events,pre_facts,pre_observed_at,pre_settled_observed_at=(
                    candidate,events,facts,observed_at,settled_observed_at)
                settle='SETTLED'
            sequence+=1
        if pre is None:
            pre,pre_events,pre_facts,pre_observed_at,pre_settled_observed_at=poll_snapshot()
        if not _stream_tail_silence:
            settle='SETTLED' if (pre_observed_at < settle_deadline and pre_facts['settled']) else 'TIMEOUT'
        first_cover_latency_seconds=(round(first_cover_observed_at-last_speech_captured_at,6)
                                     if first_cover_observed_at is not None else None)
        tail_latency_seconds=(round(pre_settled_observed_at-last_speech_captured_at,6)
                              if settle=='SETTLED' and pre_facts['effective_covers_last_speech'] else None)
        tail_endpoint_reason_pre=_tail_endpoint_reason(pre_events,last_speech_sample)
    finally:
        stopped=_clock()
        client.call('POST',f'/api/live/sessions/{ident}/stop',{'deadline':30})
        # Stop may finalize and discard the live event buffer on a later meeting read.
        # This fetch is therefore immediately after Stop, while still post-Stop.
        post_stop_events=client.call('GET',f'/api/live/sessions/{ident}/events?since_seq=-1').get('events',[])
    deadline=_clock()+240
    while True:
        saved=client.call('GET',f'/api/meetings/{ident}')
        if saved['status']!='active' or _clock()>deadline: break
        time.sleep(.5)
    tail_endpoint_reason=_tail_endpoint_reason(post_stop_events,last_speech_sample)
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
    d31_passed=(settle=='SETTLED' and tail_endpoint_reason_pre=='end_silence'
                and tail_endpoint_reason=='end_silence' and not pre_facts['stop_requested'])
    identity_telemetry_missing=any(not _has_identity_telemetry(score) for score in surfaces.values())
    identity_qualified=(not identity_telemetry_missing
                        and all(not score['identity_unqualified'] for score in surfaces.values()))
    passed=(saved['status']=='completed' and finalization=='final' and d31_passed
            and all(s['passed'] for s in surfaces.values()) and identity_qualified)
    return dict(case=case,meeting=ident,passed=passed,expected_failure=False,
                status=saved['status'],finalization_status=finalization,seconds=round(time.monotonic()-started,3),
                stop_seconds=round(time.monotonic()-stopped,3),frames_per_lane=total,
                microphone_gain=mic_gain,surfaces=surfaces,file_url_wer_bar=.15,file_url_wer_pass=file_url_bar,
                tail_latency_seconds=tail_latency_seconds,first_cover_latency_seconds=first_cover_latency_seconds,
                tail_endpoint_reason_pre=tail_endpoint_reason_pre,tail_endpoint_reason=tail_endpoint_reason,
                settle=settle,silence_frames_streamed=silence_frames_streamed,
                pre_snapshot_status=pre_facts['status'],stop_requested_before_pre=pre_facts['stop_requested'],
                identity_telemetry_missing=identity_telemetry_missing)


def accepted_case(result):
    # Completion alone cannot hide a semantic failure on either supported lane case.
    surfaces=tuple(result.get('surfaces',{}).values())
    return (result['status']=='completed' and result['finalization_status']=='final' and result['passed']
            and result.get('identity_telemetry_missing') is False and bool(surfaces)
            and all(_has_identity_telemetry(score) and not score['identity_unqualified']
                    for score in surfaces))


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
