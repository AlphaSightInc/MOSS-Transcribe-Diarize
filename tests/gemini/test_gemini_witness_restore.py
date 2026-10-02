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


@pytest.mark.parametrize('next_label', ['window-A', 'window-B'])
def test_microphone_frontier_reply_restores_across_request_labels(next_label):
    mic, system = _local_fixture(((11.8, 15.8),))
    gate = _local_gate(system, [])
    anchor = _local_phrase(' '.join(['genuine']*26), 11.8, 14.4, 'window-A')
    reply = _local_phrase(start=14.6, end=15.6, label='window-A')
    class Cleanup:
        def diarize(self, *args, **kwargs): return GeminiWords(anchor)
    terminal = TerminalTranscriber(Cleanup(), source_lane='microphone', word_gate=gate.webrtc_gate,
        word_filter=lambda words: gate.filter_terminal(mic, words, (), system_pcm16=system),
        witness_filter=lambda cleanup, kept, witness, skip: gate.restore_witnessed_words(
            mic, cleanup, kept, witness, (), system_pcm16=system, skip=skip))
    published = []
    engine = GeminiHybridEngine(published.append, word_source=object(),
        window_scheduler=FixedWindowScheduler(), registry=OverlapRegistry(),
        diarizer=Cleanup(), terminal=terminal, word_gate=gate, source_lane='microphone')
    engine._publish_window(0, 15*S, mic, anchor+reply[:2])
    next_words = tuple(GeminiWord(x.text, next_label, x.start_sample, x.end_sample) for x in anchor+reply)
    engine._publish_window(0, 30*S, mic, next_words)
    assert {r.speaker for update in published for r in getattr(update, 'segments', ())} == {'speaker-0001'}
    class VoiceTape:
        sample_count = len(mic)//2
        def read(self, *, start_sample=0, end_sample=None):
            return mic[2*start_sample:None if end_sample is None else 2*end_sample]
    try:
        asyncio.run(engine.finish(VoiceTape()))
        assert [x.text for x in terminal.last_words if x.text != 'genuine'] == [x.text for x in reply]
    finally:
        engine.close()


@pytest.mark.parametrize('seconds,word_count', [(30, 5), (45, 24)])
def test_microphone_witness_admission_preserves_provider_counters_and_anchor(seconds, word_count):
    mic, system = _local_fixture(((8, 12.1),), seconds=seconds)
    counts = []
    gate = _local_gate(system, counts)
    words = _local_phrase(' '.join(['local']*word_count), 8.4, 12 if word_count == 24 else 9.2)
    live = gate.filter(mic, words)
    # Candidate admission must not create an anchor even for a long witnessed turn.
    gate.local_speech_seen = False
    kept = gate.filter_terminal(mic, (), (), system_pcm16=system)
    before = [dict(row) for row in counts]
    rescue = gate._local_level_kept, gate._local_unanchored_kept, gate.lane_withheld_words
    output, restored = gate.restore_witnessed_words(mic, (), kept, live, (), system_pcm16=system)
    assert len(output) == word_count and len(restored) == 1
    assert counts == before
    assert (gate._local_level_kept, gate._local_unanchored_kept, gate.lane_withheld_words) == rescue
    assert not gate.local_speech_seen


def test_microphone_witness_pass_scans_voice_once_and_bounds_embedding_audio():
    from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate
    mic, system = _local_fixture(((8, 12.1), (68, 72.1), (128, 132.1)), seconds=180)
    gate = _local_gate(system, [])
    class CountingVad:
        frames = 0
        def is_speech(self, pcm, rate):
            self.frames += 1
            return True
    vad = CountingVad()
    gate.webrtc_gate = WebRtcWordGate(vad)
    embedded = []
    def embed(pcm, start, words):
        embedded.append((len(pcm), start, tuple(words)))
        return {}
    gate.embedding_source = embed
    remote = _local_phrase(' '.join(['remote']*24), 1, 4, 'tab')
    witnesses = sum((_local_phrase(' '.join(['local']*24), start, start+3.6)
                     for start in (8.4, 68.4, 128.4)), ())
    cleanup = tuple(w('neighbour', start, start+.1, 'final') for start in (5, 65, 125))
    output, restored = gate.restore_witnessed_words(mic, cleanup, cleanup, witnesses, remote, system_pcm16=system)
    assert len(output) == 75 and len(restored) == 3
    assert vad.frames == 180*100
    assert sum(words == remote for _, _, words in embedded) == 1
    assert all(size <= 4*S*2 for size, _, words in embedded if words != remote)
    before = vad.frames, len(embedded)
    assert gate.restore_witnessed_words(mic, (), (), (), remote, system_pcm16=system) == ((), [])
    assert (vad.frames, len(embedded)) == before


def test_microphone_witness_reuses_saved_contexts_and_system_vectors():
    mic, system = _local_fixture(((11.8, 15.8),))
    gate = _local_gate(system, [])
    anchor = _local_phrase(' '.join(['genuine']*26), 11.8, 14.4)
    reply = _local_phrase(start=14.6, end=15.6)
    remote = _local_phrase('remote tab turn', 1, 4, 'tab')
    scans, embedded = [], []
    frames = gate.local_voice._frames
    def scan(*args):
        scans.append(len(args[0]))
        return frames(*args)
    def embed(pcm, start, words):
        embedded.append(tuple(words))
        return {}
    gate.local_voice._frames = scan
    gate.embedding_source = embed
    kept = gate.filter_terminal(mic, anchor, remote, system_pcm16=system)
    before = len(scans)
    output, restored = gate.restore_witnessed_words(mic, anchor, kept, reply, remote, system_pcm16=system)
    assert len(output) == 31 and len(restored) == 1
    assert len(scans) == before+1  # The reply also needs the next context; the first is reused.
    assert embedded.count(remote) == 1


def _mixed_witness_fixture():
    mic, system = _local_fixture(((5.5, 7.9), (8.4, 9.6)), echo=56)
    anchor = _local_phrase(' '.join(['genuine']*20), 5.6, 7.9, 'A')
    stray = (w('remote', 8.2, 8.4, 'A'),)
    reply = _local_phrase('Can you elaborate please?', 8.5, 9.3, 'B')
    cleanup = anchor+(w('neighbour', 12, 12.2, 'final'),)
    remote = (w('remote', 8.2, 8.4, 'tab'),)
    return mic, system, anchor+stray+reply, cleanup, remote, reply


def _mixed_terminal(gate, mic, system, cleanup, remote):
    class Cleanup:
        def diarize(self, *args, **kwargs): return GeminiWords(cleanup)
    return TerminalTranscriber(Cleanup(), source_lane='microphone', word_gate=gate.webrtc_gate,
        word_filter=lambda words: gate.filter_terminal(mic, words, remote, system_pcm16=system),
        witness_filter=lambda raw, kept, witness, skip: gate.restore_witnessed_words(
            mic, raw, kept, witness, remote, system_pcm16=system, skip=skip))


@pytest.mark.parametrize('anchored', [False, True])
def test_terminal_mixed_published_speakers_restore_reply_without_borrowed_stray(anchored):
    mic, system, words, cleanup, remote, reply = _mixed_witness_fixture()
    gate = _local_gate(system, [], remote)
    assert gate.filter(mic, words) == words
    gate.local_speech_seen = anchored
    terminal = _mixed_terminal(gate, mic, system, cleanup, remote)
    published = tuple(GeminiWord(x.text, 'speaker-0002' if x.speaker == 'B' else 'speaker-0001',
                                x.start_sample, x.end_sample) for x in words)
    terminal.set_witness_words(published)
    class VoiceTape:
        sample_count = len(mic)//2
        def read(self, *, start_sample=0, end_sample=None):
            return mic[2*start_sample:None if end_sample is None else 2*end_sample]
    terminal.transcribe(VoiceTape())
    saved = [x.text for x in terminal.last_words if 8*S <= x.start_sample < 10*S]
    assert saved == [x.text for x in reply]


def test_engine_mixed_speaker_witnesses_keep_published_partitions_through_finish():
    mic, system, words, cleanup, remote, reply = _mixed_witness_fixture()
    gate = _local_gate(system, [], remote)
    terminal = _mixed_terminal(gate, mic, system, cleanup, remote)
    updates = []
    engine = GeminiHybridEngine(updates.append, word_source=object(),
        window_scheduler=FixedWindowScheduler(), registry=OverlapRegistry(),
        diarizer=terminal.diarizer, terminal=terminal, word_gate=gate, source_lane='microphone')
    class VoiceTape:
        sample_count = len(mic)//2
        def read(self, *, start_sample=0, end_sample=None):
            return mic[2*start_sample:None if end_sample is None else 2*end_sample]
    try:
        engine._publish_window(0, len(mic)//2, mic, words)
        assert any(x.text == 'remote' for x in engine._witness_words)
        asyncio.run(engine.finish(VoiceTape()))
        saved = [x.text for x in terminal.last_words if 8*S <= x.start_sample < 10*S]
        assert saved == [x.text for x in reply]
        witness_labels = {x.text: x.speaker for x in engine._witness_words if 8*S <= x.start_sample < 10*S}
        assert witness_labels['remote'] == 'speaker-0001'
        assert all(witness_labels[x.text] == 'speaker-0002' for x in reply)
        assert {r.speaker for update in updates for r in getattr(update, 'segments', ())} == {'speaker-0001', 'speaker-0002'}
    finally:
        engine.close()


@pytest.mark.parametrize('same_speaker', [False, True])
def test_two_word_replies_keep_each_published_speakers_own_text_weight(same_speaker):
    mic, system = _local_fixture(((8.4, 9.6),), echo=56)
    gate = _local_gate(system, [])
    words = _local_phrase('Thanks everyone', 8.5, 8.9, 'speaker-0001')+_local_phrase(
        'Sounds good', 9, 9.4, 'speaker-0001' if same_speaker else 'speaker-0002')
    cleanup = (w('neighbour', 12, 12.2, 'final'),)
    output, restored = gate.restore_witnessed_words(mic, cleanup, cleanup, words, (), system_pcm16=system)
    assert len(output) == (5 if same_speaker else 1)
    assert bool(restored) == same_speaker


def test_unassigned_microphone_witnesses_keep_distinct_request_partitions():
    mic, system = _local_fixture(((8.4, 9.6),), echo=56, seconds=45)
    gate = _local_gate(system, [])
    words = _local_phrase('Thanks everyone', 8.5, 8.9, 'A')+_local_phrase('Sounds good', 9, 9.4, 'B')
    cleanup = (w('neighbour', 12, 12.2, 'final'),)
    terminal = _mixed_terminal(gate, mic, system, cleanup, ())
    class UnassignedRegistry:
        def observe_window(self, start, words, *args, **kwargs):
            return {x.speaker: None for x in words}, ()
    engine = GeminiHybridEngine(lambda update: None, word_source=object(),
        window_scheduler=FixedWindowScheduler(), registry=UnassignedRegistry(),
        diarizer=terminal.diarizer, terminal=terminal, source_lane='microphone')
    class VoiceTape:
        sample_count = len(mic)//2
        def read(self, *, start_sample=0, end_sample=None):
            return mic[2*start_sample:None if end_sample is None else 2*end_sample]
    try:
        engine._publish_window(0, 15*S, mic, words)
        engine._publish_window(0, 31*S, mic, (w('new', 30, 30.2, 'A'),))
        assert len({x.speaker for x in engine._witness_words}) == 3
        asyncio.run(engine.finish(VoiceTape()))
        assert not any(x.text in {w.text for w in words} for x in terminal.last_words)
    finally:
        engine.close()
