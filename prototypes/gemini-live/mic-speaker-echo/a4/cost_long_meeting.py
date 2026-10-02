"""L1: fixed two-hour solid population, production added preview work, no provider."""
import argparse
import inspect
import json
import statistics
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
from moss_transcribe_diarize.app import gemini_live_runtime as rt
from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment

S = 16000
LANES = ('system', 'microphone')


def measure():
    solid_text = ' '.join(f'solidword{i}' for i in range(30))
    solid = tuple(EffectiveTranscriptSegment(
        i * 5 * S, (i + 1) * 5 * S, solid_text, None, 'rolling', LANES[i % 2])
        for i in range(1440))
    preview_text = ' '.join(f'previewword{i}' for i in range(24))
    state = SimpleNamespace(preview_snapshots=rt._PreviewSnapshots(), preview_counters={})
    snapshots = state.preview_snapshots
    snapshots.advance(solid)
    origins = tuple(rt.GeminiSegment(7190 * S, 7194 * S, preview_text, source_lane=lane)
                    for lane in LANES)
    snapshots.publication(origins, tuple((lane, 7194 * S) for lane in LANES))
    # Only the benchmark supports both signatures to retain the pre-fix measurement.
    old_signature = 'solid' in inspect.signature(rt._preview_diagnostics).parameters
    lock = threading.RLock()
    added_ms, diagnostics_ms = [], []
    for i in range(210):
        clock = (7201 + i) * S
        rows = tuple(rt.GeminiSegment(7190 * S, clock, preview_text, source_lane=lane)
                     for lane in LANES)
        update = rt.GeminiPreview(clock, rows, rows,
                                  tuple((lane, clock) for lane in LANES))
        # Unchanged text trim is deliberately outside added-work timing.
        text_rows = rt._trim_committed_preview(rows, solid, [])
        before = time.perf_counter_ns()
        with lock:
            snapshots.advance(solid)
            clocks_before = dict(snapshots.clocks)
            snapshots.publication(update.origins, update.lane_end_samples, update.finished_turns)
            cuts = snapshots.cuts(update.segments, update.origins)
            shown = rt._apply_preview_time_cuts(update.segments, text_rows, cuts)
            snapshots.finish(update.finished_turns)
            args = (state, update, text_rows, shown, clocks_before)
            if old_signature:
                args = (state, update, solid, text_rows, shown, clocks_before)
            diagnostics_start = time.perf_counter_ns()
            rt._preview_diagnostics(*args)
            end = time.perf_counter_ns()
        if i >= 10:
            added_ms.append((end - before) / 1e6)
            diagnostics_ms.append((end - diagnostics_start) / 1e6)
    return {
        'solid_seconds': 7200, 'solid_rows': len(solid),
        'rows_per_lane': {lane: sum(r.source_lane == lane for r in solid) for lane in LANES},
        'solid_words_per_row': 30, 'preview_words_per_lane': 24,
        'warmup_publications': 10, 'measured_publications': len(added_ms),
        'added_mean_ms': statistics.mean(added_ms),
        'added_p95_ms': sorted(added_ms)[189],
        'diagnostics_mean_ms': statistics.mean(diagnostics_ms),
        'max_pending': snapshots.max_pending, 'gate_mean_ms': 1,
        'solid_units_last_present': any('solid_units_last' in v
                                       for v in state.preview_counters.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    report = measure()
    payload = json.dumps(report, indent=2) + '\n'
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(payload)
    print(payload, end='')
    assert report['added_mean_ms'] <= report['gate_mean_ms'], 'two-hour added cost exceeds 1ms'
    assert not report['solid_units_last_present'], 'whole-solid counter remains'


if __name__ == '__main__':
    main()
