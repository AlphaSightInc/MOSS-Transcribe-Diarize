import json
from collections import Counter

def project(trace_path, captures):
    events=[r['event'] for r in map(json.loads,trace_path.read_text().splitlines()) if r['kind']=='service_event']
    seq=[e['seq'] for e in events]
    gaps=[(a,b) for a,b in zip(seq,seq[1:]) if b!=a+1]
    rolling=[e for e in events if e['kind']=='rolling_decode_completed']
    revisions=[e for e in events if e['kind']=='text_revision_applied' and e['payload'].get('source')=='rolling']
    refused=[e for e in events if e['kind']=='text_revision_refused' and e['payload'].get('source')=='rolling']
    def at_capture(cap):
        snap=cap['snapshot'];s=snap['session'];version=s['version'];text_version=s['text_revision_version']
        applied=[e for e in revisions if e['snapshot_version']<=version and e['payload']['text_revision_version']<=text_version]
        return {'rolling_revisions_applied':len(applied),
            'rolling_window_indices_applied':[e['payload'].get('window_index') for e in applied],
            'text_revision_version':text_version,'snapshot_version':version,
            'canonical_committed_samples':s['committed_samples'],
            'accepted_samples':s['accepted_samples'],
            'finalization_status':s['finalization_status']}
    keys=['item_id','window_index','start_sample','end_sample','owned_start_sample','owned_end_sample',
          'outcome','decode_failure','proposed','applied','refusal','revised_segments','rolling_status',
          'rolling_decode_elapsed_sec','queue_wait_ms','runtime_monotonic_ns','windows_completed',
          'windows_failed','proposal_refusals','admission_refusals','last_proposal_refusal',
          'decoded_audio_samples','window_samples','owned_samples']
    return {'event_count':len(events),'first_event_seq':seq[0] if seq else None,'event_sequence_gaps':gaps,
        'rolling_completions':len(rolling),
        'rolling_windows_with_decode_measurement':sum(e['payload'].get('rolling_decode_elapsed_sec') is not None for e in rolling),
        'rolling_decode_failures':dict(Counter(e['payload'].get('decode_failure') for e in rolling if e['payload'].get('decode_failure'))),
        'rolling_completion_outcomes':dict(Counter(e['payload'].get('outcome') for e in rolling)),
        'rolling_revision_refusals':dict(Counter(e['payload'].get('refusal') for e in refused)),
        'captures':{name:at_capture(cap) for name,cap in captures.items()},
        'windows':[{k:e['payload'].get(k) for k in keys} for e in rolling]}
