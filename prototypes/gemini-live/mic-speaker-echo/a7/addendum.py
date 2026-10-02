"""Frozen A7 lead extension. Same original populations/scoring/every attack; no provider."""
import copy
import json
from pathlib import Path

import run as a7

ORIGINAL_EV = a7.EV
ORIGINAL_NAMES = a7.NAMES
NEW_NAMES = ('C5', 'C5+ONCE', 'C3S')
REPORT_NAMES = ('C0', 'C1', 'C4', 'C5', 'C5+ONCE', 'C3S')
rt, units, S = a7.rt, a7.units, a7.S


def satisfied_at(anchor, raw, cut):
    if not anchor or cut <= 0:
        return None
    for start in range(max(0, cut-len(anchor)-8), cut):
        if raw[start] not in anchor:
            continue
        n = rt._repeated_head(anchor, raw[start:cut])
        if n and n == cut-start:
            return dict(start=start, end=cut, units=raw[start:cut])
    return None


def first_hit_after(anchor, raw, cut):
    if not anchor:
        return None
    for start in range(len(raw)):
        if raw[start] not in anchor:
            continue
        n = rt._repeated_head(anchor, raw[start:start+len(anchor)+8])
        if n and start+n > cut:
            return dict(start=start, end=start+n, units=raw[start:start+n])
    return None


class SatisfiedCandidate:
    def __init__(self, floor, once=False):
        self.floor, self.once = floor, once
        self.state, self.allowance = {}, {}

    def apply(self, event, c1, rate):
        active = {tuple(r['key']) for r in event['rows'] if r['key'] is not None}
        self.state = {k:v for k,v in self.state.items() if k in active}
        cuts, details = [], []
        for row, floor_n in zip(event['rows'], c1):
            key = tuple(row['key']) if row['key'] is not None else None
            lane = row['lane']
            frontier = event['frontiers'].get(lane, 0)
            prior = self.state.get(key)
            if prior and (frontier < prior['frontier'] or row['raw_count'] < prior['n']):
                prior = None
            n = row['base_cut']
            if self.floor:
                n = max(n, floor_n, prior['n'] if prior else 0)
            current = n
            missing = row.get('missing_prefix', 0)
            raw = units(row['raw'])
            anchor, source = a7.source_tail(event['solid'], lane)
            solid_end = source[1] if source else None
            local_cut = max(0, current-missing)
            ending = satisfied_at(anchor, raw, local_cut)
            known = current > missing or missing == 0
            once_before = copy.deepcopy(self.allowance.get(lane))
            if self.once and solid_end is not None:
                old = self.allowance.get(lane)
                if old is None or solid_end > old['end']:
                    self.allowance[lane] = dict(end=solid_end, moved=False)
            old = self.allowance.get(lane)
            blocked = bool(self.once and old and (solid_end is not None and solid_end < old['end'] or old['moved']))
            hit = None
            if not ending and not blocked:
                hit = first_hit_after(anchor, raw, local_cut)
                if hit:
                    n = max(n, missing+hit['end'])
            advanced = n > current
            if self.once and advanced:
                self.allowance[lane]['moved'] = True
            if key is not None:
                self.state[key] = dict(n=n, frontier=frontier)
            cuts.append(n)
            details.append(dict(key=key, previous=prior, anchor=anchor, source=source,
                                current_cut=current, local_cut=local_cut, missing_prefix=missing,
                                satisfaction_known=known, satisfied=bool(ending), ending_match=ending,
                                hit=hit, candidate_end=missing+hit['end'] if hit else None,
                                guard_budget=None, guard_rejected=False, chosen=n, advanced=advanced,
                                once_blocked=blocked, solid_end=solid_end, once_before=once_before,
                                once_after=copy.deepcopy(self.allowance.get(lane))))
        for key in event.get('finished', ()):
            self.state.pop(tuple(key), None)
        return cuts, details


def candidates():
    original = {n:a7.TailCandidate(floor=n.startswith('C4'), guard=n.endswith('G'), joined=n.endswith('J'))
                for n in ORIGINAL_NAMES[2:]}
    return dict(**original, C5=SatisfiedCandidate(True),
                **{'C5+ONCE':SatisfiedCandidate(True, True)}, C3S=SatisfiedCandidate(False))


def parity(report, controls):
    original = json.loads((ORIGINAL_EV/'measurement.json').read_text())
    pops = ('zh-188s','en-302s','r5d-cell','c6s','c6')
    for pop in pops:
        for name in ORIGINAL_NAMES:
            assert report[pop][name] == original[pop][name], (pop,name)
    original_controls = json.loads((ORIGINAL_EV/'constructed-controls.json').read_text())
    assert set(controls) == set(original_controls)
    for case,events in controls.items():
        prior = original_controls[case]
        if not isinstance(events,list):
            assert events == prior,case
            continue
        assert len(events) == len(prior),case
        for i,(event,old) in enumerate(zip(events,prior)):
            assert json.loads(json.dumps(event['event'])) == old['event'], (case,i,'inputs')
            assert event['known_fresh_start_unit'] == old['known_fresh_start_unit'], (case,i,'boundary')
            for name in ORIGINAL_NAMES:
                assert event['results'][name] == old['results'][name], (case,i,name)
    for pop,entry in report['A2-recorded'].items():
        for name in ORIGINAL_NAMES:
            assert entry['report'][name] == original['A2-recorded'][pop]['report'][name], (pop,name)
    return dict(original_eight_candidates_exact=True, same_five_core_populations=True,
                same_three_recorded_attack_populations=True, same_all_eighteen_constructed_controls=True,
                exact_inputs_boundaries_and_original_outputs=True)


def diagnostic_counts(full):
    return {name:dict(satisfied_rows=sum(d['satisfied'] for e in full for d in e['details'][name]),
                      unknown_satisfaction_rows=sum(not d['satisfaction_known'] for e in full for d in e['details'][name]),
                      anchor_advances=sum(d['advanced'] for e in full for d in e['details'][name]),
                      once_blocked_rows=sum(d['once_blocked'] for e in full for d in e['details'][name]))
            for name in NEW_NAMES}


def proxy_episodes(full, name):
    """Count contiguous extra-flag intervals, not acoustic speech-loss episodes."""
    episodes, opened = [], None
    count = 0
    for e in full:
        extra = 0
        for chosen, base, truth in zip(e['candidate_additional_cuts'][name], e['candidate_additional_cuts']['C0'], e['truth']):
            boundary = truth['boundary']
            if boundary is not None:
                extra += max(0,chosen-boundary)-max(0,base-boundary)
        count += extra > 0
        if extra > 0 and opened is None:
            opened = e['at']
        if extra == 0 and opened is not None:
            episodes.append([opened,e['at']]); opened=None
    if opened is not None:
        episodes.append([opened,full[-1]['at']])
    return dict(flagged_observations=count, contiguous_proxy_flag_intervals=episodes,
                observed_flag_interval_seconds=sum(b-a for a,b in episodes),
                qualification='proxy observation intervals only; no acoustic rarity/duration claim')


def main():
    a7.EV = ORIGINAL_EV/'addendum'
    a7.EV.mkdir(parents=True, exist_ok=True)
    a7.NAMES = ORIGINAL_NAMES+NEW_NAMES
    a7.make_candidates = candidates
    report = dict(base='3a8223ad', provider_calls=0, cost_usd=0, candidates=list(a7.NAMES), report_candidates=list(REPORT_NAMES))
    allfull = {}
    for name,loader,count in [('zh-188s',a7.stream.load_zh,366),('en-302s',a7.stream.load_e1,575),('r5d-cell',a7.stream.load_cell,64)]:
        trace,truths,seconds = a7.complete(name,loader)
        assert len(trace) == count
        report[name],allfull[name] = a7.measure(name,trace,truths,seconds,'same complete product capture; frozen addendum overlays')
    for name,sub,count in [('c6s','runs-recheck/c6s',478),('c6','runs/c6',868)]:
        trace,truths = a7.stress(sub)
        assert len(trace) == count
        report[name],allfull[name] = a7.measure(name,trace,truths,300 if name=='c6s' else 960,'same published-row conditional repair; raw prefix/history missing')
    report['A1'] = a7.collapse(allfull['c6s'])
    controls = a7.attacks(report)
    report['constructed_fresh_hidden'] = {case:{n:sum(e['results'][n]['fresh_hidden'] for e in events) for n in a7.NAMES}
                                           for case,events in controls.items() if isinstance(events,list)}
    report['A2-recorded'] = a7.recorded_repetitions(report)
    report['parity'] = parity(report, controls)
    report['diagnostics'] = {p:diagnostic_counts(full) for p,full in allfull.items()}
    report['proxy_flag_intervals'] = {p:{n:proxy_episodes(full,n) for n in REPORT_NAMES} for p,full in allfull.items()}
    a7.save('measurement.json',report)
    a7.save('parity.json',report['parity'])
    a7.emit('addendum-summary', report)

if __name__ == '__main__':
    main()
