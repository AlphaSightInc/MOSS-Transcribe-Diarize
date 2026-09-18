"""WP3: no decoder calls for zero/silent spans; nonzero quiet speech stays eligible."""
from types import SimpleNamespace
import numpy as np
import pytest
from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference, LiveProviderError
from moss_transcribe_diarize.app.live_capture_guard import observe_capture_span
from moss_transcribe_diarize.app.live_session import FrozenSpan
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer
from moss_transcribe_diarize.app.live_lane_contract import LiveLane
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer, TerminalOutcome
from moss_transcribe_diarize.transcript_parser import parse_transcript
from tests.test_live_mixer import _frame, _Runtime
from tests.test_live_terminal_finalizer import tape_of, plan_for

class MustNotDecode:
    def transcribe(self, *a, **kw):
        raise AssertionError('decoder invoked')

@pytest.mark.parametrize('silent,value', [(False, 0), (True, 2000)])
def test_ingest_zero_and_silent_spans_emit_no_words_or_speakers(tmp_path, silent, value):
    source=LiveV2Session(max_retained_samples=32000)
    for lane in LiveLane:
        source.accept(_frame(lane,0,0,16000,8000,value,silent=silent))
    runtime=_Runtime()
    mixer=LiveCompatibilityMixer(max_output_samples=8000)
    mixed=mixer.admit_available('s',source,runtime,final=True)
    assert mixed is not None and mixed.frame.sample_count==8000
    assert not any(mixed.frame.pcm)
    adapter=RunnerBoundedWavInference(MustNotDecode(),max_samples=8000,scratch_dir=tmp_path)
    result=adapter.transcribe_pcm(span=FrozenSpan(id=1,epoch=0,start_sample=0,end_sample=8000,reason='end_silence'),pcm=mixed.frame.pcm)
    assert parse_transcript(result.transcript)==[]  # zero words and zero speaker labels
    assert result.generated_tokens==0 and result.elapsed_sec==0
    assert source.retained_frames(LiveLane.MICROPHONE)==()
    assert mixed.diagnostics.capture_guard['microphone']['decision']=='skip-zero'
    assert mixer.last_capture_guard is None

def test_terminal_zero_tape_never_calls_decoder(tmp_path):
    result=TerminalTranscriptFinalizer(runner=MustNotDecode(),scratch_dir=tmp_path).finalize(
        plan=plan_for(8000),tape=tape_of(8000,fill=b'\0\0'),base_text_revision_version=0)
    assert result.proposal is None
    assert result.accounting.outcome==TerminalOutcome.NO_TRANSCRIPT

@pytest.mark.parametrize('value',[b'\x01\0',b'\xff\xff'])
def test_one_lsb_quiet_audio_still_reaches_decoder(tmp_path,value):
    adapter=RunnerBoundedWavInference(MustNotDecode(),max_samples=8000,scratch_dir=tmp_path)
    with pytest.raises(LiveProviderError,match='decoder invoked'):
        adapter.transcribe_pcm(span=FrozenSpan(id=1,epoch=0,start_sample=0,end_sample=8000,reason='end_silence'),pcm=value*8000)

def test_playback_statistic_is_reporting_only_even_for_exact_copy():
    system=np.random.default_rng(4).normal(size=8000)
    mic=np.r_[np.zeros(80),system[:-80]]*.03
    observed=observe_capture_span(system,mic,sample_rate=16000,correlation=True)
    assert observed['playback_explained_fraction']==pytest.approx(1.)
    assert observed['playback_delay_samples']==80
    assert observed['playback_gain']==pytest.approx(.03)
    assert observed['microphone']['decision']=='decode'
    assert observed['leak_suppression'] is False

@pytest.mark.parametrize('system,mic', [([0]*8,[1]*8),([1]*8,[0]*8)])
def test_no_reference_or_mic_reports_unknown_not_leak(system,mic):
    observed=observe_capture_span(system,mic,sample_rate=16000,correlation=True)
    assert observed['playback_explained_fraction'] is None


@pytest.mark.parametrize('value',[b'\x01\0',b'\xff\xff'])
def test_single_nonzero_sample_still_reaches_decoder(tmp_path, value):
    adapter = RunnerBoundedWavInference(MustNotDecode(), max_samples=8000, scratch_dir=tmp_path)
    pcm = b'\0\0' * 3999 + value + b'\0\0' * 4000
    with pytest.raises(LiveProviderError, match='decoder invoked'):
        adapter.transcribe_pcm(span=FrozenSpan(id=1, epoch=0, start_sample=0, end_sample=8000, reason='end_silence'), pcm=pcm)


@pytest.mark.parametrize('enabled', [False, True])
def test_mixer_correlation_is_opt_in_and_never_changes_pcm(monkeypatch, enabled):
    from moss_transcribe_diarize.app import live_capture_guard as guard
    from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixerRegistry
    calls = []
    original = guard.correlate
    def track(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(guard, 'correlate', track)
    outputs = []
    for opt_in in [False, enabled]:
        source = LiveV2Session(max_retained_samples=32000)
        for lane in LiveLane:
            source.accept(_frame(lane, 0, 0, 16000, 8000, 2000))
        mixer = LiveCompatibilityMixerRegistry(max_output_samples=8000, capture_correlation=opt_in).create('s')
        mixed = mixer.admit_available('s', source, _Runtime(), final=True)
        outputs.append(mixed.frame.pcm)
        assert mixed.diagnostics.capture_guard['microphone']['decision'] == 'decode'
        assert mixed.diagnostics.capture_guard['leak_suppression'] is False
        assert (mixer.last_capture_guard is not None) is opt_in
        assert (mixed.diagnostics.capture_guard['playback_explained_fraction'] is not None) is opt_in
    assert outputs[0] == outputs[1]
    assert len(calls) == int(enabled)
