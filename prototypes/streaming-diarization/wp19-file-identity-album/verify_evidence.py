"""Offline checks: retained labels versus references and same-input legacy control.
Detect wrong denominators, per-window label remapping, text/time changes and mismatched
retained decoder inputs. No decoder/encoder/GPU calls. Fail rather than waive mismatch.
"""
import importlib.util
import json
from pathlib import Path
from moss_transcribe_diarize.app.speaker_identity import IdentityResolver
from moss_transcribe_diarize.app.windowed_transcription import plan_windows, _stitch_segments
from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

module_path=Path(__file__).with_name('accept_real.py')
spec=importlib.util.spec_from_file_location('wp19_acceptance',module_path)
accept=importlib.util.module_from_spec(spec); spec.loader.exec_module(accept)
rows=[]
for minutes in (6,30):
    retained=json.loads(Path(f'evidence/mvpfix/wp19/accept-real-{minutes}.json').read_text())
    folder=Path(f'.wp19runtime/real-{minutes}')
    segments=[TranscriptSegment(**s) for s in json.loads((folder/'segments.json').read_text())]
    score=accept.score(segments,minutes)
    for field,value in score.items(): assert value==retained[field],field
    windows=plan_windows(minutes*60)
    groups=[parse_transcript(json.loads((folder/f'decode-{w.index}.json').read_text())['text']) for w in windows]
    legacy=IdentityResolver().resolve(windows,groups,window_audio_paths=[folder/f'window-{w.index}.wav' for w in windows])
    stitched=_stitch_segments(windows,legacy.relabeled_results)
    assert [(s.start,s.end,s.text) for s in stitched]==[(s.start,s.end,s.text) for s in segments]
    assert retained['identities']==retained['truth_voices']==3
    assert retained['text_time_unchanged'] and retained['unattributed_segments']==0
    rows.append(dict(minutes=minutes,windows=len(windows),legacy_identities=len({s.speaker for s in stitched}),album_identities=score['identities'],segments=score['segments'],correct_segments=score['correct_segments'],duration_accuracy=score['duration_accuracy'],retained_rows_exact=True,text_time_exact=True))
assert sum(len(json.loads(Path(f'evidence/mvpfix/wp19/accept-real-{m}.json').read_text())['decodes']) for m in (6,30))==18
lease=json.loads(Path('evidence/mvpfix/wp19/lease-20.json').read_text())
assert len(lease)==20 and all(r['returncode']==0 for r in lease)
print(json.dumps(dict(cases=rows,lease_passes=20,decoder_requests=18),indent=2))
