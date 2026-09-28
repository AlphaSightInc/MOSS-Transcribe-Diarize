from types import SimpleNamespace

from moss_transcribe_diarize.app.gemini_provider import GeminiWord
from moss_transcribe_diarize.app.gemini_final_policy import FinalWordPolicy, WebRtcWordGate

S = 16000


def w(label, start, end, text=None):
    return GeminiWord(text or label, label, int(start*S), int(end*S))


class FakeEncoder:
    def __init__(self):
        self.intervals = {}
        self.spec = SimpleNamespace(embedding_dimension=2)

    def embed_intervals(self, path, intervals):
        self.intervals.update({start: end for start, end in intervals})
        # A1/A2 are one voice; B is similar but separated by the converse-turn veto.
        return [[1, 0] if start < 3 or start > 8 else [0, 1] for start, _ in intervals]


def test_final_policy_merges_cosine_pairs_but_vetoes_converse_turns():
    encoder = FakeEncoder()
    policy = FinalWordPolicy(encoder)
    words = [w('A', 0, 2.5), w('B', 3, 5.5), w('A', 6, 8.5),
             w('C', 12, 14.5)]
    mapped = policy.remap(words, bytes(16*S*2))
    assert [x.speaker for x in mapped] == ['A', 'B', 'A', 'A']
    assert len(encoder.intervals) == 4


def test_final_policy_continuous_spans_and_threshold():
    class Encoder:
        def __init__(self): self.seen = []
        def embed_intervals(self, path, intervals):
            self.seen.extend(intervals)
            return [[1, 0] for _ in intervals]
    encoder = Encoder()
    words = [w('X', 0, 1), w('X', 1.5, 2.7), w('X', 4, 5),
             w('X', 5.8, 7), w('X', 9, 9.5)]
    assert FinalWordPolicy._intervals(words, "X") == [(0, 2.7)]


def test_webrtc_gate_keeps_words_with_padded_voiced_frame_and_drops_silence():
    class Vad:
        def is_speech(self, frame, rate):
            assert rate == S and len(frame) == 320
            return frame[0] == 1
    pcm = bytearray(3*S*2)
    pcm[100*320] = 1  # frame 1.00 s
    gate = WebRtcWordGate(vad=Vad())
    kept = gate.filter(bytes(pcm), [w('A', .8, .82), w('A', 2, 2.1)])
    assert [x.start_sample for x in kept] == [int(.8*S)]
