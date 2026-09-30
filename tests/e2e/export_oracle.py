"""Compare downloaded words, labels and represented times with the selected API meeting.

The product exports Markdown and plain text only (#11); both expose start seconds only. Do not claim
precision or fields a format does not carry. No renderer imports or generated expected text.
"""
import math
import re
from moss_transcribe_diarize.lane_word_oracle import words

UNKNOWN_SPEAKER_IDS = frozenset({'S00', 'UNKNOWN'})
NEEDS_REVIEW_NOTICE = 'Needs review: one or more speaker assignments remain uncertain or processing ended partially.'
MARKDOWN_NEEDS_REVIEW_NOTICE = '> **Needs review:** One or more speaker assignments remain uncertain or processing ended partially.'


def clock(value):
    hours,minutes,seconds=value.split(':')
    return int(hours)*3600+int(minutes)*60+int(seconds)


def expected_rows(meeting):
    segments=(meeting.get('transcript') or {}).get('segments', [])
    defaults=sorted({s['speaker'] for s in segments if re.fullmatch(r'SPEAKER_\d+',s['speaker'])},
                    key=lambda v:int(v.split('_')[-1]))
    labels={s:f'SPEAKER_{i+1:02d}' for i,s in enumerate(defaults)}
    rows=[]
    for segment in segments:
        if not segment['text'].strip(): continue
        identity=segment.get('speaker_entity_id') or segment['speaker']
        label=labels.get(segment['speaker'], 'Preview' if segment['speaker']=='UNKNOWN' else segment['speaker'])
        row=dict(start=segment['start'],end=segment['end'],label=label,identity=identity,
                 tokens=words(segment['text']),lane=segment.get('source_lane'),
                 segment_ids=[segment['id']] if isinstance(segment.get('id'),str) and segment['id'] else [])
        if (rows and identity not in UNKNOWN_SPEAKER_IDS
                and all(rows[-1][key]==row[key] for key in ('identity','label','lane'))):
            rows[-1]['tokens'].extend(row['tokens']); rows[-1]['segment_ids'].extend(row['segment_ids'])
            rows[-1]['end']=row['end']
        else: rows.append(row)
    return rows


def downloaded_export(fmt,text):
    if fmt not in ('txt','md'): raise ValueError('Unsupported export format')
    notice=MARKDOWN_NEEDS_REVIEW_NOTICE if fmt=='md' else NEEDS_REVIEW_NOTICE
    marker=notice+'\n\n'
    review=text.startswith(marker)
    if review: text=text[len(marker):]
    pattern = r'^## \[(\d{2}:\d{2}:\d{2})\] (.+)\n\n' if fmt=='md' else r'^\[(\d{2}:\d{2}:\d{2})\] (.+):\n'
    matches=list(re.finditer(pattern,text,re.M))
    if not matches or text[:matches[0].start()].strip(): raise ValueError('Unexpected export header')
    rows=[dict(start=clock(m[1]),label=m[2],tokens=words(text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)])) for i,m in enumerate(matches)]
    return rows, review


def compare_export(fmt,text,meeting):
    expected=expected_rows(meeting)
    try: actual,review=downloaded_export(fmt,text)
    except (ValueError,KeyError,TypeError):
        return dict(ok=False,expected_turns=len(expected),parse_error=True)
    same_count=len(actual)==len(expected) and bool(expected)
    # Round-3 Q6: export files carry the transcript only, never a review notice, whatever the
    # meeting's needs_review flag says. The parser still detects a notice so one that returns fails.
    checks=dict(words=same_count,labels=same_count,timing=same_count,review=review is False)
    for a,b in zip(actual,expected):
        checks['words'] &= a['tokens']==b['tokens']
        checks['labels'] &= a['label']==b['label']
        checks['timing'] &= a['start']==math.floor(b['start'])
    return dict(ok=all(checks.values()),expected_turns=len(expected),downloaded_turns=len(actual),**checks)
