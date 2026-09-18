"""WP32 review probe: terminal telemetry must retain either lane's truncation.
Failure detected: microphone-only truncation disappears when system is the template.
Consequence: finding for lead; aggregate the flag across successful lane results.
One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> evidence/mvpfix/wp32/spec_probe.py
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import wave

root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('wp32_lane_fixture', root / 'tests/test_live_lane_decode.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
rows = []
for truncated in (None, 1, 2):
    coordinator, _, session, arbiter = fixture.make()
    coordinator.accept_frame(fixture.frame())
    fixture.commit(coordinator, arbiter)
    class Runner:
        def transcribe(self, path, **kwargs):
            with wave.open(str(path)) as audio:
                marker = audio.readframes(1)[0]
            return SimpleNamespace(text='[0][S01]fixture words[2.5]', possibly_truncated=(marker == truncated))
    result = fixture.finalize_lanes(
        coordinator, fixture.TerminalTranscriptFinalizer(runner=Runner(), scratch_dir=Path(__file__).parent),
        plan=fixture.TerminalDecodePlan(session.epoch, 40000, 0, fixture.RollingStatus.STOPPED, 0, 0),
        tape=coordinator.tape, base_text_revision_version=0,
        base_surface=session.snapshot().effective_transcript,
        canonical_speakers=session.snapshot().identity_snapshot.canonical_speakers,
    )
    applied = session.apply_text_revision(result.proposal).applied
    rows.append(dict(truncated_lane={None: None, 1: 'system', 2: 'microphone'}[truncated],
                     expected=truncated is not None, actual=result.accounting.possibly_truncated,
                     applied=applied, finalization=session.snapshot().finalization_status))
    coordinator.release_tape()
print(json.dumps({'rows': rows, 'matched': sum(row['expected'] == row['actual'] for row in rows), 'total': len(rows)}, indent=2))
assert rows[0]['actual'] is False and rows[1]['actual'] is True and rows[2]['actual'] is False
