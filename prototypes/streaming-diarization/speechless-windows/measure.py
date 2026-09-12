"""Opt-in PCM/VAD probe: .venv/bin/python prototypes/streaming-diarization/speechless-windows/measure.py --speech /path/to/human-speech.wav
Question: does a conservative VAD classify silence while retaining brief speech in a 150s window?
Falsifier: embedded real speech classifies speechless. No decoder, service, or database calls.
"""
import argparse
import json
import time
import tempfile
import sys
import wave
from pathlib import Path
import webrtcvad

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app.windowed_transcription import _speechless_window, WindowPlan


def measure(pcm):
    vad = webrtcvad.Vad(0)
    voiced = 0
    frames = 0
    for start in range(0, len(pcm), 640):
        frame = pcm[start:start+640]
        frames += 1
        if vad.is_speech(frame.ljust(640, b'\0'), 16000):
            voiced += len(frame) // 2
    return {'samples': len(pcm)//2, 'frames': frames, 'voiced_samples': voiced,
            'voiced_fraction': voiced / (len(pcm)//2), 'speechless': voiced / (len(pcm)//2) < .0001}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--speech', type=Path, required=True)
    args = parser.parse_args()
    with wave.open(str(args.speech), 'rb') as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        speech = w.readframes(w.getnframes())
    cases = {'silence_150s': bytes(150*32000), 'real_speech': speech,
             'speech_then_long_silence': speech + bytes(max(0, 150*32000-len(speech))),
             'brief_speech_in_silence': bytes(70*32000) + speech[:32000] + bytes(79*32000),
             'silence_partial_frame': bytes(32001*2)}
    output = {'source': 'local-speech-fixture', 'vad_mode': 0, 'frame_ms': 20, 'threshold': .0001}
    for name, pcm in cases.items():
        start = time.monotonic(); output[name] = {**measure(pcm), 'seconds': time.monotonic()-start}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'window.wav'
            with wave.open(str(path), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
            duration = len(pcm)/32000
            decision = _speechless_window(path, WindowPlan(0, 0, duration, 0, duration))
        output[name]['production_speechless'] = decision is not None
        assert output[name]['speechless'] == output[name]['production_speechless']
    print(json.dumps(output, indent=2))
