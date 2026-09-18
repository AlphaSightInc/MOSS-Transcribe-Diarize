"""One-off mutation efficacy: all mutations restored before process exit."""
from pathlib import Path
import sys, json
sys.path[:0]=['.','tests/phase2','prototypes/lane-decode-proto']
from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference, InferenceTranscript
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer, TerminalOutcome
import pytest
terminal_only='--terminal-only' in sys.argv
if not terminal_only: RunnerBoundedWavInference.transcribe_pcm=lambda self,**kwargs:InferenceTranscript(transcript='')
TerminalTranscriptFinalizer.finalize=lambda self,**kwargs:self._refused(kwargs['plan'],TerminalOutcome.NO_TRANSCRIPT,'mutation_dropped_terminal',gaps=())
p=Path('frontend/src/api/mossPoller.ts');original=p.read_text()
anchor='function parsePublishedSegments(value: unknown, sampleRate: unknown, speakers: string[]): TranscriptItem[] | null {'
assert original.count(anchor)==1
if not terminal_only: p.write_text(original.replace(anchor,anchor+'\n  return []; // temporary WP12 mutation: drop published words'))
try:
 targets=[
 'tests/phase2/test_runner_composition.py::test_launcher_without_prompt_finalizer_builds_http_request',
 'tests/test_live_service_replay.py::ReplayTerminalFinalizationWaitTest::test_the_run_reports_the_terminal_surface_and_the_events_that_made_it'] if terminal_only else [
 'tests/test_live_pipeline_seams.py::test_the_decode_seam_publishes_a_salvaged_span_and_says_that_it_salvaged_it',
 'tests/test_live_rolling_wiring.py::RollingRuntimeWiringTest::test_a_rolling_window_is_never_offered_to_the_M1_salvage_gate',
 'tests/phase2/test_runner_composition.py::test_launcher_without_prompt_finalizer_builds_http_request',
 'tests/test_live_service_replay.py::ReplayTerminalFinalizationWaitTest::test_the_run_reports_the_terminal_surface_and_the_events_that_made_it',
 'tests/phase2/test_draft_lane.py::test_reader_retires_draft_by_audio_boundary[multiple]']
 result=pytest.main(['-q','-p','no:cacheprovider','-p','evidence.mvpfix.wp16.local_scratch','--basetemp=.wp33/mutation-tests',*targets])
 assert result==1
finally:
 if not terminal_only: p.write_text(original)
