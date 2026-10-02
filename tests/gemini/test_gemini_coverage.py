"""Rule H regression seeds, recorded F3 patterns with provider times unchanged."""
from moss_transcribe_diarize.app import gemini_coverage as coverage
from moss_transcribe_diarize.app.gemini_provider import GeminiWord as Word
S = 16000

def owned(words, frontiers):
    result = []
    for word, frontier in zip(words, frontiers):
        result = coverage.drop_restated(result, [word], frontier)
    return result

def w(text, a, b, speaker='t1'):
    return Word(text, speaker, int(round(a * S)), int(round(b * S)))

def run(cleanup, live, frontiers=None):
    live = owned(live, frontiers) if frontiers else live
    out, restored = coverage.restore_witnessed_words(cleanup, live)
    text = ' '.join((x.text for x in sorted(out, key=lambda x: (x.start_sample, x.end_sample))))
    return (text, restored, out)

def test_omitted_name_is_restored_in_its_hole():
    text, restored, out = run([w('院', 5.2, 5.3), w('计', 5.8, 5.9)], [w('院', 5.2, 5.3), w('Media', 5.3, 5.5), w('Lab', 5.5, 5.7), w('的', 5.7, 5.8), w('計', 5.8, 5.9)])
    assert text == '院 Media Lab 的 计'

def test_word_after_the_hole_is_not_doubled():
    text, restored, out = run([w('院', 2.1, 2.3), w('的', 2.6, 2.8), w('计', 2.8, 2.9)], [w('Media', 2.3, 2.5), w('Lab', 2.5, 2.7), w('的', 2.7, 2.8)])
    assert text == '院 Media Lab 的 计'

def test_abutting_word_after_hole_is_not_doubled():
    text, restored, out = run([w('院', 7.2, 7.3), w('的', 7.8, 7.9), w('計', 7.9, 8.0)], [w('Media', 7.3, 7.5), w('Lab', 7.5, 7.7), w('的', 7.7, 7.8)])
    assert text == '院 Media Lab 的 計'

def test_replacement_is_kept():
    text, restored, out = run([w('道', 15.8, 16.0), w('Computer', 16.0, 16.5), w('File', 16.5, 16.7), w('10', 16.7, 16.9)], [w('道', 15.8, 15.9), w('Computerphile', 15.9, 16.6), w('10', 16.6, 16.8)])
    assert text == '道 Computer File 10'

def test_name_with_neighbour_one_step_into_it_is_restored():
    text, restored, out = run([w('道', 15.8, 16.0), w('10', 16.7, 16.8)], [w('道', 15.8, 15.9), w('Computerphile', 15.9, 16.6), w('10', 16.6, 16.8)])
    assert text == '道 Computerphile 10'

def test_same_number_written_two_ways_is_not_doubled():
    text, restored, out = run([w('道', 15.8, 16.0), w('十', 16.7, 16.8), w('月', 16.8, 16.9)], [w('Computer', 15.9, 16.3), w('File', 16.3, 16.6), w('10', 16.6, 16.8)])
    assert text == '道 Computer File 十 月'

def test_one_time_step_of_jitter_is_not_a_hole():
    text, restored, out = run([w('年。', 9.5, 9.9), w('他', 10.0, 10.1), w('研', 10.1, 10.3)], [w('年。', 9.4, 9.9), w('他', 9.9, 10.0), w('研', 10.1, 10.3)])
    assert text == '年。 他 研'

def test_long_live_word_over_the_same_cleanup_word_is_not_doubled():
    text, restored, out = run([w('though.', 26.8, 27.0), w('Amazing.', 28.2, 28.5), w('Why', 29.0, 29.2)], [w('though.', 26.8, 27.1), w('Amazing.', 27.4, 28.5)])
    assert text == 'though. Amazing. Why'

def test_frontier_restatement_is_not_a_witness():
    text, restored, out = run([w('道', 14.3, 14.4), w('10', 15.1, 15.3)], [w('道', 14.3, 14.4), w('Computer', 14.4, 14.8), w('Computerphile', 14.4, 15.1), w('10', 15.1, 15.3)], frontiers=[0, 0, int(15 * S), int(15 * S)])
    assert text == '道 Computerphile 10'

def test_abutting_frontier_restatement_is_not_a_witness():
    text, restored, out = run([w('们', 14.4, 14.6), w('先', 15.1, 15.3)], [w('们', 14.4, 14.7), w('要', 14.8, 14.9), w('要', 14.9, 15.1), w('先', 15.1, 15.3)], frontiers=[0, 0, int(15 * S), int(15 * S)])
    assert text == '们 要 先'

def test_frontier_duplicate_covered_by_cleanup_stays_removed():
    text, restored, out = run([w('会', 14.7, 14.9), w('议。', 14.9, 15.1), w('这', 15.2, 15.3)], [w('會', 14.7, 14.8), w('議。', 14.8, 14.9), w('议。', 14.9, 15.1), w('这', 15.1, 15.3)], frontiers=[0, 0, int(15 * S), int(15 * S)])
    assert text == '会 议。 这'

def test_mistimed_live_word_is_not_restored():
    text, restored, out = run([w('我', 12.0, 12.1), w('觉', 12.1, 12.3)], [w('我', 0.1, 0.2), w('觉', 12.0, 12.3)])
    assert text == '我 觉'

def test_restored_run_takes_nearer_neighbour_speaker_and_kept_words_keep_theirs():
    text, restored, out = run([w('bard', 19.2, 19.6, 't2'), w('But', 21.0, 21.2, 't3')], [w('there.', 19.7, 20.0, 'live')])
    assert [x.speaker for x in sorted(out, key=lambda x: x.start_sample)] == ['t2', 't2', 't3'], out
    assert text == 'bard there. But'

def test_trailing_zero_length_speech_is_restored():
    text, restored, out = run([w('and', 37.3, 37.5)], [w('and', 37.4, 37.5), w('uh', 37.5, 37.5), w('I', 38.0, 38.2), w('I', 38.2, 38.2)])
    assert text == 'and uh I I'

def test_interval_owned_by_the_ten_second_fallback_is_skipped():
    out, restored = coverage.restore_witnessed_words([w('a', 1.0, 1.2), w('b', 30.0, 30.2)], [w('x', 10.0, 10.5), w('y', 10.5, 11.0)], skip=[(int(1.2 * S), int(30 * S))])
    text = ' '.join((x.text for x in out))
    assert text == 'a b'

def test_system_live_only_invention_limit():
    text, restored, out = run([w('a', 1.0, 1.2), w('b', 9.0, 9.2)], [w('Oui.', 5.0, 5.3)])
    assert text == 'a Oui. b'
