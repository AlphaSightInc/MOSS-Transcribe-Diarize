"""THROWAWAY falsifier: can missing/unknown/merged speakers look perfect?

Run: PYTHONPATH=. .venv/bin/python prototypes/streaming-diarization/round2-measurement/probe.py
No decoder calls, production scorer and qualification interface, full score state.
"""
import json
from tools.qualify.speaker_quality import score_speakers

reference = [dict(start=0, end=2, speaker='Alice'), dict(start=2, end=4, speaker='Bob')]
cases = {
    'exact': (reference, 0),
    'missing_Bob': (reference[:1], .5),
    'merged_people': ([dict(start=0, end=4, speaker='one')], .5),
    'all_unknown': ([dict(start=0, end=4, speaker='S00')], 1),
}
for name, (observed, expected_error) in cases.items():
    result = score_speakers(reference, observed)
    print(json.dumps(dict(case=name, **result)))
    assert result['diarization_error_rate'] == expected_error
    assert (result['participant_presence_witness'] == 'PASS') == (name == 'exact')
