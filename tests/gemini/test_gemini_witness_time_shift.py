"""H2: stress text reconstructions with injected word clocks, plus omission controls."""
import pytest

from moss_transcribe_diarize.app import gemini_coverage as coverage
from moss_transcribe_diarize.app.gemini_provider import GeminiWord as Word, GeminiWords, TerminalTranscriber
from test_gemini_lane_engine import _local_fixture, _local_gate, _local_phrase

S = 16000


def w(text, a, b, speaker='unassigned-live'):
    return Word(text, speaker, round(a*S), round(b*S))


@pytest.mark.parametrize('side', ['before', 'after'])
def test_reconstructed_c7_shifted_phrase_is_saved_once(side):
    # c7 exported text: live "Who got the truth?", saved "Who got the got the truth?".
    # Original pre-H annotations unavailable; these per-word timings are a reconstruction.
    if side == 'after':
        cleanup = (w('Who', 41, 41.2), w('got', 41.7, 41.8),
                   w('the', 41.8, 41.9), w('truth?', 41.9, 42.1))
        live = (w('got', 41.2, 41.4), w('the', 41.4, 41.6))
    else:
        cleanup = (w('Who', 41, 41.1), w('got', 41.1, 41.3),
                   w('the', 41.3, 41.5), w('truth?', 41.9, 42.1))
        live = (w('got', 41.6, 41.7), w('the', 41.7, 41.9))
    output, restored = coverage.restore_system_witnessed_words(cleanup, live)
    assert ' '.join(x.text for x in output) == 'Who got the truth?'
    assert restored == []
    assert all(a is b for a, b in zip(cleanup, output))


@pytest.mark.parametrize('grouped', [False, True])
def test_reconstructed_c5b_shifted_chinese_grouping_is_saved_once(grouped):
    # c5b live frontier "产品规划。大家好…", saved "…产品规划。规划。大家好…".
    # Preserve exported frontier270.400375; inject clocks and pre-H words explicitly.
    cleanup = (w('产品规划。', 270, 270.2, 'final-a'), w('大家好', 270.8, 271, 'final-b'))
    live = ((w('规划。', 270.400375, 270.8),) if grouped else
            (w('规', 270.400375, 270.6), w('划。', 270.6, 270.8)))
    output, restored = coverage.restore_system_witnessed_words(cleanup, live)
    assert ''.join(x.text for x in output) == '产品规划。大家好'
    assert restored == []
    assert output == cleanup


def test_shifted_phrase_uses_existing_numeral_equality():
    cleanup = (w('十', 1, 1.2), w('days.', 1.2, 1.4), w('next', 2.2, 2.4))
    output, restored = coverage.restore_witnessed_words(cleanup, (w('10', 1.6, 1.8), w('DAYS!', 1.8, 2)))
    assert output == cleanup and restored == []


def test_microphone_time_shift_is_removed_before_local_admission():
    mic, system = _local_fixture()
    gate = _local_gate(system, [])
    live = _local_phrase()
    cleanup = tuple(Word(x.text, 'final-local', x.start_sample+S, x.end_sample+S) for x in live)
    output, restored = gate.restore_witnessed_words(mic, cleanup, cleanup, live, (), system_pcm16=system)
    assert output == cleanup and restored == []


def test_terminal_time_shift_keeps_final_words_and_zero_restore_counter():
    cleanup = (w('Who', 1, 1.2, 'final'), w('got', 1.7, 1.8, 'final'),
               w('the', 1.8, 1.9, 'final'), w('truth?', 1.9, 2.1, 'final'))
    class Decoder:
        def diarize(self, *args, **kwargs):
            return GeminiWords(cleanup)
    class Tape:
        sample_count = 3*S
        def read(self, *, start_sample=0, end_sample=None):
            return bytes(2*((self.sample_count if end_sample is None else end_sample)-start_sample))
    usage = []
    terminal = TerminalTranscriber(Decoder(), report_usage=lambda **row: usage.append(row))
    terminal.transcribe(Tape())
    baseline = terminal.last_words
    terminal.set_witness_words((w('got', 1.2, 1.4), w('the', 1.4, 1.6)))
    rows = terminal.transcribe(Tape())
    assert ' '.join(r.text for r in rows) == 'Who got the truth?'
    assert terminal.last_words == baseline
    assert sum(r.get('witness_restored_words', 0) for r in usage) == 0


def test_omitted_name_occurring_elsewhere_is_still_restored():
    cleanup = (w('Media', 1, 1.2), w('Lab', 1.2, 1.4), w('then', 1.4, 1.6),
               w('visited', 2.2, 2.4), w('today', 3.2, 3.4))
    output, restored = coverage.restore_witnessed_words(cleanup, (w('Media', 2.5, 2.7), w('Lab', 2.7, 2.9)))
    assert ' '.join(x.text for x in output) == 'Media Lab then visited Media Lab today'
    assert restored[0]['text'] == ['Media', 'Lab']


@pytest.mark.parametrize('gap,restored_count', [(1., 0), (1.0000625, 2)])
def test_time_shift_neighbourhood_is_bounded_in_time(gap, restored_count):
    cleanup = (w('thank you', 1, 1.4), w('next', 5, 5.2))
    live = (w('thank', 1.4+gap, 1.6+gap), w('you', 1.6+gap, 1.8+gap))
    output, restored = coverage.restore_witnessed_words(cleanup, live)
    assert len(output) == len(cleanup)+restored_count


@pytest.mark.parametrize('count,restored_count', [(12, 0), (13, 13)])
def test_time_shift_neighbourhood_is_bounded_in_units(count, restored_count):
    # Use all-letter words; the comparable-unit tokenizer separates letters and numerals.
    tokens = [chr(97+i)+'word' for i in range(count)]
    cleanup = (w(' '.join(tokens), 1, 1.4), w('next', 2.5, 2.7))
    live = tuple(w(token, 1.6+i*.03, 1.63+i*.03) for i, token in enumerate(tokens))
    output, restored = coverage.restore_witnessed_words(cleanup, live)
    assert len(output) == len(cleanup)+restored_count


def test_live_stutter_absent_from_cleanup_remains_restored():
    cleanup = (w('and', 37.3, 37.5), w('next', 39, 39.2))
    live = (w('uh', 37.5, 37.5), w('I', 38, 38.2), w('I', 38.2, 38.2))
    output, restored = coverage.restore_witnessed_words(cleanup, live)
    assert ' '.join(x.text for x in output) == 'and uh I I next'


def test_partial_run_next_to_similar_phrase_keeps_omitted_name():
    cleanup = (w('thank', 1, 1.2), w('you', 1.2, 1.4), w('next', 2.5, 2.7))
    live = (w('thank', 1.6, 1.8), w('you', 1.8, 2), w('Cosette', 2, 2.3))
    output, restored = coverage.restore_witnessed_words(cleanup, live)
    assert restored[0]['text'] == ['thank', 'you', 'Cosette']
    assert [x.text for x in output].count('Cosette') == 1


@pytest.mark.parametrize('tokens', [('yes', 'yes'), ('对', '对', '对')])
def test_genuine_adjacent_repetition_is_withheld_as_accepted_loss(tokens):
    cleanup = (w(' '.join(tokens), 1, 1.4), w('next', 2.5, 2.7))
    live = tuple(w(token, 1.6+i*.2, 1.8+i*.2) for i, token in enumerate(tokens))
    output, restored = coverage.restore_witnessed_words(cleanup, live)
    assert output == cleanup and restored == []
