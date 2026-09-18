"""Retained 180 s Stop decomposition. No decoder calls; no invented timing precision."""
import json
from pathlib import Path

out = Path('evidence/mvpfix/wp12')
trace = [json.loads(line) for line in (out/'trace.jsonl').read_text().splitlines()]
reports = []
for arm in ('overlap-fixed', 'mono180-traced'):
    run = json.loads((out/f'{arm}-parity-180.json').read_text())
    rows = [x for x in trace if x['arm'] == arm and run['stop'] <= x['time'] <= run['stop']+run['stop_to_final']]
    events = {x['event']: x for x in rows if x['kind'] == 'event'}
    start = events['terminal_finalization_started']['time']
    published = events['terminal_finalization_completed']['time']
    terminals = [x for x in rows if x['kind'] == 'terminal_end']
    jobs = []
    for job in terminals:
        accounting = job['accounting']
        # Existing lane trace omits thread; retained final surface segment counts
        # identify the 56-row system and 30-row mic results unambiguously.
        lane = {56: 'system', 30: 'microphone'}[accounting['segments']] if arm == 'overlap-fixed' else 'mono'
        jobs.append(dict(lane=lane, windows=accounting['window_count'],
            decoded_audio_seconds=accounting['decoded_audio_samples']/16000,
            terminal_wall_seconds=job['seconds'], decode_stage_seconds=accounting['decode_elapsed_sec'],
            mapping_and_other_non_decode_upper_bound_seconds=job['seconds']-accounting['decode_elapsed_sec']))
    mapping = [x for x in rows if x['kind'] == 'terminal_mapping' and x['time'] >= start]
    publication = [x for x in rows if x['kind'] == 'publication_end']
    embeddings = [x for x in rows if x['kind'] == 'embedding' and x['time'] >= start]
    drain = next(x for x in rows if x['kind'] == 'drain_end')
    phases = [dict(phase=x['phase'], seconds=x['seconds'], start_after_stop=x['start']-run['stop'])
              for x in rows if x['kind'] == 'phase_end' and x['time'] < start]
    reports.append(dict(arm=arm, stop_to_final=run['stop_to_final'], requests=run['requests'], saved_equal=run['saved_equal'],
        stop_to_terminal_seconds=start-run['stop'], drain_wait_seconds=drain['seconds'], drain_phases=phases,
        terminal_to_publication_seconds=published-start, jobs=jobs,
        mapping_seconds=[x['seconds'] for x in mapping] if mapping else None,
        publication_seconds=[x['seconds'] for x in publication] if publication else None,
        last_terminal_return_to_publication_event_seconds=published-max(x['time'] for x in terminals),
        publication_event_to_client_final_seconds=run['stop']+run['stop_to_final']-published,
        terminal_embedding_calls=len(embeddings), terminal_embedding_audio_seconds=sum(x['audio_seconds'] for x in embeddings),
        critical_decode_fraction_of_stop_to_final=max(x['decode_stage_seconds'] for x in jobs)/run['stop_to_final']))

print(json.dumps(dict(reports=reports,
    limitations='Single observations, shared GPU; mono mixes the same two inputs. Old candidate trace did not isolate mapping/publication calls: report non-decode upper bounds and final-return-to-publication interval, not exact mapping or persistence timing. New mono trace measures mapping and publication method wall time. Decode stage includes WAV/window handling. Publication event precedes client observation; that residual is not attributed solely to persistence.'), indent=2))
