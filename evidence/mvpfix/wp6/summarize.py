"""Offline reduction of retained WP6 measurements; no network or decoder calls."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def p95(values):
    if not values:
        return None
    values = sorted(values)
    index = (len(values)-1)*.95
    low = int(index)
    high = min(low+1, len(values)-1)
    return values[low]+(values[high]-values[low])*(index-low)


runs = []
for path in sorted(ROOT.glob('*x*/result.json')):
    result = json.loads(path.read_text())
    actions = [json.loads(line) for line in path.with_name('actions.jsonl').read_text().splitlines()]
    decoder = [json.loads(line) for line in path.with_name('decoder.jsonl').read_text().splitlines()]
    resources = result['resources']
    pauses, opened = [], None
    for row in actions:
        if row['kind'] == 'pause':
            opened = row['time']
        elif row['kind'] == 'resume' and opened is not None:
            pauses.append(row['time']-opened)
            opened = None
    runs.append(dict(
        run=path.parent.name, sessions=result['sessions'], seconds=result['seconds'],
        clean=result['clean'], failures=result['failures'],
        harness_interrupted=path.with_name('INTERRUPTION.md').exists(),
        decoder_calls=sum(row['kind']=='start' for row in decoder),
        decoder_completed=sum(row['kind']=='finish' for row in decoder),
        maximum_own_inflight=max((row['active'] for row in decoder), default=0),
        pause_seconds=pauses, unresolved_pause=opened is not None,
        foreign_samples=sum(row['foreign_load_detected'] for row in resources),
        resource_samples=len(resources),
        rss_start_bytes=resources[0]['app_rss_bytes'] if resources else None,
        rss_peak_bytes=max((row['app_rss_bytes'] for row in resources), default=None),
        shared_queue_peak=max((row['metrics']['num_requests_waiting'] for row in resources), default=None),
        gpu_memory_mib=sorted({row['gpu_memory_mib'] for row in resources if row['gpu_memory_mib']}),
        refinement_queue_peak=result.get('maximum_refinement_queue_depth'),
        inference_rtf=result.get('prestop_inference',{}).get('rtf'),
        fairness=result.get('fairness'),
        per_session=[dict(
            **{k:v for k,v in row.items() if k not in ('events','updates','coverage_lags','canonical_lags')},
            updates=len(row['updates']),
            p95_visible_update_age_seconds=p95([x['newest_audio_age_seconds'] for x in row['updates'] if x['words']]),
            canonical_events=len(row.get('canonical_lags',[])),
        ) for row in sorted(result['session_results'],key=lambda x:x['ordinal'])],
    ))
print(json.dumps(dict(runs=runs,total_decoder_calls=sum(row['decoder_calls'] for row in runs)),indent=2))
