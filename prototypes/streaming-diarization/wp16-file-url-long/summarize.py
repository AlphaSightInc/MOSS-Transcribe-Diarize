"""Compact content-free report from browser, window and resource measurements."""
import json,subprocess
from pathlib import Path
root=Path('evidence/mvpfix/wp16')
read=lambda name:json.loads((root/name).read_text())
windows=[json.loads(line) for line in (root/'windows.jsonl').read_text().splitlines()]
resources=[json.loads(line) for line in (root/'resources.jsonl').read_text().splitlines()]
rows=[]
for name in ['long.wav','long.mp3','long.m4a','concurrent-a','concurrent-b','direct','youtube','commons','missing','html','hang','empty.wav','text.mp3','truncated.mp3','silence.wav','two.wav']:
 row=read(name+'.json'); a=row.get('audio') or {}; started=row['started_monotonic']; ended=started+row['elapsed_seconds']
 sampled=[r['rss_kib'] for r in resources if started<=r['monotonic']<=ended]
 decoded=[w for w in windows if started<=w['started']<ended]
 # Concurrent windows overlap both observation intervals: retain denominator honestly.
 row.update(saved_audio_seconds=a.get('duration_ms',0)/1000,throughput_x=(1800/row['elapsed_seconds']) if name.startswith(('long.','concurrent')) else None,rss_samples=len(sampled),sampled_rss_max_kib=max(sampled,default=None),windows_in_observation_interval=len(decoded),concurrent_window_count_shared=name.startswith('concurrent'))
 rechecks=read('surface-recheck.json')
 match=next((s for s in rechecks if s['case']==name and s.get('meeting_id')==row['meeting_id']),None)
 if match:
  row.update({k:match[k] for k in ['history_reason','header_reason','foreign_read_status']}); row['surface_rechecked']=True
 row.pop('audio',None);rows.append(row)
summary=dict(cases=rows,requests=len(Path('.wp16runtime/state/requests.jsonl').read_text().splitlines()),request_budget=200,window_records=len(windows),resource_samples=len(resources),rss_kib_min=min(r['rss_kib'] for r in resources),rss_kib_max=max(r['rss_kib'] for r in resources),max_shared_running=max(float(q.rsplit(' ',1)[1]) for r in resources for q in r['queue'] if 'num_requests_running{' in q),max_shared_waiting=max(float(q.rsplit(' ',1)[1]) for r in resources for q in r['queue'] if 'num_requests_waiting{' in q),exports_passed=sum(v['ok'] for r in rows for v in r['exports'].values()),exports_total=sum(len(r['exports']) for r in rows),oversize=read('oversize.json'))
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='cases'},indent=2))
