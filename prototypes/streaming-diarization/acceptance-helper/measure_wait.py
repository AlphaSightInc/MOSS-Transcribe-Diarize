"""Create one fresh local workspace; prove an idle replay owner renews a 30s lease."""
import argparse,asyncio,json,os,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService,SESSION_COOKIE

p=argparse.ArgumentParser();p.add_argument('--base',default='https://127.0.0.1:17861');p.add_argument('--ca',required=True);p.add_argument('--out',required=True);a=p.parse_args()
os.environ['SSL_CERT_FILE']=a.ca
with tempfile.TemporaryDirectory(prefix='moss-lease-wait-') as directory:
    with httpx.Client(verify=a.ca) as client:
        client.post(a.base+"/api/workspace/bootstrap").raise_for_status()
        cookie=client.cookies.get(SESSION_COOKIE)
    if not cookie:raise RuntimeError('fresh workspace did not issue a cookie')
    path=Path(directory)/'cookie';path.write_text(cookie);path.chmod(0o600)
    adapter=AccountCookieLiveReplayService(base_url=a.base,cookie_file=path)
    beats=[];request=adapter._json
    def observed(method,path,payload=None,**kwargs):
        value=request(method,path,payload,**kwargs)
        if path.endswith('/heartbeat'):beats.append({'sequence':payload['sequence'],'t':time.monotonic()})
        return value
    adapter._json=observed
    ident=None
    try:
        created=adapter.create();ident=created.session_id
        start=time.monotonic();time.sleep(35)
        snapshot=adapter.snapshot(ident)
        result={'wait_seconds':time.monotonic()-start,'heartbeats':len(beats),'sequences':[x['sequence'] for x in beats],
                'maximum_heartbeat_gap_seconds':max((b['t']-a['t'] for a,b in zip(beats,beats[1:])),default=None),
                'session_status':snapshot.session.status,'failure_reason':snapshot.session.failure_reason,
                'accepted_samples':snapshot.session.accepted_samples}
        result['ok']=result['session_status']=='active' and result['heartbeats']>=6 and result['accepted_samples']==0
        Path(a.out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:
        if ident:asyncio.run(adapter.abort(ident,'acceptance helper wait probe complete'))
        adapter.close()
