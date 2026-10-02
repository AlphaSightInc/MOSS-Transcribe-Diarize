"""A7 throwaway offline bench: frozen candidates; full state; no provider calls."""
import copy
import difflib
import importlib.util
from functools import lru_cache
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent/'a6'), str(HERE.parent/'a4'), str(HERE.parent/'f1')]
spec = importlib.util.spec_from_file_location('a6_bench', HERE.parent/'a6/run.py')
a6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a6)
rt, score, stream = a6.rt, a6.score, a6.stream
units, S = a6.units, a6.S
EV = Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A7'
NAMES = ('C0', 'C1', 'C3', 'C3G', 'C4', 'C4G', 'C3J', 'C4J')

# Cache pure scorer inputs; exactly the a6 calculation, avoiding eight duplicate baselines.
original_residue = a6.residue
@lru_cache(maxsize=8192)
def cached_residue(text, solid, bounded=False):
    return original_residue(text, list(solid), bounded)
a6.residue = lambda text, solid, bounded=False: cached_residue(text, tuple(solid), bounded)


def emit(name, value):
    print(json.dumps(dict(kind=name, state=value), ensure_ascii=False), flush=True)


def save(name, value):
    (EV/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def source_tail(solid, lane, joined=False):
    rows = [(i, r) for i, r in enumerate(solid) if r[3] == lane]
    if not rows:
        return [], None
    if joined:
        text = ' '.join(r[2] for _, r in sorted(rows, key=lambda x:(x[1][0], x[0])))
        source = [r for _, r in sorted(rows, key=lambda x:(x[1][0], x[0]))]
    else:
        _, row = max(rows, key=lambda x:(x[1][1], x[1][0], x[0]))
        text, source = row[2], row
    raw = units(text)
    weight = 0
    for k in range(1, len(raw)+1):
        weight += rt._unit_weight(raw[-k])
        if weight >= 25:
            return raw[-k:], source
    return [], source


def anchor_hit(anchor, raw, start):
    if not anchor:
        return None
    allowed = set(anchor)
    for i in range(max(0, start), len(raw)):
        if raw[i] not in allowed:
            continue
        n = rt._repeated_head(anchor, raw[i:i+len(anchor)+8])
        if n:
            return dict(start=i, end=i+n, units=raw[i:i+n])
    return None


def rates(trace):
    by_lane = {}
    for event in trace:
        for row in event['solid']:
            if row[1] <= row[0] or not units(row[2]):
                continue
            v = len(units(row[2]))/((row[1]-row[0])/S)
            if v > by_lane.get(row[3], {}).get('maximum_row_units_per_second', -1):
                by_lane[row[3]] = dict(maximum_row_units_per_second=v, rate=2*v, witness=row)
    return by_lane


class TailCandidate:
    def __init__(self, floor=False, guard=False, joined=False):
        self.floor, self.guard, self.joined = floor, guard, joined
        self.state = {}

    def apply(self, event, c1, rate):
        active = {tuple(r['key']) for r in event['rows'] if r['key'] is not None}
        self.state = {k:v for k,v in self.state.items() if k in active}
        cuts, details = [], []
        for row, floor_n in zip(event['rows'], c1):
            key = tuple(row['key']) if row['key'] is not None else None
            frontier = event['frontiers'].get(row['lane'], 0)
            prior = self.state.get(key)
            if prior and (frontier < prior['frontier'] or row['raw_count'] < prior['n']):
                prior = None
            previous = prior['n'] if prior else 0
            previous_frontier = prior['frontier'] if prior else 0
            missing = row.get('missing_prefix', 0)
            anchor, source = source_tail(event['solid'], row['lane'], self.joined)
            hit = anchor_hit(anchor, units(row['raw']), max(0, previous-missing))
            n = row['base_cut']
            if self.floor:
                n = max(n, floor_n, previous)
            budget = max(0, frontier-previous_frontier)/S*rate.get(row['lane'], {}).get('rate', 0)
            end = missing+hit['end'] if hit else None
            rejected = bool(hit and self.guard and end-previous > budget)
            if hit and not rejected:
                n = max(n, end)
            if key is not None:
                self.state[key] = dict(n=n, frontier=frontier)
            cuts.append(n)
            details.append(dict(key=key, previous=prior, anchor=anchor, source=source, hit=hit,
                                candidate_end=end, guard_budget=budget, guard_rejected=rejected, chosen=n))
        for key in event.get('finished', ()):
            self.state.pop(tuple(key), None)
        return cuts, details


def make_candidates():
    return {n:TailCandidate(floor=n.startswith('C4'), guard=n.endswith('G'), joined=n.endswith('J'))
            for n in NAMES[2:]}


def complete(name, loader):
    events, commits, total = loader()
    trace = a6.capture(name, loader, a6.HEAD)
    final = stream.final_rows(commits)
    lineage, indexed = {}, {}
    for text, start, end, _ in sorted(events, key=lambda e:e[2]):
        raw = units(text)
        prior, clocks = lineage.get(start, ([], []))
        prefix = next((i for i, (a,b) in enumerate(zip(prior, raw)) if a != b), min(len(prior), len(raw)))
        clocks = clocks[:prefix]+([end]*(len(raw)-prefix) if prefix == len(prior) else [None]*(len(raw)-prefix))
        lineage[start] = (raw, clocks)
        indexed[(text.strip(), end)] = clocks
    truths = []
    for event in trace:
        rows = []
        for row in event['rows']:
            f = event['frontiers'].get(row['lane'], 0)
            solid = [x[2] for x in event['solid'] if x[3] == row['lane']]
            t = score.true_cut(units(row['raw']), score.later_solid(final, row['lane'], f),
                               score.units(' '.join(solid))[-row['raw_count']-40:])
            rows.append(dict(boundary=t, publication_clocks=indexed.get((row['raw'], row['end']))))
        truths.append(rows)
    return trace, truths, total/S


def stress(sub):
    xs = a6.load(sub)
    trace, truths, previous, next_id = [], [], [], 0
    final = next(x['solid'] for x in reversed(xs) if x['status'] == 'active')
    final_rows = [[r['start_sample'], r['end_sample'], r['text'], r.get('source_lane')] for r in final]
    for x in xs:
        if x['status'] != 'active':
            continue
        shown = (x.get('provisional') or {}).get('segments', [])
        fronts = {lane:max((r['end_sample'] for r in x['solid'] if r.get('source_lane') == lane), default=0)
                  for lane in ('system', 'microphone')}
        rows, ts = [], []
        for r in shown:
            lane = r['source_lane']
            matches = [o for o in previous if o['lane'] == lane and r['start_sample'] < o['end'] and r['end_sample'] >= o['end']]
            if len(matches) == 1:
                key = matches[0]['key']
            else:
                next_id += 1
                key = (lane, next_id)
            p = x.get('preview', {}).get(lane, {})
            only = sum(q['source_lane'] == lane for q in shown) == 1
            hidden = p.get('raw_units_last', 0)-p.get('shown_units_last', 0) if only and p else 0
            rows.append(dict(lane=lane, key=key, start=r['start_sample'], end=r['end_sample'], raw=r['text'],
                             raw_count=len(units(r['text']))+hidden, base_cut=hidden, missing_prefix=hidden))
            t = score.true_cut(units(r['text']), score.later_solid(final_rows, lane, fronts[lane]),
                               score.units(' '.join(q['text'] for q in x['solid'] if q.get('source_lane') == lane))[-len(units(r['text']))-40:])
            ts.append(dict(boundary=t))
        trace.append(dict(at=x['e'], rows=rows, solid=[[r['start_sample'], r['end_sample'], r['text'], r.get('source_lane')]
                                                   for r in x['solid']], frontiers=fronts))
        truths.append(ts)
        previous = rows
    return trace, truths


def measure(name, trace, truths, seconds, seam):
    rate = rates(trace)
    floor = a6.Floor()
    candidates = make_candidates()
    outputs = {n:[] for n in NAMES}
    full, examples = [], []
    for i, event in enumerate(trace):
        c0 = [r['base_cut'] for r in event['rows']]
        c1 = floor.apply(event['rows'], event['frontiers'], event.get('finished', ()))
        allcuts, detail = dict(C0=c0, C1=c1), {}
        for name_c, candidate in candidates.items():
            allcuts[name_c], detail[name_c] = candidate.apply(event, c1, rate)
        rendered = {}
        for n in NAMES:
            extra = [max(0, v-r.get('missing_prefix', 0)) for r,v in zip(event['rows'], allcuts[n])]
            assert all(v <= len(units(r['raw'])) for r,v in zip(event['rows'], extra))
            outputs[n].append(extra)
            rendered[n] = [a6.shown_after(r['raw'], v) for r,v in zip(event['rows'], extra)]
            for j,(r,v,b,t) in enumerate(zip(event['rows'],extra,outputs['C0'][-1],truths[i])):
                boundary = t['boundary']
                if boundary is not None and max(0,v-boundary) > max(0,b-boundary):
                    examples.append(dict(candidate=n, at=event['at'], row=j, cut=v, boundary=boundary,
                                         additional=max(0,v-boundary)-max(0,b-boundary),
                                         removed_units=units(r['raw'])[max(b,boundary):v], raw=r['raw'], solid=event['solid']))
        full.append(dict(**event, candidate_cuts=allcuts, candidate_additional_cuts={n:outputs[n][-1] for n in NAMES},
                         rendered=rendered, details=detail, truth=truths[i], c1_state=copy.deepcopy(list(floor.state.items())),
                         candidate_state={n:copy.deepcopy(list(c.state.items())) for n,c in candidates.items()}))
    with (EV/f'{name}-state.jsonl').open('w') as receipt:
        for event in full:
            receipt.write(json.dumps(event, ensure_ascii=False)+'\n')
            emit(name, event)
    save(f'{name}-fresh-proxy-examples.json', examples)
    report = {n:a6.aggregate(trace, outputs[n], truths, outputs['C0']) for n in NAMES}
    report.update(audio_seconds=seconds, scope=seam, rates=rate,
                  guard_rejections={n:sum(d['guard_rejected'] for e in full for d in e['details'][n]) for n in candidates},
                  anchor_source_differences=sum(source_tail(e['solid'],r['lane'])[0] != source_tail(e['solid'],r['lane'],True)[0]
                                                for e in trace for r in e['rows']))
    emit(name+'-summary', report)
    return report, full


def control_sequence(case, events, known_boundaries, rate):
    floor = a6.Floor()
    candidates = make_candidates()
    memory, out = [], []
    for event, boundary in zip(events, known_boundaries):
        row = event['rows'][0]
        rr = rt.GeminiSegment(row['start'], row['end'], row['raw'], source_lane=row['lane'])
        cc = tuple(score.eff(r) for r in event['solid'])
        shown = rt._trim_committed_preview((rr,), cc, memory)
        row['base_cut'] = a6.cut(row['raw'], shown[0].text) if shown else len(units(row['raw']))
        row['raw_count'] = len(units(row['raw']))
        c1 = floor.apply(event['rows'], event['frontiers'], event.get('finished', ()))
        cuts, details = dict(C0=[row['base_cut']], C1=c1), {}
        for n,c in candidates.items():
            cuts[n], details[n] = c.apply(event, c1, rate)
        results = {n:dict(cut=v[0], fresh_hidden=max(0,v[0]-boundary),
                         exact_fresh_units_hidden=units(row['raw'])[boundary:v[0]], shown=a6.shown_after(row['raw'],v[0]))
                   for n,v in cuts.items()}
        record = dict(case=case, event=copy.deepcopy(event), known_fresh_start_unit=boundary,
                      results=results, details=details, state={n:copy.deepcopy(list(c.state.items())) for n,c in candidates.items()})
        out.append(record)
        emit('control', record)
    return out


def event(raw, solid, f=15, clock=20, key=('system',0), start=None):
    return dict(at=clock, rows=[dict(lane=key[0], key=key, start=int((f if start is None else start)*S),
                                   end=int(clock*S), raw=raw, raw_count=len(units(raw)), base_cut=0)],
                solid=solid, frontiers={key[0]:int(f*S)}, finished=())


def attacks(populations):
    rate = populations['en-302s']['rates']
    controls = {}
    en = units(max(stream.load_e1()[0], key=lambda e:len(units(e[0])))[0])
    zh = units(max(stream.load_zh()[0], key=lambda e:len(units(e[0])))[0])
    old, fresh = en[:60], zh[:20]
    assert not set(old)&set(fresh)
    solid = [[0,15*S,' '.join(old),'system']]
    controls['A5-known-clock-rewrite'] = control_sequence('A5-known-clock-rewrite',
        [event(' '.join(old),solid,clock=16), event(' '.join(old[15:]+fresh),solid,clock=20)], [60,45],rate)
    # Exact a6 snapshot proof: rewritten prefix shares no head, so time cut0.
    snapshot = rt._PreviewSnapshots()
    origin = rt.GeminiSegment(0,14*S,' '.join(old),source_lane='system')
    snapshot.publication((origin,),(('system',14*S),))
    snapshot.advance(tuple(score.eff(r) for r in solid))
    raw = ' '.join(old[15:]+fresh)
    origin = rt.GeminiSegment(0,20*S,raw,source_lane='system')
    row = rt.GeminiSegment(15*S,20*S,raw,source_lane='system')
    snapshot.publication((origin,),(('system',20*S),))
    tc = snapshot.cuts((row,),(origin,))
    assert tc == [0], tc
    controls['A5-time-proof'] = dict(time_cut=tc, old=old, deleted_head=old[:15], fresh=fresh)
    old_text = 'one settled introduction about the previous meeting then finish with a chorus now'
    raw = ('one settled introduction about the previous meeting fresh unrevised speech has never '
           'been committed and this completely different lengthy passage belongs to the new '
           'chorus occurrence today then finish with a chorus now')
    controls['A2-F1-A2-later-chorus'] = control_sequence('A2-F1-A2-later-chorus',
        [event(raw,[[0,40*S,old_text,'system']],f=40,clock=55)], [8],rate)
    old_text = 'one settled introduction with several words before the frontier'
    fresh_text = 'Zebras gallop quietly while fresh speakers discuss entirely novel matters today'
    controls['A2-A4-new-turn-chorus'] = control_sequence('A2-A4-new-turn-chorus',
        [event(old_text+' '+fresh_text,[[0,15*S,old_text,'system']],key=('system',16*S),start=16)], [0],rate)
    # Same ongoing turn: old anchor disappears, exact phrase reappears only in fresh speech.
    head = 'alpha beta gamma delta epsilon'
    tail = 'then finish with a chorus now'
    old_text = head+' '+tail
    fresh_text = 'fresh unrevised speech has never been committed and belongs to a later occurrence '+tail
    controls['A2-same-turn-missing-old-anchor'] = control_sequence('A2-same-turn-missing-old-anchor',
        [event(old_text,[[0,15*S,old_text,'system']],clock=16),
         event(head+' '+fresh_text,[[0,30*S,old_text,'system']],f=30,clock=35)], [11,5],rate)
    for name, solid_text, raw, boundary in [
        ('short-common-four', 'yes we can agree', 'different fresh words yes we can agree',0),
        ('common-five', 'yes we can agree now', 'different fresh words yes we can agree now',0),
        ('CJK-eight', '今天一起讨论计划', '今天一起讨论计划新的内容',8),
        ('CJK-nine', '今天我们讨论新计划', '今天我们讨论新计划新的内容',9),
        ('mixed-script', '今天Gemini模型需要新的計畫', '新的語句今天Gemini模型需要新的計畫',0),
        ('traditional-simplified', '我們會討論這個問題和計畫', '我们会讨论这个问题和计划新的内容',12)]:
        controls['A3-'+name] = control_sequence('A3-'+name,
            [event(raw,[[0,15*S,solid_text,'system']])],[min(boundary,len(units(raw)))],
            {**rate,'system':populations['zh-188s']['rates']['system']})
    # A starts first, finishes last; B starts later, ends earlier. Joined-start tail is stale B.
    latest = 'the latest ending speaker closes this discussion with a clear decision'
    stale = 'the overlapping speaker repeats this familiar chorus again'
    solids = [[0,20*S,latest,'system'],[10*S,18*S,stale,'system']]
    controls['A4-latest-end'] = control_sequence('A4-latest-end',
        [event(latest+' fresh words stay visible today',solids,f=20,clock=25)], [len(units(latest))],rate)
    controls['A4-stale-tail-in-fresh'] = control_sequence('A4-stale-tail-in-fresh',
        [event('new speech from this moment '+stale,solids,f=20,clock=25)], [0],rate)
    long_prefix = 'new speech from this moment belongs to a separate entirely fresh overlapping speaker occurrence today'
    controls['A4-long-fresh-stale-tail'] = control_sequence('A4-long-fresh-stale-tail',
        [event(long_prefix+' '+stale,solids,f=20,clock=25)], [0],rate)
    for label,text in [('common-five','yes we can agree now'),('mixed-script','今天Gemini模型需要新的計畫')]:
        controls['A3-long-prefix-'+label] = control_sequence('A3-long-prefix-'+label,
            [event(long_prefix+' '+text,[[0,15*S,text,'system']])],[0],
            {**rate,'system':populations['zh-188s']['rates']['system']})
    for cell in ('c2','c3','c4'):
        xs = a6.load('runs/'+cell)
        final = next(x['solid'] for x in reversed(xs) if x['status'] == 'active')
        old_row = next(r for r in final if 'Is it you? Is it you? Is it you?' in r['text'])
        old = [old_row['start_sample'],old_row['end_sample'],old_row['text'],'system']
        # Explicit known-clock composition from recorded chorus text, not a service occurrence claim.
        frontier = old[1]/S
        controls['A2-recorded-'+cell+'-chorus-composition'] = control_sequence('A2-recorded-'+cell+'-chorus-composition',
            [event(long_prefix+' '+old[2],[old],f=frontier,clock=frontier+10)], [0],rates([dict(solid=[old])]))
    save('constructed-controls.json',controls)
    return controls


def collapse(full):
    at = next(i for i,e in enumerate(full) if e['at'] == 255.1)
    e = full[at]
    row = next(r for r in e['rows'] if r['lane'] == 'system')
    raw = units(row['raw'])
    limit = max(60,len(raw)*5//4+8)
    tail = units(' '.join(r[2] for r in e['solid'] if r[3] == 'system'))[-limit:]
    blocks = [b for b in difflib.SequenceMatcher(None,tail,raw,autojunk=False).get_matching_blocks() if b.size]
    gaps = [dict(solid_gap=b.a-a.a-a.size, grey_gap=b.b-a.b-a.size,
                 missing=tail[a.a+a.size:b.a], next_size=b.size, tail_units_after_gap=len(tail)-b.a)
            for a,b in zip(blocks,blocks[1:]) if b.a-a.a-a.size == 24 and b.b-a.b-a.size == 0]
    anchor, source = source_tail(e['solid'],'system')
    now_hit = anchor_hit(anchor,raw,0)
    future = []
    for i,x in enumerate(full[at+1:],1):
        for r in x['rows']:
            if r['lane'] != 'system':continue
            a,s = source_tail(x['solid'],'system')
            h = anchor_hit(a,units(r['raw']),0)
            if a != anchor and h:
                future.append(dict(publications_after_collapse=i, at=x['at'], delta_seconds=x['at']-e['at'],
                                   anchor=a, source=s, hit=h))
                break
        if future:break
    out = dict(collapse_at=e['at'], gaps24=gaps, latest_end_anchor=anchor, latest_end_source=source,
               current_anchor_hit=now_hit, first_later_tail_hit=future[0] if future else None,
               raw_prefix_missing=row.get('missing_prefix',0), seam='published suffix; original raw/keys unavailable')
    save('A1-collapse.json',out)
    emit('A1-collapse',out)
    return out


def recorded_repetitions(populations):
    # Cells2--4 recorded snapshots only. Never run their capture/provider helpers.
    base = a6.BASE
    folders = [('cell2','runs/c2'),('cell3','runs/c3'),('cell4','runs/c4')]
    out = {}
    for label, sub in folders:
        path = base/sub/'snapshots.jsonl'
        if not path.is_file():
            out[label] = dict(stage='UNMEASURED', reason='recorded snapshots absent', path=str(path))
            continue
        trace,truths = stress(sub)
        seconds = json.loads((base/sub/'receipt.json').read_text())['audio']
        # Fixture audio metadata is descriptive; duration from observed tape samples in receipt when available.
        report,full = measure(label,trace,truths,seconds['duration_ms']/1000,'extra attack population; recorded published rows only; not core denominator')
        repeat_examples = []
        for e in full:
            for r in e['rows']:
                anchor,_ = source_tail(e['solid'],r['lane'])
                raw = units(r['raw'])
                exact = [i for i in range(len(raw)-len(anchor)+1) if anchor and raw[i:i+len(anchor)] == anchor]
                if exact:
                    repeat_examples.append(dict(at=e['at'],lane=r['lane'],anchor=anchor,exact_hit_starts=exact,
                                                proxy_boundaries=[t['boundary'] for t in e['truth']],
                                                candidate_cuts=e['candidate_cuts'],raw=r['raw']))
        save(label+'-repeated-lines.json',repeat_examples)
        final = next(x['solid'] for x in reversed(a6.load(sub)) if x['status'] == 'active')
        chorus_rows = [r for r in final if 'is it you' in r['text'].casefold()]
        chorus = []
        for old_row in chorus_rows:
            old_units = units(old_row['text'])
            for later_row in chorus_rows:
                if later_row['start_sample'] < old_row['end_sample']:continue
                blocks = [b for b in difflib.SequenceMatcher(None,old_units,units(later_row['text']),autojunk=False).get_matching_blocks()
                          if sum(rt._unit_weight(u) for u in old_units[b.a:b.a+b.size]) >= 25]
                if blocks:
                    chorus.append(dict(old=old_row,later=later_row,blocks=[list(b) for b in blocks],
                                       latest_end_anchor=source_tail([[old_row['start_sample'],old_row['end_sample'],old_row['text'],old_row.get('source_lane')]],old_row.get('source_lane'))[0]))
        save(label+'-chorus-source.json',dict(chorus_rows=chorus_rows,repeated_row_pairs=chorus,
                                           actual_acoustic_retention='UNMEASURED; no grey word clocks'))
        out[label] = dict(report=report, exact_anchor_rows=len(repeat_examples), multiple_exact_anchor_rows=sum(len(e['exact_hit_starts'])>1 for e in repeat_examples), recorded_chorus_rows=len(chorus_rows), repeated_chorus_row_pairs=len(chorus), audio_metadata=seconds)
    save('A2-recorded-repetitions.json',out)
    return out


def main():
    EV.mkdir(parents=True,exist_ok=True)
    report = dict(base='099b1fde',provider_calls=0,cost_usd=0,candidates=list(NAMES),frozen_notes=str(HERE/'NOTES.md'))
    allfull = {}
    for name,loader,count in [('zh-188s',stream.load_zh,366),('en-302s',stream.load_e1,575),('r5d-cell',stream.load_cell,64)]:
        trace,truths,seconds = complete(name,loader)
        assert len(trace) == count,(name,len(trace),count)
        report[name],allfull[name] = measure(name,trace,truths,seconds,'complete product capture; candidate overlay, not shipped candidate')
    for name,sub,count in [('c6s','runs-recheck/c6s',478),('c6','runs/c6',868)]:
        trace,truths = stress(sub)
        assert len(trace) == count,(name,len(trace),count)
        report[name],allfull[name] = measure(name,trace,truths,300 if name=='c6s' else 960,'published-row repair; overlap continuity conditional; raw/final flags absent')
    report['A1'] = collapse(allfull['c6s'])
    controls = attacks(report)
    report['constructed_fresh_hidden'] = {name:{n:sum(e['results'][n]['fresh_hidden'] for e in xs) for n in NAMES}
                                           for name,xs in controls.items() if isinstance(xs,list)}
    report['A2-recorded'] = recorded_repetitions(report)
    save('measurement.json',report)
    emit('summary',report)

if __name__ == '__main__':
    main()
