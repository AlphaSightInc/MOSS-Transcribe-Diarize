"""FIX7 throwaway witness/recovery measurement; absorbed into the A4 bench."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE)]
import candidate
from measure_core import snapshot_state
from moss_transcribe_diarize.app import gemini_live_runtime as rt

S = 16000
A = 'alpha beta gamma delta epsilon'
B = 'zeta eta theta iota kappa'


def main():
    factory = rt._PreviewSnapshots if '--product' in sys.argv else candidate.PreviewSnapshots
    report = {}
    for count in (65, 64):
        snapshots = factory()
        trace = []

        def publication(text, clock):
            rows = (rt.GeminiSegment(0, int(clock*S), text, source_lane='system'),)
            snapshots.publication(rows, (('system', int(clock*S)),))
            return rows

        publication(A, 14)
        snapshots.advance((rt.GeminiSegment(0, 15*S, 'unrelated solid', source_lane='system'),))
        trace.append(dict(action='seed', state=snapshot_state(snapshots)))
        for i in range(count):
            publication(B+' revision '+str(i), 20+i*.25)
        trace.append(dict(action='history', state=snapshot_state(snapshots)))
        solid = (rt.GeminiSegment(0, int(20.125*S), 'unrelated solid', source_lane='system'),)
        snapshots.advance(solid)
        rows = publication(A+' fresh tail', 37)
        cuts = snapshots.cuts(rows, rows)
        trace.append(dict(action='gap', cuts=cuts, state=snapshot_state(snapshots)))
        snapshots.advance((rt.GeminiSegment(0, 36*S, 'unrelated solid', source_lane='system'),))
        rows = publication(B+' revision '+str(count-1)+' fresh tail', 38)
        resumed = snapshots.cuts(rows, rows)
        snapshots.advance((rt.GeminiSegment(0, 36*S, 'unrelated solid', source_lane='system'),))
        persisted = snapshots.cuts(rows, rows)
        trace.append(dict(action='resumed', cuts=resumed, persisted=persisted,
                          state=snapshot_state(snapshots)))
        report[str(count)] = dict(gap_cuts=cuts, resumed_cuts=resumed,
                                 persisted_cuts=persisted, trace=trace)
    # Prototype the one-place optional-proof recovery with actual row/cut primitives.
    state = SimpleNamespace(preview_snapshots=factory(), preview_snapshot_errors=0)
    rows = (rt.GeminiSegment(0, 20*S, A+' fresh tail', source_lane='system'),)
    text_rows = rt._trim_committed_preview(rows, ())

    def explode(*args):
        raise RuntimeError('injected optional snapshot fault')

    state.preview_snapshots.cuts = explode
    try:
        cuts = state.preview_snapshots.cuts(rows, rows)
        shown = rt._apply_preview_time_cuts(rows, text_rows, cuts)
    except Exception:
        shown = text_rows
        state.preview_snapshots.clear()
        state.preview_snapshot_errors += 1
    report['fault'] = dict(shown=[r.text for r in shown], errors=state.preview_snapshot_errors,
                           state=snapshot_state(state.preview_snapshots))
    print(json.dumps(report, indent=2))
    assert all(report[str(n)]['gap_cuts']==[0] for n in (65, 64))
    assert all(report[str(n)]['resumed_cuts']==report[str(n)]['persisted_cuts']==[7]
               for n in (65, 64))
    assert shown==text_rows and state.preview_snapshot_errors==1


if __name__ == '__main__':
    main()
