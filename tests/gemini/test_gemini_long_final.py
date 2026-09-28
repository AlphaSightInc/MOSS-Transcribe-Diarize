from moss_transcribe_diarize.app.gemini_long_final import LongFinalStitcher
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, TerminalChunk

S = 16_000


def word(text, speaker, start, end):
    return GeminiWord(text, speaker, round(start*S), round(end*S))


class FakeEncoder:
    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = []

    def embed_intervals(self, path, intervals):
        self.calls.append(intervals)
        start = round(intervals[0][0], 1)
        return [self.vectors[start]]


def test_seam_overlap_rejected_when_both_voice_centroids_disagree():
    encoder = FakeEncoder({0.0: (1.0, 0.0), 3.0: (0.0, 1.0)})
    chunks = (TerminalChunk(0, 0, 4*S, 3*S, (word("before", "A", 0, 4),)),
              TerminalChunk(1, 3*S, 7*S, 7*S, (word("after", "X", 3, 6.5),)))
    fixed = LongFinalStitcher(encoder).stitch(chunks, bytes(7*32000))
    assert [w.text for w in fixed] == ["before", "after"]
    assert fixed[0].speaker != fixed[1].speaker
    assert len(encoder.calls) == 2


def test_aba_turn_motif_vetoes_global_cosine_union():
    encoder = FakeEncoder({0.0: (1.0, 0.0), 2.3: (.9, .435)})
    chunk = TerminalChunk(0, 0, 7*S, 7*S,
                          (word("a1", "A", 0, 2.2),
                           word("b", "B", 2.3, 4.5),
                           word("a2", "A", 4.6, 6.8)))
    fixed = LongFinalStitcher(encoder).stitch((chunk,), bytes(7*32000))
    assert [w.text for w in fixed] == ["a1", "b", "a2"]
    assert fixed[0].speaker == fixed[2].speaker != fixed[1].speaker


def test_positive_seam_links_when_short_local_label_has_no_centroid():
    encoder = FakeEncoder({0.0: (1.0, 0.0)})
    chunks = (TerminalChunk(0, 0, 4*S, 3*S, (word("before", "A", 0, 4),)),
              TerminalChunk(1, 3*S, 6*S, 6*S, (word("after", "X", 3.5, 4.5),)))
    fixed = LongFinalStitcher(encoder).stitch(chunks, bytes(6*32000))
    assert len(fixed) == 2
    assert fixed[0].speaker == fixed[1].speaker


def test_global_cosine_links_returning_voice_without_seam_cooccurrence():
    encoder = FakeEncoder({0.0: (1.0, 0.0), 4.0: (.8, .6)})
    chunks = (TerminalChunk(0, 0, 4*S, 3*S, (word("before", "A", 0, 2.5),)),
              TerminalChunk(1, 3*S, 7*S, 7*S, (word("after", "X", 4, 6.5),)))
    fixed = LongFinalStitcher(encoder).stitch(chunks, bytes(7*32000))
    assert len(fixed) == 2
    assert fixed[0].speaker == fixed[1].speaker
