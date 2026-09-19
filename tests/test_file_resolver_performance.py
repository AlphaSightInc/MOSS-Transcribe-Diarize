"""WP28: execution scheduling must preserve the complete identity result."""
from dataclasses import asdict
import json
import os
from pathlib import Path
from threading import Event, Lock, enumerate as threads
from types import SimpleNamespace

import numpy as np
import pytest

from moss_transcribe_diarize.app import speaker_identity as si
from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
from moss_transcribe_diarize.app.live_identity_album import ALBUM_MIN_MATCH_SCORE, ALBUM_MIN_MATCH_MARGIN
from moss_transcribe_diarize.app.windowed_transcription import WindowPlan, plan_windows
from moss_transcribe_diarize.transcript_parser import TranscriptSegment

FIXTURES = Path(__file__).resolve().parents[1] / 'evidence/mvpfix/wp28'


def fake_encoder(workers, *, fail=False, session=None):
    samples = np.zeros(16000 * 120, dtype='float32')
    samples[40 * 16000:50 * 16000] = 1

    class Session:
        def run(self, outputs, inputs):
            voice = int(inputs['feats'][0, 0, 0])
            if fail and voice:
                raise RuntimeError('probe failed')
            vector = np.zeros((1, 256), dtype='float32')
            vector[0, voice] = 1
            return [vector]

    encoder = si._OnnxWeSpeakerEmbedder(
        Path('unused'), device='cpu', interval_workers=workers,
        audio_loader=lambda path: (samples, 16000),
        fbank=lambda clip: np.full((1, 80), clip[0], dtype='float32'),
    )
    encoder._session = session or Session()
    encoder.descriptor = {'provider': 'perfect-vector'}
    return encoder


def config():
    return SimpleNamespace(
        identity_config=dict(max_speakers=16, min_match_score=ALBUM_MIN_MATCH_SCORE,
                             min_match_margin=ALBUM_MIN_MATCH_MARGIN),
        identity_provider=dict(min_segment_samples=8000),
    )


@pytest.mark.parametrize('count', [3, 15])
@pytest.mark.parametrize('voices', [1, 2])
def test_perfect_vectors_keep_exact_album_output_with_parallel_intervals(count, voices):
    groups = [[TranscriptSegment(start, start + 2, f'S{voice + 1:02d}', 'placeholder')
               for voice in range(voices) for start in (20 + 20 * voice, 23 + 20 * voice)]
              for _ in range(count)]
    windows = plan_windows(count * 120, window_seconds=150, stride_seconds=120)
    outputs = [AlbumIdentityResolver(config=config(), encoder=fake_encoder(workers)).resolve(
        windows, groups, window_audio_paths=['unused'] * count) for workers in (1, 4)]
    assert outputs[0] == outputs[1]
    assert outputs[1].summary['canonical_speakers'] == voices


def test_parallel_probe_failure_preserves_window_abstention_and_closes_workers():
    groups = [[TranscriptSegment(20, 22, 'S01', 'a'),
               TranscriptSegment(40, 42, 'S01', 'b')]]
    windows = plan_windows(120)
    outputs = [AlbumIdentityResolver(config=config(), encoder=fake_encoder(workers, fail=True)).resolve(
        windows, groups, window_audio_paths=['unused']) for workers in (1, 4)]
    assert outputs[0] == outputs[1]
    assert outputs[1].diagnostics['windows'][0]['reason'] == 'evidence_provider_failed:RuntimeError'
    assert [s.speaker for s in outputs[1].relabeled_results[0]] == ['S00', 'S00']
    assert not [t for t in threads() if t.name.startswith('moss-file-embedding')]


def test_interval_vectors_are_exposed_before_the_local_label_mean():
    encoder = fake_encoder(1)
    vectors = encoder.embed_intervals('unused', [(0, 2), (40, 42)])
    assert vectors[0][0] == 1 and vectors[0][1] == 0
    assert vectors[1][0] == 0 and vectors[1][1] == 1
    assert encoder.embed('unused', [(0, 2), (40, 42)]) == si._mean_unit_vector(vectors)


def test_parallel_probes_are_bounded_and_reduce_in_input_order(monkeypatch):
    lock = Lock()
    all_started = Event()
    completed = []
    release = [Event() for _ in range(4)]
    active = 0
    peak = 0
    originals = [[float(i), 1., 0.] for i in range(4)]

    def run(session, features):
        nonlocal active, peak
        index = int(features[0, 0, 0])
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 4:
                all_started.set()
                release[3].set()
        assert all_started.wait(5), 'four independent probes did not start'
        assert release[index].wait(5)
        with lock:
            completed.append(index)
            active -= 1
            if index:
                release[index - 1].set()
        return originals[index]

    encoder = fake_encoder(4)
    samples = np.repeat(np.arange(4, dtype='float32'), 16000)
    encoder._audio_loader = lambda path: (samples, 16000)
    monkeypatch.setattr(si, '_run_onnx_embedding', run)
    reduced = []
    original_mean = si._mean_unit_vector
    monkeypatch.setattr(si, '_mean_unit_vector', lambda vectors: (reduced.extend(vectors), original_mean(vectors))[1])
    result = encoder.embed('unused', [(i, i + 1) for i in range(4)])
    expected = [si._normalized_vector(v) for v in originals]
    assert peak == 4 and completed == [3, 2, 1, 0]
    assert reduced == expected
    assert result == original_mean(expected)
    assert not [t for t in threads() if t.name.startswith('moss-file-embedding')]


@pytest.mark.parametrize('workers', [1, 4])
def test_parallel_intervals_keep_empty_and_clipped_interval_semantics(workers):
    encoder = fake_encoder(workers)
    assert encoder.embed('unused', [(-1, 2), (2, 2), (130, 132)]) == encoder.embed('unused', [(0, 2)])
    with pytest.raises(ValueError, match='intervals are empty'):
        encoder.embed('unused', [(2, 2), (130, 132)])


@pytest.mark.parametrize('minutes', [6, 30])
def test_retained_real_fixture_is_byte_identical_to_pre_wp28_oracle(minutes):
    root = os.environ.get('WP28_REAL_FIXTURES')
    if root is None:
        pytest.skip('set WP28_REAL_FIXTURES to retained real-{6,30} WAV directories')
    fixture = json.loads((FIXTURES / f'fixture-{minutes}.json').read_text())
    windows = [WindowPlan(**row) for row in fixture['windows']]
    groups = [[TranscriptSegment(**row) for row in group] for group in fixture['local_results']]
    paths = [Path(root) / f'real-{minutes}' / f'window-{w.index}.wav' for w in windows]
    assert all(p.is_file() for p in paths), 'explicit real-fixture request must not skip missing WAVs'
    resolver = AlbumIdentityResolver()
    result = resolver.resolve(windows, groups, window_audio_paths=paths)
    from moss_transcribe_diarize.app.live_provider_bundle import _identity_encoder
    assert resolver._encoder._get_embedder()._interval_workers == 4
    assert _identity_encoder(resolver._config)._interval_workers == 1
    assert json.dumps(asdict(result), sort_keys=True) == json.dumps(fixture['expected'], sort_keys=True)
