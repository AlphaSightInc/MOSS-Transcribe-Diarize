"""Create a /tmp-only, known-onset speech fixture; never modify the corpus."""
import argparse
import shutil
from pathlib import Path
import numpy as np
import soundfile as sf

p = argparse.ArgumentParser()
p.add_argument('corpus', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
source, rate = sf.read(a.corpus / 'audio.wav')
assert rate == 16000 and source.ndim == 1
# A one-second preflight tone connects both lanes; actual speech starts at exactly 4s.
audio = np.zeros(15 * rate)
audio[:rate] = .1 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)
audio[4 * rate:] = source[round(.84 * rate):round(.84 * rate) + 11 * rate]
a.output.mkdir(parents=True, exist_ok=True)
sf.write(a.output / 'audio.wav', audio, rate, subtype='PCM_16')
shutil.copyfile(a.corpus / 'reference.jsonl', a.output / 'reference.jsonl')
print('Known injected speech onset: 4.000 seconds. Tone/silence are not speech.')
