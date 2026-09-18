"""PROTOTYPE: exact digital zero is sufficient to skip File decoding; any signal is not.
Falsifier: quiet/nonzero or empty input is classified as all-zero, or decoding still
runs for a nonempty all-zero mix. No loudness threshold; reuse settled PCM primitive.
"""
import json,time,wave
from pathlib import Path
from moss_transcribe_diarize.app.live_silence import is_digital_silence
root=Path('.wp16runtime/media')
for name,pcm in [('quiet.wav',b'\1\0'*160000),('last-signal.wav',bytes(319998)+b'\1\0')]:
 with wave.open(str(root/name),'wb') as out:
  out.setparams((1,2,16000,0,'NONE','not compressed')); out.writeframes(pcm)
def inspect(path):
 with wave.open(str(path),'rb') as audio:
  samples=audio.getnframes()
  if not samples: return False
  while pcm:=audio.readframes(16000):
   if not is_digital_silence(pcm): return False
  return True
rows=[]
for name,expected in [('silence.wav',True),('two.wav',False),('quiet.wav',False),('last-signal.wav',False),('long.wav',False)]:
 start=time.monotonic(); value=inspect(root/name)
 row=dict(case=name,all_zero=value,expected=expected,elapsed=time.monotonic()-start,passed=value==expected); rows.append(row); print(json.dumps(row))
assert all(row['passed'] for row in rows)
