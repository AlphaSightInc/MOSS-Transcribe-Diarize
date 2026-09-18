"""WP16 throwaway real-media preparation; no audio committed."""
import argparse, json, subprocess, wave
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--scratch',type=Path,default=Path('.wp16runtime'))
parser.add_argument('--out',type=Path,default=Path('evidence/mvpfix/wp16'))
args=parser.parse_args()
root=args.scratch/'media'; root.mkdir(parents=True,exist_ok=True)
args.out.mkdir(parents=True,exist_ok=True)
corpus=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')
names=['interview_bill_ackman_60s','interview_keyu_jin_60s']
refs=[]; boundaries=[]
with wave.open(str(root/'long.wav'),'wb') as out:
    out.setparams((1,2,16000,0,'NONE','not compressed'))
    for i in range(30):
        name=names[i%2]
        with wave.open(str(corpus/name/'audio.wav'),'rb') as src:
            assert src.getframerate()==16000 and src.getnchannels()==1 and src.getsampwidth()==2
            frames=src.readframes(960000); assert len(frames)==1920000
            out.writeframes(frames)
        boundaries.append(dict(index=i,source=name,start=i*60,end=(i+1)*60))
        for line in (corpus/name/'reference.jsonl').read_text().splitlines():
            row=json.loads(line); row.update(start=row['start']+i*60,end=row['end']+i*60,source=name); refs.append(row)
(root/'reference.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in refs))
(args.out/'composite-boundaries.json').write_text(json.dumps(dict(duration=1800,distinct_clips=2,reference_speakers=sorted({r['speaker'] for r in refs}),boundaries=boundaries),indent=2)+'\n')
def ff(*a): subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',*map(str,a)],check=True)
ff('-i',root/'long.wav','-c:a','libmp3lame','-b:a','64k',root/'long.mp3')
ff('-i',root/'long.wav','-c:a','aac','-b:a','64k',root/'long.m4a')
ff('-i',root/'long.wav','-t','2',root/'two.wav')
ff('-i',root/'long.wav','-t','12','-c:a','libmp3lame',root/'short.mp3')
(root/'truncated.mp3').write_bytes((root/'short.mp3').read_bytes()[:int((root/'short.mp3').stat().st_size*.6)])
(root/'empty.wav').touch(); (root/'text.mp3').write_text('WP16 deliberately invalid media')
with wave.open(str(root/'silence.wav'),'wb') as out:
    out.setparams((1,2,16000,0,'NONE','not compressed')); out.writeframes(bytes(16000*2*10))
(root/'index.html').write_text('<html><body>WP16 non-media source</body></html>')
print(json.dumps(dict(files={p.name:p.stat().st_size for p in root.iterdir()},boundaries=len(boundaries),reference_segments=len(refs))))
