"""Aggregate the six content-free probe results and exact decoder HTTP request counts.
Usage: python summarize.py --requests /private/scratch/requests.jsonl
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--requests', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    requests = [json.loads(line) for line in args.requests.read_text().splitlines()]
    result = {}
    for arm in ('single-off', 'single-on', 'two-off', 'two-on', 'two-on-portal'):
        files = [root / f'{arm}-{i}.json' for i in (1, 2)] if arm.startswith('two') else [root / f'{arm}.json']
        rows = [json.loads(path.read_text()) for path in files]
        if len(rows) != (2 if arm.startswith('two') else 1):
            raise ValueError(f'{arm}: missing measurements')
        start = min(row['started_monotonic'] for row in rows)
        end = max(row['ended_monotonic'] for row in rows)
        selected = [row for row in requests if start <= row['time'] <= end]
        draft = sum(row['draft'] for row in selected)
        ticks = sum((row['draft_stats'] or {}).get('ticks', 0) for row in rows)
        skipped = sum((row['draft_stats'] or {}).get('skipped', 0) for row in rows)
        audio = sum(row['audio_seconds'] for row in rows)
        result[arm] = dict(
            probes=len(rows), audio_seconds=audio, decoder_requests=len(selected),
            draft_requests=draft, non_draft_requests=len(selected)-draft,
            requests_per_audio_second=len(selected)/audio,
            draft_ticks=ticks, skipped_ticks=skipped,
            skipped_fraction=skipped/ticks if ticks else None,
            **{key: [row.get(key) for row in rows] for key in (
                'coverage_p50_s', 'coverage_p95_s', 'first_text_latency_s',
                'first_text', 'label_coverage_p50_s', 'label_coverage_p95_s',
                'wer_vs_reference', 'legacy_sequence_match_error', 'final_finalization',
            )},
        )
    (root / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
