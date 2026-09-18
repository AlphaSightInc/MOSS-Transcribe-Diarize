"""Summarize completed WP22 profiles; refuse missing checkpoints or changed content."""
import json
from pathlib import Path
root=Path('evidence/mvpfix/wp22')
summary={}; lines=['# WP22 measured owner bytes', '', 'Recursive Python ownership estimates; not additive physical RAM. Album count means speaker banks.', '']
for arm in ['mono-base','lanes-before','lanes-after']:
    rows=[json.loads(x) for x in (root/(arm+'.jsonl')).read_text().splitlines()]
    points=[next(r for r in rows if r['seconds']==second and r['phase']=='capture') for second in [300,900,1800]]
    final=next(r for r in rows if r['phase']=='after_terminal')
    assert final['accepted']==final['committed']==28_800_000
    assert all(v['count']==0 for k,v in final['structures'].items() if k.startswith(('tape_','pending_pcm_')))
    warm=next(r for r in rows if r['seconds']==30)
    summary[arm]=dict(rss_5_15_30=[r['rss_bytes'] for r in points],python_5_15_30=[r['python_bytes'] for r in points],rss_after=final['rss_bytes'],python_after=final['python_bytes'],rss_warm_30s=warm['rss_bytes'],status=final['status'],finalization=final['finalization'],wall_seconds=final['wall_seconds'],decoder_calls=final['decoder_calls'],sample_count=len(rows),rss_max_sampled=max(r['rss_bytes'] for r in rows))
    lines += [f'## {arm}', '', '| Owner | bytes at 5 min | 15 min | 30 min | post-Stop bytes / count |','|---|---:|---:|---:|---:|']
    for name in points[-1]['structures']:
        cells=[str(p['structures'][name]['bytes']) for p in points]
        last=final['structures'][name]
        lines.append('| '+name+' | '+' | '.join(cells)+f" | {last['bytes']} / {last['count']} |")
    lines+=['']
before=json.loads((root/'lanes-before.content.json').read_text());after=json.loads((root/'lanes-after.content.json').read_text())
assert before==after,'Per-lane transcript changed'
summary['content']=dict(exact_equal=True,segments=len(after),words=sum(len(s['text'].split()) for s in after))
publication=[json.loads(x) for x in (root/'publication.jsonl').read_text().splitlines()]
assert publication[-1]['terminal'] and publication[-1]['queue_count']==0
summary['publication']=dict(final=publication[-1],max_sampled_queue=max(r['max_queue_count'] for r in publication))
(root/'profile-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(root/'OWNERS.md').write_text('\n'.join(lines))
print(json.dumps(summary,indent=2))
