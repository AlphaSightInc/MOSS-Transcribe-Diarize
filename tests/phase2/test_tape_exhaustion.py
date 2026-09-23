"""Exhaustion through real HTTP Stop, durable transcript, MP3 and lease cleanup."""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / 'prototypes/streaming-diarization/tape-exhaustion/probe.py'
_SPEC = importlib.util.spec_from_file_location('wp29_probe', _PATH)
probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe)


@pytest.mark.parametrize('case', probe.CASES)
def test_exhaustion_finishes_truthfully(tmp_path, case):
    # Portable regression input; the standalone measurement uses real public speech.
    output = probe.exercise(tmp_path, case, emit=lambda _: None,
                            clips=[b'\x01\x00'*16000, b'\x02\x00'*16000])
    for r in output['results']:
        interrupted = case == 'lease_expiry'
        assert r['saved_status'] == ('interrupted' if interrupted else 'completed')
        assert r['reopened_status'] == r['saved_status']
        assert r['reopened_segments'] == r['saved_segments'] > 0
        assert r['saved_equal'] and r['prefix_preserved'] and r['reopened_document_equal']
        assert r['reopened_notice'] == r['notice']
        assert r['audio']['state'] == 'partial'
        assert r['audio']['duration_ms'] == round(float(r['mp3']['format']['duration']) * 1000)
        assert r['decoded_samples'] == 60 * 16000
        assert not r['state']['lease_armed']
        assert r['state']['queue'] == 0
        assert all(t['released'] and t['retained_bytes'] == 0 for t in r['state']['tapes'].values())
        if interrupted:
            assert r['finalization'] == 'not_started'
            continue
        assert r['terminal_failure'] is None
        assert r['state']['accepted'] == r['state']['accounted'] == 90*16000
        expected = 'final' if case.endswith('_only') else 'unavailable'
        assert r['finalization'] == expected
        payload = r['events'][-1]['payload']
        assert payload['tape_gaps'] == (0 if case == 'mixed_only' else 1 if case.endswith('_only') else 2)
        assert {'outcome', 'tape_samples', 'reason', 'applied', 'finalization_status'} <= payload.keys()
        if case != 'mixed_only':
            assert r['notice'] == ('Final transcript refinement was unavailable for some audio. '
                                   'Previously committed words were kept.')
