"""Compare downloaded words, labels and represented times with the selected API meeting.

Text/Markdown expose start seconds only; subtitle formats expose milliseconds;
JSON additionally exposes end times, canonical identity and optional source lane. Do not claim precision
or fields a format does not carry. No renderer imports or generated expected text.
"""
import html
import json
import math
import re
from moss_transcribe_diarize.lane_word_oracle import words


def clock(value):
    hours,minutes,seconds=value.replace(',', '.').split(':')
    return int(hours)*3600+int(minutes)*60+float(seconds)


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
                 tokens=words(segment['text']),lane=segment.get('source_lane'))
        if rows and all(rows[-1][key]==row[key] for key in ('identity','label','lane')):
            rows[-1]['tokens'].extend(row['tokens']); rows[-1]['end']=row['end']
        else: rows.append(row)
    return rows


def downloaded_rows(fmt,text):
    if fmt=='json':
        body=json.loads(text)
        return [dict(start=r['start'],end=r['end'],label=r['speaker_label'],identity=r['speaker_entity_id'],
                     tokens=words(r['text']),lane=r.get('source_lane')) for r in body['turns']]
    if fmt in ('txt','md'):
        pattern = r'^## \[(\d{2}:\d{2}:\d{2})\] (.+)\n\n' if fmt=='md' else r'^\[(\d{2}:\d{2}:\d{2})\] (.+):\n'
        matches=list(re.finditer(pattern,text,re.M))
        if not matches or text[:matches[0].start()].strip(): raise ValueError('Unexpected export header')
        return [dict(start=clock(m[1]),label=m[2],tokens=words(text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)])) for i,m in enumerate(matches)]
    if fmt=='vtt':
        if not text.startswith('WEBVTT\n\n'): raise ValueError('Missing WEBVTT')
        text=text[len('WEBVTT\n\n'):]
    result=[]
    for cue in re.split(r'\n\s*\n',text.strip()):
        match=re.fullmatch(r'\d+\n(\d{2}:\d{2}:\d{2}[.,]\d{3}) --> (\d{2}:\d{2}:\d{2}[.,]\d{3})\n([^\n]+?): (.*)',cue,re.S)
        if not match: raise ValueError('Malformed cue')
        result.append(dict(start=clock(match[1]),end=clock(match[2]),label=html.unescape(match[3]),tokens=words(html.unescape(match[4]))))
    return result


def compare_export(fmt,text,meeting):
    expected=expected_rows(meeting)
    try: actual=downloaded_rows(fmt,text)
    except (ValueError,KeyError,TypeError):
        return dict(ok=False,expected_turns=len(expected),parse_error=True)
    same_count=len(actual)==len(expected) and bool(expected)
    checks=dict(words=same_count,labels=same_count,timing=same_count,identity=same_count)
    if fmt=='json': checks['lane']=same_count
    for a,b in zip(actual,expected):
        checks['words'] &= a['tokens']==b['tokens']
        checks['labels'] &= a['label']==b['label']
        start=math.floor(b['start']) if fmt in ('md','txt') else b['start']
        end=b['end']
        if fmt in ('srt','vtt'):
            start=math.floor(start*1000+0.5)/1000
            end=max(start+0.001,math.floor(end*1000+0.5)/1000)
        checks['timing'] &= math.isclose(a['start'],start,abs_tol=1e-9)
        if 'end' in a: checks['timing'] &= math.isclose(a['end'],end,abs_tol=1e-9)
        if fmt=='json':
            checks['identity'] &= a['identity']==b['identity']
            checks['lane'] &= a['lane']==b['lane']
    return dict(ok=all(checks.values()),expected_turns=len(expected),downloaded_turns=len(actual),**checks)
