import importlib.util
import json
import shutil
from pathlib import Path
import pytest


RUN_PATH = Path(__file__).resolve().parents[2] / 'prototypes/browser-stress/run.py'


def load_browser_stress():
    spec = importlib.util.spec_from_file_location('browser_stress_run', RUN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_case_10_artifacts_survive_private_cleanup_without_auth_state(tmp_path):
    run = load_browser_stress()
    private = tmp_path / 'private'
    private.mkdir()
    meeting = {
        'id': 'public-corpus-meeting',
        'needs_review': True,
        'transcript': {'segments': [
            {'id': 'seg_0001', 'start': 0.0, 'end': 1.0, 'speaker': 'Speaker 1',
             'speaker_entity_id': 'speaker-0001', 'text': 'Public test words.'},
        ]},
    }
    payloads = {fmt: f'{fmt} public export\n'.encode() for fmt in ('md', 'txt', 'json', 'srt', 'vtt')}
    exports = {}
    for fmt, payload in payloads.items():
        path = private / f'live.{fmt}'
        path.write_bytes(payload)
        exports[fmt] = path
    (private / 'cookies.json').write_text('never retain me')

    for mode in ('live', 'file'):
        run.retain_case_10_artifacts(tmp_path / 'output', mode, meeting, exports)
    with pytest.raises(ValueError, match='exactly five transcript exports'):
        run.retain_case_10_artifacts(
            tmp_path / 'output', 'live', meeting, {**exports, 'cookies': private / 'cookies.json'})
    shutil.rmtree(private)

    for mode in ('live', 'file'):
        retained = tmp_path / f'output/case-10-artifacts/{mode}'
        assert (retained / 'meeting.json').read_bytes() == (json.dumps(meeting, indent=2) + '\n').encode()
        assert {path.name for path in retained.iterdir()} == {
            'meeting.json', 'transcript.md', 'transcript.txt', 'transcript.json',
            'transcript.srt', 'transcript.vtt',
        }
        for fmt, payload in payloads.items():
            assert (retained / f'transcript.{fmt}').read_bytes() == payload
