"""Standing bench extension: fresh CPU embeddings, unchanged production profile rule."""
import json,sys,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder
from moss_transcribe_diarize.app.phase2_voiceprint_match import VoiceprintProfile,match_voiceprint
from moss_transcribe_diarize.app.phase2_speaker_identity import _eligible_evidence,VOICEPRINT_ENROLLMENT_SECONDS
ASSET=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx')
CORPUS=ROOT/'evidence/live-policy-sweep-20260825/corpus'
e=_OnnxWeSpeakerEmbedder(ASSET,device='cpu');e.load();start=time.monotonic()
vector=e.embed(CORPUS/'interview_adam_frank_180s/audio.wav',[(49,52)])
profile=VoiceprintProfile('adam','Adam','pinned-wespeaker',tuple(vector));rows=[]
for name,a,b,truth in [('interview_adam_frank_180s',61,64,'adam'),('interview_adam_frank_180s',83,86,'adam'),('interview_bill_ackman_60s',0,3,None),('interview_keyu_jin_60s',0,3,None)]:
    v=e.embed(CORPUS/name/'audio.wav',[(a,b)])
    o=SimpleNamespace(centroid=v,sample_seconds=b-a,provisional=False,embedder_id='pinned-wespeaker')
    result=match_voiceprint(o,[profile])
    rows.append(dict(case=name,start=a,end=b,expected=truth,observed=result.voiceprint_id if result else None))
floors=[]
for seconds in [1.99,2.0,3.0]:
    o=SimpleNamespace(centroid=vector,sample_seconds=seconds,provisional=False,embedder_id='pinned-wespeaker')
    floors.append(dict(seconds=seconds,eligible=_eligible_evidence(o) is not None))
report=dict(production_embedder=True,device='cpu',fresh_embeddings=5,profile_seconds=3,
    enrollment_floor=VOICEPRINT_ENROLLMENT_SECONDS,matching=rows,floors=floors,seconds=time.monotonic()-start)
print(json.dumps(report,indent=2));(ROOT/'evidence/mvpfix/wp7/cpu-results.json').write_text(json.dumps(report,indent=2)+'\n')
