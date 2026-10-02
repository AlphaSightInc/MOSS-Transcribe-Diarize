"""A4 first falsifier: literal publication freshness vs max(snapshot, retained cuts).

Absorbed replay bench. No product mutation and no provider/audio access.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(HERE.parent / 'f1'), str(ROOT / 'tests/gemini')]
import score
import stream
import test_gemini_preview_duplication as tests
from moss_transcribe_diarize.app import gemini_live_runtime as rt

S = 16000
EV = Path.home() / 'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A4'
F1 = EV.parent / 'P72/f1/runs'


def common(a, b):
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


class Snapshot:
    """Ideal original-key/lane-clock reducer: the strongest form of T4's premise."""
    def __init__(self):
        self.publications = {}

    def publish(self, lane, turn, clock, text):
        self.publications.setdefault((lane, turn), []).append((clock, score.units(text, fold=False)))

    def cut(self, lane, turn, frontier, text):
        eligible = [p for p in self.publications.get((lane, turn), ()) if p[0] <= frontier]
        if not eligible:
            return 0
        return common(max(eligible, key=lambda p: p[0])[1], score.units(text, fold=False))


def attack():
    """Known fresh occurrences, no guessed turn key or stale clock, actual runtime seam."""
    cases = [
        ('five-word-new-turn', 'alpha beta gamma delta epsilon', 'alpha beta gamma delta epsilon'),
        ('new-turn-with-unique-insert', 'alpha beta gamma delta epsilon',
         'alpha beta gamma novelword delta epsilon'),
        ('chorus', 'yes yes yes yes yes yes', 'yes yes yes yes yes yes'),
        ('eleven-character-new-turn', '这是大家共同讨论的问题', '这是大家共同讨论的问题'),
    ]
    report = []
    for name, solid, raw in cases:
        for lane in ('system', 'microphone'):
            with tempfile.TemporaryDirectory() as tmp:
                runtime = tests._runtime(Path(tmp), seconds=30, lanes=True)
                tests._commit(runtime, solid, through_s=15, lane=lane)
                reducer = Snapshot()
                reducer.publish(lane, 16*S, 20*S, raw)
                time_cut = reducer.cut(lane, 16*S, 15*S, raw)
                row = rt.GeminiSegment(16*S, 20*S, raw, source_lane=lane)
                effective = runtime.snapshot('one').session.effective_transcript
                baseline = rt._trim_committed_preview((row,), effective)
                text_cut = score.cuts((row,), baseline)[0][2]
                runtime.publish_update('one', rt.GeminiPreview(20*S, (row,)))
                shown = [r['text'] for r in runtime.snapshot('one').session.provisional.segments]
                raw_units = score.units(raw, fold=False)
                report.append(dict(case=name, lane=lane, injection=True,
                    frontier=15*S, original_turn_start=16*S, first_publication=20*S,
                    raw=raw, solid=[r.text for r in effective], shown=shown,
                    unit_first_publication=[20*S]*len(raw_units),
                    text_cut=text_cut, time_cut=time_cut, max_cut=max(text_cut,time_cut),
                    fresh_units_hidden=max(text_cut,time_cut),
                    unique_fresh_units_hidden=[u for u in raw_units[:text_cut]
                                              if u not in score.units(solid, fold=False)],
                    remembered_state=runtime._sessions['one'].preview_cuts,
                    baseline_output=[r.text for r in baseline]))
                assert shown == [r.text for r in baseline]
                assert time_cut == 0
    (EV/'controls.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return [{k:v for k,v in r.items() if k in ('case','lane','time_cut','text_cut',
            'fresh_units_hidden','unique_fresh_units_hidden')} for r in report]


def recorded(name, loader, filename):
    events, commits, total = loader()
    prior, indexed, by_turn = {}, {}, {}
    # Only pure initial/growing publications yield known occurrence clocks. A rewrite
    # invalidates identity for the rewritten suffix: no semantic alignment invented.
    for index, (text, start, end, final) in enumerate(events):
        units = score.units(text, fold=False)
        old, clocks = prior.get(start, ([], []))
        prefix = common(old, units)
        clocks = clocks[:prefix] + ([end]*(len(units)-prefix) if prefix == len(old)
                                    else [None]*(len(units)-prefix))
        event = dict(event=index, text=text.strip(), start=start, end=end, final=final,
                     units=units, first_publication=clocks)
        prior[start] = units, clocks
        indexed[(text.strip(),end)] = event
        by_turn.setdefault(start, []).append(event)
    calls = [json.loads(line) for line in (F1/filename).read_text().splitlines()]
    cuts, trace = [], []
    unmapped = 0
    for index, call in enumerate(calls):
        segments = tuple(score.seg(r) for r in call['segments'])
        committed = tuple(score.eff(r) for r in call['committed'])
        kept = rt._trim_committed_preview(segments, committed, cuts)
        for row, (_, units, text_cut) in zip(segments, score.cuts(segments, kept)):
            event = indexed.get((row.text.strip(),row.end_sample))
            if event is None:
                unmapped += 1
                continue
            frontier = call.get('frontier', max((r.end_sample for r in committed
                                               if r.source_lane == row.source_lane),default=0))
            eligible = [e for e in by_turn[event['start']] if e['end'] <= frontier]
            snapshot = max(eligible,key=lambda e:e['end']) if eligible else None
            time_cut = common(snapshot['units'],units) if snapshot else 0
            hidden = [i for i, clock in enumerate(event['first_publication'][:text_cut])
                      if clock is not None and clock > frontier]
            if hidden:
                trace.append(dict(call=index, at=call['at'], frontier=frontier,
                    event=event, snapshot=snapshot, lane=row.source_lane,
                    text_cut=text_cut,time_cut=time_cut, chosen_cut=max(text_cut,time_cut),
                    time_adds_nothing=time_cut<=text_cut, known_fresh_hidden_indices=hidden,
                    known_fresh_hidden_units=[units[i] for i in hidden],
                    raw=row.text, baseline_shown=[r.text for r in kept],
                    solid=[r.text for r in committed if r.source_lane==row.source_lane]))
    (EV/f'{name}-fresh-audit.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
    return dict(calls=len(calls),events=len(events),unmapped_rows=unmapped,
                publications_hiding_known_fresh=len(trace),
                known_fresh_hidden_unit_publications=sum(len(r['known_fresh_hidden_indices']) for r in trace),
                conflicts_where_time_adds_nothing=sum(r['time_adds_nothing'] for r in trace),
                scope='Literal first-publication clocks; rewritten suffix lineage unknown. Not an acoustic-loss metric.')


def main():
    EV.mkdir(parents=True,exist_ok=True)
    report = dict(controls=attack(),recorded={
        'zh-188s': recorded('zh-188s',stream.load_zh,'zh-long-trim-base.jsonl'),
        'en-302s': recorded('en-302s',stream.load_e1,'e1-en-trim-base.jsonl')})
    report['absolute_gate_passes'] = all(r['fresh_units_hidden']==0 for r in report['controls']) and all(
        r['known_fresh_hidden_unit_publications']==0 for r in report['recorded'].values())
    report['decision'] = ('BLOCKED: G-fresh absolute conflicts with retained text cuts/G-same'
                          if not report['absolute_gate_passes'] else 'Proceed to remaining prototype gates')
    (EV/'measurement.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
