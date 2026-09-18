"""Per-process current RSS and shared queue every 30 s; no historical-peak claim."""
import json,re,subprocess,time,urllib.request
from pathlib import Path
pid=re.search(r'Started server process \[(\d+)\]',Path('.wp16runtime/server.log').read_text())[1]
while True:
    result=subprocess.run(['ps','-o','rss=','-p',pid],capture_output=True,text=True)
    if not result.stdout.strip(): break
    metrics=urllib.request.urlopen('http://127.0.0.1:18116/metrics',timeout=10).read().decode()
    row=dict(monotonic=time.monotonic(),pid=int(pid),rss_kib=int(result.stdout),queue=[s for s in metrics.splitlines() if s.startswith(('vllm:num_requests_running{','vllm:num_requests_waiting{'))])
    with Path('evidence/mvpfix/wp16/resources.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
    time.sleep(30)
