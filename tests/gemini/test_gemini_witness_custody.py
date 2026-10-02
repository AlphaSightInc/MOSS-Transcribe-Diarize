"""C2/pass4 regressions: evidence correspondence is independent of displayed identity."""
import asyncio

import pytest

from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry
from moss_transcribe_diarize.app.gemini_hybrid_engine import GeminiHybridEngine, GrowingContextWindowScheduler
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiRolling
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords, TerminalTranscriber
from moss_transcribe_diarize.app.live_transcript_convergence import terminal_speaker_mapping
from test_gemini_lane_engine import _local_fixture, _local_gate, _local_phrase

S = 16000


class Tape:
    def __init__(self, pcm):
        self.pcm = pcm
        self.sample_count = len(pcm)//2

    def read(self, *, start_sample=0, end_sample=None):
        return self.pcm[start_sample*2:None if end_sample is None else end_sample*2]


def engine_for(mic, tab, cleanup, embeddings, remote=()):
    gate = _local_gate(tab, [], remote)
    class Decoder:
        def diarize(self, *args, **kwargs):
            return GeminiWords(cleanup)
    terminal = TerminalTranscriber(Decoder(), source_lane='microphone', word_gate=gate.webrtc_gate,
        word_filter=lambda words: gate.filter_terminal(mic, words, remote, system_pcm16=tab),
        witness_filter=lambda raw, kept, witness, skip: gate.restore_witnessed_words(
            mic, raw, kept, witness, remote, system_pcm16=tab, skip=skip))
    updates = []
    engine = GeminiHybridEngine(updates.append, word_source=object(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=30, stride_seconds=15),
        registry=ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                   birth_min_seconds=2, id_prefix='local'),
        diarizer=Decoder(), terminal=terminal, word_gate=gate, embedding_source=embeddings,
        source_lane='microphone')
    return engine, terminal, updates


@pytest.mark.parametrize('identity', ['unassigned', 'born', 'changed_label'])
def test_unassigned_or_born_reply_keeps_source_correspondence_across_frontier(identity):
    mic, tab = _local_fixture(((11.8, 15.8), (20, 23)), echo=100)
    anchor = _local_phrase(' '.join(['genuine']*26), 11.8, 14.4, 'anchor-A')
    reply = _local_phrase('Can you elaborate on that?', 14.6, 15.6, 'reply-B')
    later = _local_phrase('This is my later longer local speech turn', 20, 22.6, 'reply-B') if identity == 'born' else ()
    def embeddings(pcm, start, words):
        from moss_transcribe_diarize.app.gemini_hybrid_engine import attributed_embedding_intervals
        return {label: ((1., 0.) if label == 'anchor-A' else (0., 1.), sum(b-a for a, b in spans)/S)
                for label, spans in attributed_embedding_intervals(words, start).items()}
    engine, terminal, updates = engine_for(mic, tab, anchor+later, embeddings)
    try:
        engine._publish_window(0, 15*S, mic[:30*S], anchor+reply[:2])
        second = anchor+reply+later
        if identity == 'changed_label':
            second = tuple(GeminiWord(w.text, 'reply-C' if w.speaker == 'reply-B' else w.speaker,
                                      w.start_sample, w.end_sample) for w in second)
        engine._publish_window(0, 30*S, mic, second)
        engine.set_terminal_witness(tuple(r for u in updates if isinstance(u, GeminiRolling) for r in u.segments))
        asyncio.run(engine.finish(Tape(mic)))
        assert [w.text for w in terminal.last_words if 14.5*S < w.start_sample < 16*S] == [w.text for w in reply]
        if identity == 'born':
            witnesses = [w for w in engine._witness_words if 14.5*S < w.start_sample < 16*S]
            assert {w.speaker for w in witnesses} == {'local-0002'}
    finally:
        engine.close()


def test_reassigned_identity_splits_old_source_only_at_positive_word_matches():
    mic, tab = _local_fixture(((5.5, 7.9), (10, 12.8), (14.4, 15.8), (20, 23)), echo=100)
    a = _local_phrase(' '.join(['personA']*20), 5.6, 7.9, 'A')
    c = _local_phrase(' '.join(['personB']*20), 10, 12.6, 'C')
    reply = _local_phrase('Can you elaborate on that?', 14.6, 15.6, 'A')
    later = _local_phrase('This is my later longer local speech turn', 20, 22.6, 'A')
    vectors = [{'A': ((1., 0.), 2.7), 'C': ((0., 1.), 2.6)},
               {'D': ((1., 0.), 2.3), 'A': ((0., 1.), 3.6), 'C': ((0., 1.), 2.6)}]
    engine, terminal, _ = engine_for(mic, tab, a+c+later, lambda *args: vectors.pop(0))
    try:
        engine._publish_window(0, 15*S, mic[:30*S], a+c+reply[:2])
        a2 = tuple(GeminiWord(w.text, 'D', w.start_sample, w.end_sample) for w in a)
        engine._publish_window(0, 30*S, mic, a2+c+reply+later)
        asyncio.run(engine.finish(Tape(mic)))
        assert [w.text for w in terminal.last_words if 14.5*S < w.start_sample < 16*S] == [w.text for w in reply]
    finally:
        engine.close()


@pytest.mark.parametrize('case', ['stray', 'two_short_replies'])
def test_aliased_published_identity_cannot_pool_request_source_evidence(case):
    mic, tab = _local_fixture(((5.5, 7.9), (8.4, 9.6), (20, 23)), echo=56 if case == 'stray' else 100)
    a = _local_phrase(' '.join(['anchorA']*20), 5.6, 7.9, 'A')
    b = _local_phrase(' '.join(['anchorB']*20), 20, 22.6, 'B')
    suspect = (GeminiWord('remote', 'A', round(8.2*S), round(8.4*S)),) if case == 'stray' else _local_phrase('Thanks everyone', 8.5, 8.9, 'A')
    reply = _local_phrase('Can you elaborate please?', 8.5, 9.3, 'B') if case == 'stray' else _local_phrase('Sounds good', 9, 9.4, 'B')
    remote = (GeminiWord('remote', 'tab', round(8.2*S), round(8.4*S)),) if case == 'stray' else ()
    engine, terminal, updates = engine_for(mic, tab, a+b,
        lambda *args: {'A': ((1., 0.), 2.3), 'B': ((1., 0.), 2.6)}, remote)
    try:
        engine._publish_window(0, 30*S, mic, a+suspect+reply+b)
        assert {r.speaker for u in updates if isinstance(u, GeminiRolling) for r in u.segments} == {'local-0001'}
        asyncio.run(engine.finish(Tape(mic)))
        assert [w.text for w in terminal.last_words if 8*S < w.start_sample < 10*S] == ([w.text for w in reply] if case == 'stray' else [])
    finally:
        engine.close()


def test_restored_whole_utterance_keeps_its_live_name_without_final_neighbours():
    live = (GeminiWord('welcome', 'Ben', 52*S, 53*S), GeminiWord('Gilbert', 'Ben', 67*S, 68*S))
    class Decoder:
        def diarize(self, *args, **kwargs):
            return GeminiWords((GeminiWord('jingle', 'A', 50*S, 51*S), GeminiWord('next', 'B', 69*S, 70*S)))
    terminal = TerminalTranscriber(Decoder(), source_lane='system')
    terminal.set_witness_words(live)
    rows = terminal.transcribe(Tape(bytes(140*S)))
    from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment
    surface = tuple(EffectiveTranscriptSegment(w.start_sample, w.end_sample, w.text, w.speaker, 'rolling', 'system') for w in live)
    mapping = terminal_speaker_mapping(tuple((r.speaker, r.start_sample, r.end_sample, r.text) for r in rows), base_surface=surface, canonical_speakers=('Ben',))
    welcome = next(r for r in rows if 'welcome' in r.text)
    assert mapping[welcome.speaker] == 'Ben'
    assert [w.speaker for w in terminal.last_words if w.text == 'welcome'] == ['witness-Ben']
    assert next(w for w in terminal.last_words if w.text == 'jingle').speaker != welcome.speaker


def test_restored_name_bridges_same_live_person_instead_of_closest_other_speaker():
    class Decoder:
        def diarize(self, *args, **kwargs):
            return GeminiWords((GeminiWord('own', 'A', S, 2*S), GeminiWord('other', 'B', 5*S, 6*S)))
    terminal = TerminalTranscriber(Decoder(), source_lane='system')
    terminal.set_witness_words((GeminiWord('own', 'published-own', S, 2*S), GeminiWord('name', 'published-own', 6*S, round(6.3*S))))
    terminal.transcribe(Tape(bytes(24*S)))
    own, other, name = terminal.last_words
    assert name.speaker == own.speaker and name.speaker != other.speaker


@pytest.mark.parametrize('collision', ['within_step', 'same_time'])
def test_single_common_word_cannot_pool_two_people_short_replies(collision):
    mic, tab = _local_fixture(((11.8, 15.8),), echo=100)
    anchor = _local_phrase(' '.join(['genuine']*26), 11.8, 14.4, 'anchor-X')
    first = (GeminiWord('Thanks', 'A', round(14.6*S), round(14.8*S)),
             GeminiWord('okay', 'A', round(14.8*S), round(14.9*S)))
    second = _local_phrase('sounds good', 15, 15.4, 'B')
    context = GeminiWord('okay', 'B', round((14.9 if collision == 'within_step' else 14.8)*S),
                         round((15 if collision == 'within_step' else 14.9)*S))
    engine, terminal, _ = engine_for(mic, tab, anchor, lambda *args: {
        'anchor-X': ((1., 0.), 2.6), 'A': ((0., 1.), .3), 'B': ((-.6, .8), .5)})
    try:
        engine._publish_window(0, 15*S, mic[:30*S], anchor+first)
        engine._publish_window(0, 30*S, mic, anchor+(context,)+second)
        witnesses = [w for w in engine._witness_words if w.start_sample > 14.5*S]
        assert len({w.source_partition for w in witnesses}) == 2
        asyncio.run(engine.finish(Tape(mic)))
        assert not [w for w in terminal.last_words if w.start_sample > 14.5*S]
    finally:
        engine.close()


@pytest.mark.parametrize('context_text', ['okay', 'yes'])
def test_rejected_partition_cannot_lend_or_veto_genuine_reply(context_text):
    mic, tab = _local_fixture(((11.4, 14), (14.6, 15.8)), echo=56)
    anchor = _local_phrase(' '.join(['genuine']*26), 11.4, 14, 'A')
    unrelated = (GeminiWord('remote', 'A', round(14.3*S), round(14.5*S)),
                 GeminiWord('okay', 'A', round(14.8*S), round(14.9*S)))
    reply = _local_phrase('Can you elaborate please?', 15, 15.8, 'B')
    engine, terminal, _ = engine_for(mic, tab, anchor, lambda *args: {
        'A': ((1., 0.), 2.9), 'B': ((-.6, .8), .8)})
    try:
        engine._publish_window(0, 15*S, mic[:30*S], anchor+unrelated)
        engine._publish_window(0, 30*S, mic, (GeminiWord(context_text, 'B', round(14.9*S), 15*S),)+reply)
        asyncio.run(engine.finish(Tape(mic)))
        assert [w.text for w in terminal.last_words if w.start_sample > 14.2*S] == [w.text for w in reply]
    finally:
        engine.close()


def test_correspondence_needs_two_distinct_occurrences_in_both_requests():
    from moss_transcribe_diarize.app.gemini_coverage import WitnessWord, source_partitions
    old = [WitnessWord('okay', 'published', 100, 200, 'prior')]
    new = [GeminiWord('okay', 'B', 100, 200), GeminiWord('okay', 'B', 101, 201)]
    updated, mapping, context = source_partitions(old, old, new, 1000)
    assert mapping['B'] != 'prior' and updated == old and not context
    old = [WitnessWord('okay', 'published', 100, 200, 'prior'),
           WitnessWord('okay', 'published', 101, 201, 'prior')]
    new = [GeminiWord('okay', 'B', 100, 200)]
    updated, mapping, context = source_partitions(old, old, new, 1000)
    assert mapping['B'] != 'prior' and updated == old and not context


def test_one_word_reheard_prefix_keeps_only_independently_eligible_suffix():
    mic, tab = _local_fixture(((11.8, 15.8),), echo=100)
    anchor = _local_phrase(' '.join(['genuine']*26), 11.8, 14.4, 'anchor-A')
    reply = _local_phrase('Can you elaborate on that?', 14.7, 15.7, 'reply-B')
    engine, terminal, _ = engine_for(mic, tab, anchor, lambda *args: {'anchor-A': ((1., 0.), 2.6)})
    try:
        engine._publish_window(0, 15*S, mic[:30*S], anchor+reply[:1])
        engine._publish_window(0, 30*S, mic, anchor+reply)
        asyncio.run(engine.finish(Tape(mic)))
        assert [w.text for w in terminal.last_words if w.start_sample > 14.5*S] == [w.text for w in reply[1:]]
    finally:
        engine.close()


def test_weak_competing_label_still_blocks_whole_partition_continuation():
    from moss_transcribe_diarize.app.gemini_coverage import WitnessWord, source_partitions
    old = [WitnessWord('Can', 'published', S, S+3200, 'prior'),
           WitnessWord('you', 'published', 2*S, 2*S+3200, 'prior'),
           WitnessWord('remote', 'published', 3*S, 3*S+3200, 'prior')]
    new = [GeminiWord(w.text, 'B' if w.text == 'remote' else 'A', w.start_sample, w.end_sample) for w in old]
    updated, mapping, _ = source_partitions(old, old, new, 4*S)
    assert mapping['A'] != 'prior'
    assert [w.source_partition for w in updated] == [mapping['A'], mapping['A'], 'prior']
    assert mapping['B'] not in ('prior', mapping['A'])


def test_weak_competing_partition_still_blocks_merging_old_groups():
    from moss_transcribe_diarize.app.gemini_coverage import WitnessWord, source_partitions
    old = [WitnessWord('Can', 'published', S, S+3200, 'pA'),
           WitnessWord('you', 'published', 2*S, 2*S+3200, 'pA'),
           WitnessWord('remote', 'published', 3*S, 3*S+3200, 'pB')]
    new = [GeminiWord(w.text, 'merged', w.start_sample, w.end_sample) for w in old]
    updated, mapping, _ = source_partitions(old, old, new, 4*S)
    assert mapping['merged'] not in ('pA', 'pB') and updated == old


def _finish_mixed_shift(*, cleanup_has_reply, rejected_neighbour):
    mic, tab = _local_fixture(((11.4, 14.0), (14.6, 17.0)), echo=56)
    anchor = _local_phrase(' '.join(['genuine']*26), 11.4, 14.0, 'A')
    unrelated = (GeminiWord('remote', 'A', round(14.3*S), round(14.5*S)),
                 GeminiWord('okay', 'A', round(14.8*S), round(14.9*S)))
    reply = _local_phrase('Can you elaborate please?', 15, 15.8, 'B')
    shifted = tuple(GeminiWord(w.text, w.speaker, w.start_sample+S, w.end_sample+S)
                    for w in reply)
    cleanup = anchor+(shifted if cleanup_has_reply else ())
    engine, terminal, _ = engine_for(mic, tab, cleanup, lambda *args: {
        'A': ((1., 0.), 2.9), 'B': ((-.6, .8), .8)})
    usage = []
    terminal.report_usage = lambda **row: usage.append(row)
    try:
        engine._publish_window(0, 15*S, mic[:30*S], anchor+(unrelated if rejected_neighbour else ()))
        engine._publish_window(0, 30*S, mic, reply)
        witnesses = [w for w in engine._witness_words if w.start_sample > 14.2*S]
        assert [w.text for w in witnesses] == [w.text for w in
                                               ((unrelated if rejected_neighbour else ())+reply)]
        if rejected_neighbour:
            assert len({w.source_partition for w in witnesses}) == 2
        rows = asyncio.run(engine.finish(Tape(mic)))
        saved = [w for w in terminal.last_words if w.start_sample > 14.2*S]
        assert [w.text for w in saved] == [w.text for w in reply]
        assert [(w.start_sample, w.end_sample) for w in saved] == [
            (w.start_sample, w.end_sample) for w in (shifted if cleanup_has_reply else reply)]
        assert 'Can you elaborate please? Can' not in ' '.join(r.text for r in rows)
        assert sum(r.get('witness_restored_words', 0) for r in usage) == (0 if cleanup_has_reply else 4)
    finally:
        engine.close()


def test_shifted_reply_with_rejected_source_is_saved_once():
    _finish_mixed_shift(cleanup_has_reply=True, rejected_neighbour=True)


def test_genuine_omission_with_rejected_source_is_restored_once():
    _finish_mixed_shift(cleanup_has_reply=False, rejected_neighbour=True)


def test_isolated_shifted_reply_stays_saved_once():
    _finish_mixed_shift(cleanup_has_reply=True, rejected_neighbour=False)
