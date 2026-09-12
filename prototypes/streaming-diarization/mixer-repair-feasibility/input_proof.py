"""Content-free PCM custody check; no decoder, database or network.
Run from repository root: .venv/bin/python prototypes/streaming-diarization/mixer-repair-feasibility/input_proof.py
"""
import json
import sys
import wave
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session

class Collector:
    def __init__(self): self.frames = []
    def snapshot(self, _):
        return SimpleNamespace(session=SimpleNamespace(next_frame_sequence=len(self.frames), version=len(self.frames)))
    def accept_frame(self, _, frame, **kwargs):
        self.frames.append(frame)
        return SimpleNamespace(queued_item_ids=())

rows = []
for path in sorted((ROOT / 'evidence/live-policy-sweep-20260825/corpus').glob('*/audio.wav')):
    with wave.open(str(path)) as audio:
        assert audio.getframerate() == 16000 and audio.getnchannels() == 1
        raw = audio.readframes(audio.getnframes())
    source = LiveV2Session(max_retained_samples=960000)
    mixer, output = LiveCompatibilityMixer(max_output_samples=8000), Collector()
    for sequence, start in enumerate(range(0, len(raw), 16000)):
        chunk = raw[start:start + 16000]
        begin, end = start // 2 * 62500, (start + len(chunk)) // 2 * 62500
        for lane in LiveLane:
            silent = lane == LiveLane.MICROPHONE
            source.accept(LiveV2Frame(lane, sequence, begin, 0, silent, False, 16000,
                len(chunk) // 2, bytes(len(chunk)) if silent else chunk, capture_end_timestamp_ns=end))
            while mixer.admit_available('proof', source, output) is not None: pass
    before_stop = sum(frame.sample_count for frame in output.frames)
    assert mixer.admit_available('proof', source, output, final=True) is None
    analysis = b''.join(frame.analysis_pcm if frame.analysis_pcm is not None else frame.pcm for frame in output.frames)
    decoder = b''.join(frame.pcm for frame in output.frames)
    a = np.frombuffer(raw, dtype='<i2').astype(float)
    expected = np.trunc(a / 32768 * 10 ** (-6 / 20) * 32767).astype('<i2').tobytes()
    row = dict(case_id=path.parent.name, samples=len(raw)//2, pre_stop_accepted_samples=before_stop,
        analysis_matches_source=analysis == raw, decoder_matches_previous_headroom=decoder == expected,
        source_rms=float(np.sqrt(np.mean(a*a))),
        decoder_rms=float(np.sqrt(np.mean(np.frombuffer(decoder, dtype='<i2').astype(float)**2))),
        largest_analysis_frame_bytes=max(len(frame.analysis_pcm or b'') for frame in output.frames))
    assert row['analysis_matches_source'] and row['decoder_matches_previous_headroom']
    assert before_stop == len(raw)//2
    rows.append(row)
print(json.dumps(rows, indent=2))
