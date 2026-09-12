"""Evidence-only A2 bench; production identity, local ONNX, no policy mutation."""
from __future__ import annotations
import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import live_identity_accuracy as I
from moss_transcribe_diarize.app.speaker_identity import WeSpeakerResNet152LmAdapter
from moss_transcribe_diarize.app.live_identity_sweep import SWEEP_INTERVAL_SECONDS


def read_truth(path):
    speakers, rows = {}, []
    previous = 0.
    for line in path.read_text().splitlines():
        x = json.loads(line)
        speaker = speakers.setdefault(x['speaker'], len(speakers))
        start, end = max(float(x['start']), previous), float(x['end'])
        if end > start:
            rows.append((start, end, speaker))
            previous = end
    return np.asarray(rows), list(speakers)


def embed(name, truth, audio, adapter, output, reuse):
    cache = output / f'{name}.npz'
    if reuse and cache.exists():
        with np.load(cache) as z:
            assert np.array_equal(truth, z['truth'])
            meeting = I.Meeting(name, len(set(truth[:, 2])), truth, z['rows'], z['vectors'])
    else:
        grouped = {}
        for p in I.plan_spans(truth):
            grouped.setdefault((p.span, p.true_speaker), []).append(p)
        rows, vectors = [], []
        for (span, speaker), pieces in sorted(grouped.items()):
            selected = [p for p in pieces if p.duration >= .5]
            if selected:
                vectors.append(adapter.embed(audio, [(p.start, p.end) for p in selected]))
            rows.append((span, speaker, min(p.start for p in pieces), max(p.end for p in pieces),
                         sum(p.duration for p in selected), bool(selected)))
        meeting = I.Meeting(name, len(set(truth[:, 2])), truth, np.asarray(rows), np.asarray(vectors, dtype=np.float32))
        np.savez_compressed(cache, truth=truth, rows=meeting.rows, vectors=meeting.vectors)
    I.assert_fixture_matches_production(meeting)
    return meeting


def ownership(labels, truths, durations):
    result = {}
    for label in sorted(set(labels) - {None}):
        weights = {int(t): sum(d for l, s, d in zip(labels, truths, durations) if l == label and s == t)
                   for t in sorted(set(truths))}
        result[label] = max(weights, key=weights.get)
    return result


def metrics(meeting, trace):
    units = I.evidence_units(meeting)
    durations = [sum(p.duration for p in u) for u in units]
    truths = [u[0].true_speaker for u in units]
    ends = [max(p.end for p in u) for u in units]
    live = [x for x in trace if x['event'] == 'commit'][-1]['live_labels']
    final = trace[-1]['labels']
    result = {'all_speech_seconds': sum(durations), 'units': len(units)}
    for phase, labels in [('live', live), ('final', final)]:
        owner = ownership(labels, truths, durations)
        counts = [sum(t == s for t in owner.values()) for s in sorted(set(truths))]
        result[phase] = dict(false_splits=sum(max(0, n-1) for n in counts),
                             missed_people=sum(n == 0 for n in counts), ids_per_person=counts,
                             unnamed_seconds=sum(d for l, d in zip(labels, durations) if l is None),
                             misassigned_seconds=sum(d for l, t, d in zip(labels, truths, durations)
                                                     if l is not None and owner[l] != t))
    owner = ownership(final, truths, durations)
    delays, revision_delays, unresolved, units_out = [], [], 0, []
    for i, (t, end) in enumerate(zip(truths, ends)):
        events = [e for e in trace if e['time'] >= end - 1e-6]
        revision_delays.extend(max(0., curr['time'] - end) for prev, curr in zip(events, events[1:])
                               if prev['labels'][i] != curr['labels'][i])
        correct = [e['labels'][i] is not None and owner.get(e['labels'][i]) == t for e in events]
        delay = None
        if not correct[-1]:
            unresolved += 1
        elif not all(correct):
            last_bad = max(j for j, ok in enumerate(correct) if not ok)
            delay = max(0., events[last_bad + 1]['time'] - end)
            delays.append(delay)
        units_out.append(dict(unit=i, true_speaker=t, end=end, speech_seconds=durations[i],
                              live_label=live[i], final_label=final[i], correction_delay_seconds=delay,
                              final_correct=correct[-1]))
    result['correction'] = dict(corrected_units=len(delays), unresolved_units=unresolved,
                                 delays_seconds=delays, label_revision_delays_seconds=revision_delays, p50_seconds=float(np.median(delays)) if delays else None,
                                 max_seconds=max(delays) if delays else None)
    result['units_detail'] = units_out
    return result


def check_metric_examples():
    """Known state history catches counting and audio-clock errors before measuring."""
    truth = np.asarray([[0, 1, 0], [2, 3, 0], [4, 5, 1]])
    rows = np.asarray([[0, 0, 0, 1, 1, 1], [1, 0, 2, 3, 1, 1], [2, 1, 4, 5, 1, 1]])
    trace = [dict(event='commit', time=1, labels=['a', None, None], live_labels=['a', None, None]),
             dict(event='commit', time=3, labels=['a', 'b', None], live_labels=['a', 'b', None]),
             dict(event='commit', time=5, labels=['a', 'b', None], live_labels=['a', 'b', None]),
             dict(event='sweep', time=10, labels=['a', 'a', 'c'])]
    result = metrics(I.Meeting('metric_examples', 2, truth, rows, np.zeros((3, 256))), trace)
    assert (result['live']['false_splits'], result['final']['false_splits']) == (1, 0)
    assert (result['live']['missed_people'], result['final']['missed_people']) == (1, 0)
    assert (result['live']['unnamed_seconds'], result['final']['unnamed_seconds']) == (1, 0)
    assert result['correction']['delays_seconds'] == [7., 5.]
    assert result['correction']['label_revision_delays_seconds'] == [7., 5.]
    trace[-1]['labels'] = ['a', 'a', None]
    result = metrics(I.Meeting('unresolved_example', 2, truth, rows, np.zeros((3, 256))), trace)
    assert result['correction']['unresolved_units'] == 1
    assert result['units_detail'][2]['correction_delay_seconds'] is None


def main():
    check_metric_examples()
    p = argparse.ArgumentParser()
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--intro-wav', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path(__file__).parent / 'results')
    p.add_argument('--reuse', action='store_true')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    adapter = WeSpeakerResNet152LmAdapter(a.data_root / 'voxceleb_resnet152_LM.onnx')
    adapter.preflight()
    manifest = json.loads((ROOT / 'tests/fixtures/live_identity_real_corpus.json').read_text())
    cases = []
    for case in manifest['cases']:
        path = a.data_root / 'real' / case['path']
        truth, speakers = read_truth(path / 'reference.jsonl')
        cases.append((case['name'], truth, path / 'audio.wav', speakers, 'nine_clip', None))
    activity = json.loads((ROOT / 'prototypes/streaming-diarization/fragment-embedding-audit/speech-results.json').read_text())
    activity = activity['groups']['1.0']['activity']
    starts = [float(x['start']) for x in activity if x['speech_seconds'] == 1.0]
    intro, rate = sf.read(a.intro_wav, dtype='float32')
    assert rate == 16000 and intro.ndim == 1
    bill_path = a.data_root / 'real/benchmark_diarization_1min/samples/lex_bill_ackman/audio.wav'
    bill, bill_rate = sf.read(bill_path, dtype='float32')
    assert bill_rate == rate and bill.ndim == 1
    for name, seeded, brief, returns in [('lex_short_only',False,0,False),
            ('lex_seeded',True,0,False), ('unseeded_brief_1s',False,1.,False),
            ('unseeded_brief_1p5s',False,1.5,False), ('brief_1s',True,1.,False),
            ('brief_1p5s',True,1.5,False), ('brief_1s_return',True,1.,True)]:
        # Remove seed-covered units, preserving chronological source observations.
        observations = [('Lex Fridman', 1., 3.)] if seeded else []
        observations += [('Lex Fridman', s, s+1.) for s in starts if not seeded or s >= 3.]
        if brief:
            observations.insert(5, ('Bill Ackman', 1., 1.+brief))
        if returns:
            observations.insert(20, ('Bill Ackman', 10., 12.))
        speakers, truth, pcm, plan, cursor = [], [], [], [], 0
        for speaker, start, end in observations:
            if speaker not in speakers:
                speakers.append(speaker)
            source = intro if speaker == 'Lex Fridman' else bill
            chunk = source[round(start*rate):round(end*rate)]
            truth.append((cursor/rate, (cursor+len(chunk))/rate, speakers.index(speaker)))
            plan.append(dict(speaker=speaker, source=str(a.intro_wav if speaker == 'Lex Fridman' else bill_path),
                             source_start=start, source_end=end, meeting_start=cursor/rate))
            pcm.extend([chunk, np.zeros(9600, dtype=np.float32)])
            cursor += len(chunk)+9600
        audio = a.output / f'{name}.wav'
        if not a.reuse or not audio.exists():
            sf.write(audio, np.concatenate(pcm), rate, subtype='PCM_16')
        cases.append((name, np.asarray(truth), audio, speakers, 'controlled', plan))
    output = dict(code_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  asset=str(a.data_root / 'voxceleb_resnet152_LM.onnx'), manifest=manifest, sweep_seconds=SWEEP_INTERVAL_SECONDS, cases={})
    for name, truth, audio, speakers, group, plan in cases:
        print(f'EMBED {name}', flush=True)
        meeting = embed(name, truth, audio, adapter, a.output, a.reuse)
        arms = {}
        for floor in (1.,1.5,2.):
            trace = []
            result = I.replay(meeting, policy='album', birth_min_seconds=floor,
                              sweep_interval=SWEEP_INTERVAL_SECONDS, trace=trace)
            # Observer must not change any historical acceptance metric.
            assert result == I.replay(meeting, policy='album', birth_min_seconds=floor,
                                       sweep_interval=SWEEP_INTERVAL_SECONDS)
            arms[str(floor)] = dict(regression=dataclasses.asdict(result), metrics=metrics(meeting, trace), trace=trace)
            print(name, floor, result.accuracy, json.dumps({k:v for k,v in arms[str(floor)]['metrics'].items()
                                                          if k not in ('units_detail',)}), flush=True)
        output['cases'][name] = dict(group=group, speakers=speakers, source_plan=plan, arms=arms)
        (a.output / 'results.json').write_text(json.dumps(output, separators=(',', ':'))+'\n')

if __name__ == '__main__':
    main()
