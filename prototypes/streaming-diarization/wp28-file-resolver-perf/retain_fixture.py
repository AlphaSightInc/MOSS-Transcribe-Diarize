"""Retain timing/label inputs and exact serial oracle, replacing every word.
Run only against the unmodified baseline. Public audio stays outside git.
"""
from dataclasses import asdict
import json
from pathlib import Path
from moss_transcribe_diarize.app.windowed_transcription import plan_windows
from moss_transcribe_diarize.transcript_parser import parse_transcript

for minutes in (6,30):
    windows=plan_windows(minutes*60,window_seconds=150,stride_seconds=120)
    expected=json.loads(Path(f'.wp28runtime/baseline-{minutes}-result.json').read_text())
    groups=[]
    for w in windows:
        rows=[asdict(s) for s in parse_transcript(json.loads(Path(f'.wp28runtime/real-{minutes}/decode-{w.index}.json').read_text())['text'])]
        for i,row in enumerate(rows):
            placeholder=f'window-{w.index}-segment-{i}'
            row['text']=placeholder
            expected['relabeled_results'][w.index][i]['text']=placeholder
        groups.append(rows)
    fixture=dict(minutes=minutes,windows=[asdict(w) for w in windows],local_results=groups,expected=expected)
    Path(f'evidence/mvpfix/wp28/fixture-{minutes}.json').write_text(json.dumps(fixture,indent=2)+'\n')
