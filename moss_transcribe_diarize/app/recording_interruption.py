"""Capture gaps are timeline metadata, never speech or speaker rows."""
from __future__ import annotations


def clock_time(seconds: float) -> str:
    hours, remainder = divmod(max(0, int(seconds)), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def interruption_line(gap: dict, sample_rate: int = 16000) -> str | None:
    end = gap['end_sample']
    if end is None:
        return None
    return (f"([{clock_time(gap['start_sample'] / sample_rate)}-"
            f"{clock_time(end / sample_rate)}] Recording Interrupted)")


def interruption_fields(gaps: list[dict], sample_rate: int = 16000) -> dict:
    if not gaps:
        return {}
    return {'interruptions': [dict(gap) for gap in gaps],
            'interruption_lines': [line for gap in gaps if (line := interruption_line(gap, sample_rate)) is not None]}


def transcript_export(document: dict, format: str) -> str:
    """The product's Markdown/plain-text formats, with gaps in meeting order."""
    if format not in {'md', 'txt'}:
        raise ValueError('Transcript format must be md or txt.')
    rows = []
    for row in document.get('segments', []):
        text = str(row.get('text', '')).strip()
        if text:
            label = str(row.get('speaker', 'Speaker TBD'))
            stamp = clock_time(row['start'])
            rendered = (f'## [{stamp}] {label}\n\n{text}' if format == 'md'
                        else f'[{stamp}] {label}:\n{text}')
            rows.append((row['start'], 1, rendered))
    for gap in document.get('interruptions', []):
        if (line := interruption_line(gap)) is not None:
            rows.append((gap['start_sample'] / 16000, 0, line))
    return '\n\n'.join(row[2] for row in sorted(rows, key=lambda row: row[:2]))
