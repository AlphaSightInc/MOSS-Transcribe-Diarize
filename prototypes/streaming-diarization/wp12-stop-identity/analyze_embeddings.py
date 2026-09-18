"""Content-free matched Stop/embedding accounting from the standing bench trace."""
import json
from collections import defaultdict
from pathlib import Path

OUT = Path('evidence/mvpfix/wp12')
trace = [json.loads(line) for line in (OUT / 'trace.jsonl').read_text().splitlines()]

def union(intervals):
    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged

def overlap(intervals, reference):
    return sum(max(0, min(b, d) - max(a, c)) for a, b in intervals for c, d in union(reference)) / 16000

reports = []
for path in sorted(OUT.glob('*traced-parity-*.json')):
    run = json.loads(path.read_text())
    rows = [x for x in trace if x['arm'] == run['arm'] and run['start'] <= x['time'] <= run['stop'] + run['stop_to_final']]
    owners = {p: lane for x in rows for lane, p in x.get('owners', {}).items()}
    readers = {}
    groups = defaultdict(list)
    intervals = defaultdict(list)
    for x in rows:
        if x['kind'] == 'revision_reader':
            readers[x['provider']] = x['owner']
        if x['kind'] != 'embedding':
            continue
        lane = owners.get(readers.get(x.get('provider'), x.get('provider')), 'mono')
        phase = x['reason']
        groups[(phase, lane)].append(x)
        intervals[(phase, lane)].extend((round(a * 16000) + x['offset'], round(b * 16000) + x['offset']) for a, b in x['intervals'])
    events = {x['event']: x for x in rows if x['kind'] == 'event' and x['time'] >= run['stop']}
    terminal_start = events['terminal_finalization_started']['time']
    preparation = []
    for (phase, lane), calls in sorted(groups.items()):
        row = dict(phase=phase, lane=lane, embedding_calls=len(calls), encoder_intervals=sum(len(x['intervals']) for x in calls), audio_seconds=sum(x['audio_seconds'] for x in calls), elapsed_seconds=sum(x['seconds'] for x in calls))
        if phase == 'terminal':
            prior = [i for (p, l), values in intervals.items() if p != 'terminal' and l == lane for i in values]
            causal = [i for (p, l), values in intervals.items() if p not in ('terminal', 'rolling_window') and l == lane for i in values]
            terminal = intervals[(phase, lane)]
            def call_intervals(call):
                return tuple((round(a*16000)+call['offset'], round(b*16000)+call['offset']) for a,b in call['intervals'])
            prior_calls = [call_intervals(call) for (p,l), values in groups.items() if p!='terminal' and l==lane for call in values]
            row.update(exact_prior_embedding_calls=sum(call_intervals(call) in prior_calls for call in calls), exact_prior_intervals=sum(i in prior for i in terminal), exact_causal_intervals=sum(i in causal for i in terminal), prior_audio_overlap_seconds=overlap(terminal, prior), causal_audio_overlap_seconds=overlap(terminal, causal))
        preparation.append(row)
    before_terminal = [dict(phase=x['phase'], start_after_stop=x['start']-run['stop'], end_after_stop=x['time']-run['stop'], elapsed_seconds=x['seconds']) for x in rows if x['kind']=='phase_end' and x['time']>=run['stop'] and x['start']<=terminal_start]
    reports.append(dict(file=path.name, stop_to_final=run['stop_to_final'], requests=run['requests'], saved_equal=run['saved_equal'], stop_to_terminal=terminal_start-run['stop'], terminal_to_publication=events['terminal_finalization_completed']['time']-terminal_start, stop_queues=events['stop_requested']['queues'], drain_jobs=before_terminal, embedding=preparation))
print(json.dumps(reports, indent=2))
