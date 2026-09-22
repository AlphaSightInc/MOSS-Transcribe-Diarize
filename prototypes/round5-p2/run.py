"""THROWAWAY: run the P2 row-10 receipt controls with no decoder request."""
import copy
import json
from pathlib import Path

from tests.e2e.verify_workspace import project_row10_timing, retained_metadata


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT/'docs/audits/row10-recognition-events-20260912.json'
TIMING = {'started': 0.0, 'matched': 10844.687167, 'meeting_id': 'row10-audit'}


def print_state(name, value):
    print(f'STATE {name}')
    print(json.dumps(value, indent=2, sort_keys=True))


def main():
    events = json.loads(AUDIT.read_text())
    retained = retained_metadata({'events': events})
    loss = {
        'input_events': len(events),
        'retained_events': len(retained['events']),
        'retained_kinds_null': sum(event['kind'] is None for event in retained['events']),
        'retained_payload_keys': sorted({key for event in retained['events'] for key in event if key == 'payload'}),
    }
    assert loss == {'input_events': 78, 'retained_events': 78, 'retained_kinds_null': 78, 'retained_payload_keys': []}
    print_state('SANITIZER_LOSS', loss)

    positive = project_row10_timing(events, TIMING)
    assert positive['decode']['queue_wait_seconds'] == 0.000173667
    assert positive['decode']['processing_elapsed_seconds'] == 7.438577042
    assert positive['decode']['decode_elapsed_seconds'] == 7.068335624877363
    print_state('POSITIVE_HISTORICAL', positive)

    injected = copy.deepcopy(events)
    for event in injected:
        event['payload'].update({'transcript': 'NEVER_RETAIN_TRANSCRIPT', 'name': 'NEVER_RETAIN_NAME',
                                 'headers': 'NEVER_RETAIN_HEADERS', 'body': 'NEVER_RETAIN_BODY'})
    violating = project_row10_timing(injected, TIMING)
    assert 'NEVER_RETAIN' not in json.dumps(violating)
    print_state('VIOLATING_CONTENT', violating)

    missing = project_row10_timing([event for event in events if event['kind'] != 'canonical_queued'], TIMING)
    assert missing['canonical_queue']['seq'] is None
    assert missing['attribution'] == 'INCOMPLETE'
    print_state('MISSING_STAGE', missing)


if __name__ == '__main__':
    main()
