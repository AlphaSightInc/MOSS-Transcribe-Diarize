"""One-command generation; owns/stops all child servers and the 18124 tunnel."""
import json,os,shutil,ssl,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];PY=sys.executable
SOURCE=ROOT/'evidence/mvpfix/wp24';SCRATCH=ROOT/'.wp24';HERE=Path(__file__).parent

def main():
    target=Path(sys.argv[sys.argv.index('--regenerate')+1]).resolve()
    assert target.is_relative_to(ROOT) and target!=SOURCE
    target.mkdir(parents=True,exist_ok=True)
    (SCRATCH/'tmp').mkdir(parents=True,exist_ok=True)
    if not (SCRATCH/'cert.pem').exists():
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(SCRATCH/'key.pem'),'-out',str(SCRATCH/'cert.pem'),'-days','2','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for name in ('live-source.json','interrupted-source.json'):
        shutil.copyfile(SOURCE/name,target/name)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT),TMPDIR=str(SCRATCH/'tmp'),WP24_EVIDENCE_ROOT=str(target))
    processes=[];logs=[]
    def start(cmd,name,**extra):
        log=(SCRATCH/(name+'.log')).open('w');logs.append(log)
        proc=subprocess.Popen(cmd,cwd=ROOT,env=dict(env,**extra),stdout=log,stderr=subprocess.STDOUT);processes.append(proc);return proc
    def wait_url(url,process):
        for _ in range(120):
            if process.poll() is not None:raise RuntimeError(f'Owned process exited {process.returncode}: {url}')
            try:
                with urllib.request.urlopen(url,context=ssl._create_unverified_context(),timeout=1) as r:return r.read()
            except Exception:time.sleep(.5)
        raise RuntimeError('Stack readiness timeout: '+url)
    before=sum(len(p.read_text().splitlines()) for p in (SCRATCH/'state'/'requests.jsonl',SCRATCH/'regen-state'/'requests.jsonl') if p.exists())
    # Cumulative WP24 budget includes earlier measurement runs, retained across regeneration.
    budget=SCRATCH/'consumed.json'
    used=max(before,json.loads(budget.read_text())['requests'] if budget.exists() else 0)
    if used>=150:raise RuntimeError('WP24 150-request budget exhausted')
    state=SCRATCH/'regen-state'
    if state.exists():shutil.rmtree(state)
    try:
        tunnel=start(['ssh','-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','StrictHostKeyChecking=yes','-L','127.0.0.1:18124:127.0.0.1:8000','gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us'],'regenerate-tunnel')
        metrics=wait_url('http://127.0.0.1:18124/metrics',tunnel).decode()
        (target/'queue-before.txt').write_text('\n'.join(x for x in metrics.splitlines() if x.startswith('vllm:num_requests_'))+'\n')
        stack=['prototypes/streaming-diarization/draft-lane/run_local_stack.py','--cert','.wp24/cert.pem','--key','.wp24/key.pem','--vllm-base-url','http://127.0.0.1:18124/v1']
        private=start([PY,*stack,'--state','.wp24/regen-state','--port','17884','--max-requests',str(150-used)],'regenerate-private')
        shared=start([PY,*stack,'--state','.wp24/regen-shared','--port','17885','--max-requests','0'],'regenerate-shared',MOSS_OPEN_WORKSPACE='1')
        reference=start([PY,'tools/uifidelity/reference_oracle.py','--port','17886'],'regenerate-reference')
        wait_url('https://127.0.0.1:17884/',private);wait_url('https://127.0.0.1:17885/',shared);wait_url('http://127.0.0.1:17886/',reference)
        for script in ('browser_acquire.py','live_browser.py','extra.py','run.py'):
            subprocess.run([PY,str(HERE/script)],cwd=ROOT,env=env,check=True)
    finally:
        for proc in reversed(processes):
            proc.terminate()
            try:proc.wait(timeout=12)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        for log in logs:log.close()
        count=len((state/'requests.jsonl').read_text().splitlines()) if (state/'requests.jsonl').exists() else 0
        budget.write_text(json.dumps({'requests':used+count})+'\n')
        (target/'request-count.json').write_text(json.dumps({'this_regeneration':count,'wp24_cumulative':used+count,'limit':150,'max_inflight':2})+'\n')
if __name__=='__main__':main()
