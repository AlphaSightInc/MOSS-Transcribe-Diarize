from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry
from moss_transcribe_diarize.app.gemini_provider import GeminiWord


S = 16_000


def test_c4_overlap_default_is_point_three_seconds():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    assert registry.min_overlap_samples == round(.3*S)


def word(label, start, end):
    return GeminiWord("word", label, round(start*S), round(end*S))


def test_short_unmatched_label_stays_unattributed_until_two_seconds_then_overlap_keeps_id():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    short, _ = registry.observe_window(0, (word("A", 0, 1.5),))
    born, _ = registry.observe_window(0, (word("A", 0, 2.1),))
    renamed, _ = registry.observe_window(1, (word("B", 1, 3),))
    assert short == {"A": None}
    assert born == {"A": "speaker-0001"}
    assert renamed == {"B": "speaker-0001"}


def test_returning_voice_links_by_wespeaker_when_timed_overlap_is_absent():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    first, _ = registry.observe_window(0, (word("A", 0, 2.1),),
                                       {"A": ((1.0, 0.0), 2.1)})
    returned, _ = registry.observe_window(10, (word("B", 10, 12.1),),
                                          {"B": ((.8, .6), 2.1)})
    assert first == {"A": "speaker-0001"}
    assert returned == {"B": "speaker-0001"}


def test_acoustically_matching_nonoverlapping_local_labels_share_one_birth():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    mapped, _ = registry.observe_window(0,
        (word("X", 0, 2.1), word("Y", 2.2, 4.3)),
        {"X": ((1.0, 0.0), 2.1), "Y": ((.8, .6), 2.1)})
    assert mapped == {"X": "speaker-0001", "Y": "speaker-0001"}


def test_simultaneous_local_voices_do_not_merge_even_with_similar_vectors():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    mapped, _ = registry.observe_window(0,
        (word("X", 0, 2.1), word("Y", 0, 2.1)),
        {"X": ((1.0, 0.0), 2.1), "Y": ((.8, .6), 2.1)})
    assert mapped == {"X": "speaker-0001", "Y": "speaker-0002"}


def test_overlap_assignment_is_one_to_one_across_local_labels():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    registry.observe_window(0, (word("A", 0, 5),))
    mapped, _ = registry.observe_window(0,
        (word("X", 0, 2), word("Y", 2, 4.1)))
    assert mapped == {"X": "speaker-0002", "Y": "speaker-0001"}


def test_full_window_tail_is_overlap_evidence_for_c4():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    registry.observe_window(0, (word("A", 0, 2.1),),
                            committed_through_sample=S)
    mapped, _ = registry.observe_window(1, (word("B", 1.2, 3.3),))
    assert mapped == {"B": "speaker-0001"}


def test_fingerprint_veto_reassigns_whole_window_when_overlap_contests_voice():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2)
    registry.observe_window(0, (word("A", 0, 3), word("B", 3, 6)),
                            {"A": ((1., 0.), 3), "B": ((0., 1.), 3)})
    mapped, _ = registry.observe_window(0,
        (word("X", 0, 3), word("Y", 3, 6)),
        {"X": ((0., 1.), 3), "Y": ((1., 0.), 3)})
    assert mapped == {"X": "speaker-0002", "Y": "speaker-0001"}
    assert registry.veto_fired == 1


def test_uncontested_and_vectorless_overlap_keep_original_assignment():
    registry = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                  birth_min_seconds=2, id_prefix="local")
    registry.observe_window(0, (word("A", 0, 3), word("B", 3, 6)),
                            {"A": ((1., 0.), 3), "B": ((0., 1.), 3)})
    mapped, _ = registry.observe_window(0,
        (word("X", 0, 3), word("Y", 3, 6)),
        {"X": ((1., 0.), 3)})
    assert mapped == {"X": "local-0001", "Y": "local-0002"}
    assert registry.veto_fired == 0
