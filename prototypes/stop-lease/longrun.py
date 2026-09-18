"""WP15 isolated real-decoder durability probe; no deployment or shared writes.

COMMON Python + PYTHONPATH=. python prototypes/stop-lease/longrun.py --seconds 600
Default cumulative WP15 budget is 200. Increase only with explicit authorization.
200 + 600/1800 seconds are not assumed compatible; exhaustion is recorded, not retried.
"""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import http.cookiejar
import wave
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
HOST='gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us'
CORPUS=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,choices=[600,1800],required=True)
    p.add_argument('--total-budget',type=int,default=200)
    p.add_argument('--prepare-only',action='store_true')
    a=p.parse_args()
    clips=[]
    for name in ['interview_bill_ackman_60s','interview_keyu_jin_60s']:
        with wave.open(str(CORPUS/name/'audio.wav')) as w:
            assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(16000,1,2)
            clips.append(w.readframes(w.getnframes()))
    clips[1]=np.rint(np.frombuffer(clips[1],dtype='<i2').astype(float)*10**(-10/20)).astype('<i2').tobytes()
    used=0
    for requests in (ROOT/'.wp15').glob('real-*/state/requests.jsonl'):
        used+=len(requests.read_text().splitlines())
    remaining=a.total_budget-used
    if a.prepare_only:
        print(json.dumps(dict(prepared=True,seconds=a.seconds,system_samples=len(clips[0])//2,microphone_samples=len(clips[1])//2,microphone_db=-10,microphone_active_seconds=300,used_requests=used,remaining_requests=remaining)))
        return
    if remaining<=0: raise SystemExit('WP15 cumulative request budget exhausted')
    stamp=f'real-{time.time_ns()}'
    scratch=Path('.wp15')/stamp
    scratch.mkdir(parents=True)
    out=ROOT/'evidence/mvpfix/wp15'/stamp
    out.mkdir()
    result=dict(seconds_requested=a.seconds,source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        total_budget=a.total_budget,prior_requests=used,remaining_budget=remaining,resources=[],events=[],outcome='unfinished',contention_policy='record_only_no_pause')
    processes=[]
    rss_stop=threading.Event()
    rss_thread=None
    client=None
    ident=None
    state=scratch/'state'
    def emit(kind,**kw):
        row=dict(kind=kind,time=time.monotonic(),**kw)
        with (out/'actions.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        print(json.dumps(row),flush=True)
    def metrics():
        with urllib.request.urlopen('http://127.0.0.1:18115/metrics',timeout=5) as r:body=r.read().decode()
        answer={}
        for key in ['num_requests_running','num_requests_waiting','request_success_total']:
            matches=re.findall(r'^vllm:'+key+r'(?:\{[^\n]*\})?\s+([0-9.eE+-]+)',body,re.M)
            if not matches:raise RuntimeError('missing metrics '+key)
            answer[key]=sum(map(float,matches))
        return answer
    try:
        # Reuse WP6's isolated manifest construction, redirecting only its destination.
        source=(ROOT/'prototypes/capacity-campaign/copy_manifest.py').read_text().replace("Path('.wp6-tmp/manifest-30m.json')",repr(str(scratch/'manifest.json')))
        source=source.replace('destination = '+repr(str(scratch/'manifest.json')), 'destination = Path('+repr(str(scratch/'manifest.json'))+')')
        with (out/'manifest.txt').open('w') as log:
            subprocess.run([sys.executable,'-c',source],check=True,stdout=log)
        tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-L','127.0.0.1:18115:127.0.0.1:8000',HOST],stderr=(scratch/'ssh.log').open('w'))
        processes.append(tunnel)
        for sample in range(60):
            if tunnel.poll() is not None:raise RuntimeError('private tunnel failed')
            try:m=metrics()
            except OSError:
                time.sleep(1);continue
            emit('preflight',metrics=m)
            break
        else:raise RuntimeError('GPU metrics unavailable before capture')
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(scratch/'key.pem'),'-out',str(scratch/'cert.pem'),'-days','2','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT),TMPDIR=str(ROOT/'.wp15/t'))
        app=subprocess.Popen([sys.executable,'prototypes/capacity-campaign/stack.py','--state',str(state),'--cert',str(scratch/'cert.pem'),'--key',str(scratch/'key.pem'),'--port','17875','--vllm-base-url','http://127.0.0.1:18115/v1','--max-requests',str(remaining),'--manifest',str(scratch/'manifest.json')],env=env,stdout=(scratch/'app.log').open('w'),stderr=subprocess.STDOUT)
        processes.append(app)
        def sample_rss():
            while not rss_stop.is_set():
                rss=subprocess.run(['ps','-o','rss=','-p',str(app.pid)],capture_output=True,text=True)
                if rss.returncode!=0:break
                with (out/'rss.jsonl').open('a') as stream:
                    stream.write(json.dumps(dict(time=time.monotonic(),rss_bytes=int(rss.stdout)*1024))+'\n')
                rss_stop.wait(30)
        rss_thread=threading.Thread(target=sample_rss)
        rss_thread.start()
        base='https://127.0.0.1:17875'
        client=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(scratch/'cert.pem'))),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def call(method,path,data=None,raw=False):
            request=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json','Origin':base})
            with client.open(request,timeout=40) as r:
                payload=r.read()
                return (r.status,payload if raw else json.loads(payload))
        for _ in range(60):
            if app.poll() is not None:raise RuntimeError('local stack failed')
            try:call('POST','/api/workspace/bootstrap',{});break
            except OSError:time.sleep(1)
        else:raise RuntimeError('stack readiness timeout')
        descriptor=call('GET','/api/live/descriptor')[1]['descriptor']
        (out/'descriptor.json').write_text(json.dumps(descriptor,indent=2)+'\n')
        ident=call('POST','/api/live/sessions',{'source_revision':descriptor['source_revision']})[1]['id']
        route=f'/api/live/sessions/{ident}'
        epoch=time.time_ns(); hbseq=0; eventseq=0; previous=None; next_sample=0
        fs=descriptor['frame_samples'];sr=descriptor['sample_rate'];cadence=fs/sr
        started=time.monotonic(); acknowledged=0
        previous_metric=m; previous_own=dict(sent=0,active=0)
        result['foreign_load_detected']=False
        def own_requests():
            rows=[]
            path=state/'decoder.jsonl'
            if path.exists():
                for line in path.read_text().splitlines():
                    try:rows.append(json.loads(line))
                    except json.JSONDecodeError:pass
            return rows
        def heartbeat():
            nonlocal hbseq
            h=dict(state='capturing',device_epoch=epoch,dropped_frames=0,discontinuities=0,failure_code=None)
            call('POST',route+'/heartbeat',dict(schema='moss-live-helper-health.v1',instance_id='wp15',sequence=hbseq,sent_monotonic_ns=time.monotonic_ns(),helper_version='bench',state='capturing',lanes=dict(system=h,microphone=h)))
            hbseq+=1
        def observe(force=False):
            nonlocal eventseq,previous,next_sample,previous_metric,previous_own
            snap=call('GET',route+'/snapshot')[1]['snapshot']
            for e in call('GET',route+f'/events?since_seq={eventseq}')[1]['events']:
                if e['seq']!=eventseq:raise RuntimeError('event ring overrun')
                eventseq=e['seq']+1
                if e['kind'] in ['stop_requested','session_closed','session_aborted','terminal_failure','session_tape_released'] or e['kind'].startswith('terminal_finalization'):
                    result['events'].append(e)
            status=(snap['session']['status'],snap['session']['finalization_status'])
            if status!=previous:emit('transition',status=status,accepted=snap['session']['accepted_samples'],accounted=snap['session']['accounted_samples']);previous=status
            if force or time.monotonic()-started>=next_sample:
                before=own_requests()
                m=metrics()
                after=own_requests()
                active=max([r['active'] for r in before[-1:]+after[len(before):]] or [0])
                own_after=after[-1] if after else dict(sent=0,active=0)
                shared=m['request_success_total']-previous_metric['request_success_total']
                possible=own_after['sent']-previous_own['sent']+previous_own['active']
                foreign_completions=max(0,shared-possible)
                foreign=m['num_requests_running']+m['num_requests_waiting']>active or foreign_completions>0
                previous_metric=m
                previous_own=before[-1] if before else dict(sent=0,active=0)
                if foreign:result['foreign_load_detected']=True
                row=dict(elapsed=time.monotonic()-started,rss_bytes=int(subprocess.check_output(['ps','-o','rss=','-p',str(app.pid)],text=True))*1024,metrics=m,own_sent=own_after['sent'],own_active=active,foreign_completion_lower_bound=foreign_completions,foreign_load_detected=foreign,accepted=snap['session']['accepted_samples'],accounted=snap['session']['accounted_samples'],pending=snap.get('pending_work_items'))
                result['resources'].append(row);emit('resource',**row);next_sample+=30
            return snap
        for seq in range(round(a.seconds/cadence)):
            heartbeat()
            for lane,index in [('system',0),('microphone',1)]:
                offset=(seq*fs*2)%len(clips[index]);data=(clips[index]*2)[offset:offset+fs*2]
                if lane=='microphone' and seq*cadence>=300:data=bytes(fs*2)
                frame=dict(lane=lane,sequence=seq,capture_timestamp_ns=epoch+round(seq*cadence*1e9),device_epoch=epoch,pcm_base64=base64.b64encode(data).decode(),sample_count=fs,sample_rate=sr,silent=data==bytes(fs*2),discontinuity=False)
                retry_start=time.monotonic()
                while True:
                    try:call('POST',route+'/frames',frame);acknowledged+=1;break
                    except urllib.error.HTTPError as exc:
                        if exc.code!=429 or time.monotonic()-retry_start>30:raise
                        heartbeat();time.sleep(cadence)
            snap=observe()
            result['acknowledged_frames']=acknowledged
            if snap['terminal_failure'] is not None:raise RuntimeError('runtime terminal failure')
            time.sleep(max(0,started+(seq+1)*cadence-time.monotonic()))
        result['capture_elapsed_seconds']=time.monotonic()-started
        result['capture_paused_seconds']=0.0
        stopped=time.monotonic()
        result['stop_requested_monotonic']=stopped
        http_status,payload=call('POST',route+'/stop',{'deadline':30})
        emit('stop_response',http_status=http_status,code=payload.get('code'))
        while True:
            snap=observe()
            saved=call('GET',f'/api/meetings/{ident}')[1]
            if saved['status']!='active':break
            if time.monotonic()-stopped>1800:raise RuntimeError('terminal observation exceeded 30 minutes')
            time.sleep(.5)
        elapsed=time.monotonic()-stopped
        words=[s['text'] for s in saved['transcript']['segments']]
        result.update(outcome=snap['session']['finalization_status'],saved_status=saved['status'],stop_to_outcome_seconds=elapsed,stop_to_final_seconds=elapsed if snap['session']['finalization_status']=='final' else None,saved_words=sum(len(s.split()) for s in words),accepted_samples=snap['session']['accepted_samples'],accounted_samples=snap['session']['accounted_samples'],audio=saved['audio'])
        (scratch/'snapshot.json').write_text(json.dumps(snap))
        audio=call('GET',f'/api/meetings/{ident}/audio/download',raw=True)[1]
        (scratch/'saved.mp3').write_bytes(audio)
        result['mp3_probe']=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,sample_rate,channels','-of','json',str(scratch/'saved.mp3')],text=True))
        result['snapshot_saved_words_equal']=words==[s['text'] for s in snap['session']['effective_transcript']]
        observe(force=True)
    except Exception as exc:
        result['error']=type(exc).__name__
        if isinstance(exc,RuntimeError):result['reason']=str(exc)
        if isinstance(exc,urllib.error.HTTPError):result['http_status']=exc.code
        emit('failed',error=result['error'],reason=result.get('reason'),http_status=result.get('http_status'))
        if client and ident:
            try:call('POST',f'/api/live/sessions/{ident}/abort',{'reason':'WP15 isolated measurement cleanup'})
            except Exception:pass
    finally:
        rss_stop.set()
        if rss_thread is not None:rss_thread.join()
        for process in reversed(processes):
            process.terminate()
            try:process.wait(20)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        requests=state/'requests.jsonl'
        result['decoder_requests']=len(requests.read_text().splitlines()) if requests.exists() else 0
        if ident and (state/'phase2.sqlite').exists():
            connection=sqlite3.connect((state/'phase2.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
            row=connection.execute('SELECT status FROM meetings WHERE meeting_id=?',(ident,)).fetchone()
            result['restart_sqlite_status']=None if row is None else row[0]
            connection.close()
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(output=str(out),outcome=result['outcome'],requests=result['decoder_requests'])),flush=True)

if __name__=='__main__':main()
