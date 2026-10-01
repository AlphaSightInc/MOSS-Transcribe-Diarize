"""Terminal/engine regression tests for committed-word custody and microphone H."""
import asyncio

import pytest

from moss_transcribe_diarize.app.gemini_hybrid_engine import GeminiHybridEngine, FixedWindowScheduler, OverlapRegistry
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords, TerminalTranscriber
from test_gemini_lane_engine import _local_fixture, _local_gate, _local_phrase

S = 16000


def w(text, a, b, label='live'):
    return GeminiWord(text, label, round(a*S), round(b*S))


class Tape:
    sample_count = 12*S

    def read(self, *, start_sample=0, end_sample=None):
        return bytes(2*((self.sample_count if end_sample is None else end_sample)-start_sample))


class Diarizer:
    def diarize(self, pcm, **kwargs):
        return GeminiWords((w('before', 1, 1.2, 'A'), w('after', 2, 2.2, 'B')))


def test_terminal_restores_witnessed_words_after_labels_and_before_gates():
    import wave
    from pathlib import Path
    from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate
    with wave.open(str(Path(__file__).parents[1] / 'fixtures/idea_020_provider_smoke.wav'), 'rb') as wav:
        voice = wav.readframes(S)
    pcm = bytearray(24*S)
    pcm[S:3*S] = voice
    pcm[3*S:5*S] = voice
    class VoiceTape(Tape):
        def read(self, *, start_sample=0, end_sample=None):
            return bytes(pcm[2*start_sample:2*(self.sample_count if end_sample is None else end_sample)])
    seen, usage = [], []
    class Identity:
        def remap(self, words, pcm):
            return tuple(w(x.text, x.start_sample/S, x.end_sample/S, 'final-'+x.speaker) for x in words)
    class Gate:
        def filter(self, pcm, words):
            seen.extend(words)
            return WebRtcWordGate().filter(pcm, words)
    terminal = TerminalTranscriber(Diarizer(), identity_policy=Identity(), word_gate=Gate(),
                                   report_usage=lambda **row: usage.append(row))
    baseline = terminal.transcribe(VoiceTape())
    terminal.set_witness_words((w('Media', 1.2, 1.4), w('Lab', 1.4, 1.6),
                                w('unvoiced', 5, 5.3)))
    rows = terminal.transcribe(VoiceTape())
    assert 'Media Lab' in ' '.join(r.text for r in rows)
    assert 'unvoiced' not in ' '.join(r.text for r in rows)
    assert [x.speaker for x in seen if x.text == 'Media'] == [baseline[0].speaker]
    assert sum(r.get('witness_restored_words', 0) for r in usage) == 3


def test_chunked_terminal_restores_after_stitching():
    class Stitcher:
        def stitch(self, chunks, pcm):
            return (w('before', 1, 1.2, 'stitched-a'), w('after', 2, 2.2, 'stitched-b'))
    terminal = TerminalTranscriber(Diarizer(), chunk_seconds=8, overlap_seconds=1,
                                   stitcher=Stitcher())
    terminal.set_witness_words((w('Media', 1.2, 1.4), w('Lab', 1.4, 1.6)))
    terminal.transcribe(Tape())
    assert [(x.text, x.speaker) for x in terminal.last_words] == [
        ('before', 'stitched-a'), ('Media', 'stitched-a'), ('Lab', 'stitched-a'), ('after', 'stitched-b')]


@pytest.mark.parametrize('start', [0, 3])
def test_transcribe_interval_ignores_witness_words(start):
    terminal = TerminalTranscriber(Diarizer())
    terminal.set_witness_words((w('Media', start+1.2, start+1.4), w('Lab', start+1.4, start+1.6)))
    rows = terminal.transcribe_interval(Tape(), start*S, (start+6)*S)
    assert 'Media' not in ' '.join(r.text for r in rows)
    assert [(x.start_sample, x.end_sample) for x in terminal.last_words] == [
        ((start+1)*S, round((start+1.2)*S)), ((start+2)*S, round((start+2.2)*S))]


def test_engine_hands_committed_words_to_terminal():
    captured = []
    class Terminal:
        def set_witness_words(self, words): captured.extend(words)
        def transcribe(self, tape): return ()
    engine = GeminiHybridEngine(lambda update: None, word_source=object(),
        window_scheduler=FixedWindowScheduler(), registry=OverlapRegistry(),
        diarizer=Diarizer(), terminal=Terminal())
    engine._publish_window(0, 15*S, bytes(30*S), (w('Computer', 14.4, 14.8),))
    engine._publish_window(0, 30*S, bytes(60*S), (w('Computerphile', 14.4, 15.1),))
    engine._publish_window(0, 35*S, bytes(70*S), (w('recovery', 32, 33),), gate_words=False)
    asyncio.run(engine.finish(Tape()))
    assert [(x.text, x.start_sample, x.end_sample) for x in captured] == [('Computerphile', round(14.4*S), round(15.1*S))]


def test_saved_transcript_keeps_live_name_the_cleanup_answer_omits():
    usage = []
    terminal = TerminalTranscriber(Diarizer(), report_usage=lambda **row: usage.append(row))
    engine = GeminiHybridEngine(lambda update: None, word_source=object(),
        window_scheduler=FixedWindowScheduler(), registry=OverlapRegistry(),
        diarizer=Diarizer(), terminal=terminal)
    engine._publish_window(0, 12*S, bytes(24*S),
                           (w('Media', 1.2, 1.4), w('Lab', 1.4, 1.6), w('的', 1.6, 1.8)))
    rows = asyncio.run(engine.finish(Tape()))
    assert ' '.join(r.text for r in rows).count('Media Lab的') == 1
    assert all(a.end_sample <= b.start_sample for a, b in zip(rows, rows[1:]))
    assert sum(r.get('witness_restored_words', 0) for r in usage) == 3


@pytest.mark.parametrize('echo', [10, 56])
@pytest.mark.parametrize('count', [1, 2, 3, 4, 5, 6])
@pytest.mark.parametrize('anchored', [False, True])
def test_microphone_candidate_is_judged_alone_before_neighbour_label(echo, count, anchored):
    mic, system = _local_fixture(echo=echo)
    gate = _local_gate(system, [])
    gate.local_speech_seen = anchored
    words = _local_phrase(' '.join(['reply']*count))
    cleanup = _local_phrase(' '.join(['remote']*25), 3, 7, 'echo') + _local_phrase('tail', 9.8, 10, 'echo')
    # The original merged rule fails the evidence denominator; an isolated run succeeds.
    assert not gate.local_voice.is_local_run(mic, cleanup+words, whole_lane=True)
    kept = (w('neighbour', 9.8, 10, 'local-final'),)
    output, restored = gate.restore_witnessed_words(mic, cleanup, kept, words, (),
        system_pcm16=system, local_speaker='local-fallback')
    assert len(restored) == (1 if count >= 3 else 0)
    assert len(output) == len(kept)+(count if count >= 3 else 0)
    assert all(x.speaker == 'local-final' for x in output)


@pytest.mark.parametrize('anchored', [False, True])
@pytest.mark.parametrize('text,start,end', [('是。 哦。 六。', 20, 22.3),
    ('Think about this', 8, 8.2), ('Could you say that again', 20, 21)])
def test_microphone_invented_and_noise_witnesses_are_not_restored(anchored, text, start, end):
    mic, system = _local_fixture(((8, 8.2), (10, 13)))
    gate = _local_gate(system, [])
    gate.local_speech_seen = anchored
    real = _local_phrase(' '.join(['real']*24), 10, 13)
    output, restored = gate.restore_witnessed_words(mic, real, real,
        _local_phrase(text, start, end), (), system_pcm16=system)
    assert output == real and restored == []


def test_microphone_gated_removal_does_not_create_provider_hole():
    mic, system = _local_fixture()
    gate = _local_gate(system, [])
    witness = _local_phrase()
    output, restored = gate.restore_witnessed_words(mic, witness, (), witness, (), system_pcm16=system)
    assert output == () and restored == []


def test_microphone_without_kept_neighbour_uses_local_label():
    mic, system = _local_fixture()
    gate = _local_gate(system, [])
    output, restored = gate.restore_witnessed_words(mic, (), (), _local_phrase(), (),
        system_pcm16=system, local_speaker='local-0001')
    assert len(output) == 5 and len(restored) == 1
    assert {x.speaker for x in output} == {'local-0001'}


def test_microphone_restored_words_pass_the_terminal_gates():
    mic, system = _local_fixture()
    gate = _local_gate(system, [], _local_phrase('Can you', 8.4, 8.7, 'tab'))
    output, restored = gate.restore_witnessed_words(mic, (), (), _local_phrase(),
        gate.system_words.words_through(30*S), system_pcm16=system)
    assert [x.text for x in output] == ['elaborate', 'on', 'that?']
    assert len(restored) == 1
