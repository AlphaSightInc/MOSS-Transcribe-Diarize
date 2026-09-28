from moss_transcribe_diarize.app.gemini_provider import GeminiWord, repair_word_timestamps

S = 16_000


def word(text, start, end, speaker="spk:0"):
    return GeminiWord(text, speaker, round(start*S), round(end*S))


def test_isolated_offset_and_long_duration_repair_without_reordering_words():
    original = (word("before", 1, 1.2), word("duration", 1.5, 100),
                word("middle", 2, 2.2), word("island", 100, 101),
                word("after", 3, 3.2))
    fixed, changed = repair_word_timestamps(original, 120*S)
    assert changed == 2
    assert [(w.text, w.speaker) for w in fixed] == [(w.text, w.speaker) for w in original]
    assert fixed[1].start_sample == original[1].start_sample
    assert fixed[1].end_sample == 2*S
    assert 2*S <= fixed[3].start_sample <= 3*S
    assert fixed[3].end_sample <= 3*S
    assert fixed[0] == original[0] and fixed[2] == original[2] and fixed[4] == original[4]


def test_short_backward_jump_run_shifts_between_anchors_but_small_jump_remains():
    original = (word("anchor", 1, 1.2), word("run1", 100, 100.2),
                word("run2", 100.4, 100.6), word("return", 2, 2.2),
                word("small", 1.5, 1.6))
    fixed, changed = repair_word_timestamps(original, 120*S)
    assert changed == 2
    assert [w.text for w in fixed] == [w.text for w in original]
    assert 1*S <= fixed[1].start_sample <= 2*S
    assert fixed[1].start_sample < fixed[2].start_sample < 3*S
    assert fixed[4] == original[4]
