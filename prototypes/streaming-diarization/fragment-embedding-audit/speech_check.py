"""Sensitivity analysis: retain only cuts classified entirely as speech by local VAD."""
import json
from pathlib import Path
import wave
import webrtcvad
from probe import REPO, save, distribution, replay, cosine_similarity

out = Path(__file__).parent
source = REPO / 'evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav'
with wave.open(str(source)) as wav:
    pcm = wav.readframes(wav.getnframes())
vad = webrtcvad.Vad(1)
flags = [vad.is_speech(pcm[i:i+320], 16000) for i in range(0, len(pcm)-319, 320)]
result = dict(method='WebRTC VAD mode 1, 10 ms frames, continuous source scan; '
              'matches local manifest speech settings, not verified host configuration. '
              'Retain only windows with every frame classified as speech. VAD is not human ground truth; '
              'same cached embeddings, no silence splicing, no new model calls.', groups={})
for seconds in (1.0, 1.5, 2.0, 10.0):
    records = json.loads((out / f'vectors-{seconds:g}s.json').read_text())
    selected = []
    activity = []
    for record in records:
        window = flags[round(record['start']*100):round(record['end']*100)]
        activity.append(dict(start=record['start'], speech_seconds=sum(window)/100))
        if all(window):
            selected.append(record)
    pairs = [dict(left=a['start'], right=b['start'], score=cosine_similarity(a['vector'], b['vector']))
             for i,a in enumerate(selected) for b in selected[i+1:]]
    values = [p['score'] for p in pairs]
    failed = sum(v < .35 for v in values)
    group = dict(activity=activity, windows=len(selected), pair_count=len(pairs),
                 below_035=failed, fraction_below_035=failed/len(pairs) if pairs else None,
                 distribution=distribution(values) if values else None,
                 pairs=pairs, sequential=replay(selected, seconds) if selected else None)
    result['groups'][str(seconds)] = group
    save(out / 'speech-results.json', result)
    print(seconds, 'windows',len(selected),'pairs',len(pairs),'failed',failed,group['distribution'])
    if selected:
        print('identities',group['sequential']['identities'], 'abstentions',
              sum(t['status']!='prepared' for t in group['sequential']['trace']))
