"""Real WebRTC VAD + exact PCM; only decoder output is controlled."""
from pathlib import Path
import wave

import pytest

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError, EmptyTranscriptCause
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner, WindowTranscriptionError
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
from tests.test_live_terminal_finalizer import plan_for


def wav(path, pcm):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
    return path


def voiced_pcm():
    with wave.open(str(Path(__file__).parent / 'fixtures/idea_020_provider_smoke.wav'), 'rb') as w:
        return w.readframes(w.getnframes())


class Decoder:
    model_path = 'controlled'
    def __init__(self, kind='zero', first_text=False):
        self.kind = kind
        self.first_text = first_text
        self.calls = 0
    def transcribe(self, path, **kwargs):
        self.calls += 1
        if self.first_text and self.calls == 1:
            text, tokens = '[0][S01]Hello[1]', 4
        elif self.kind in ('zero', 'blank'):
            raise EmptyTranscriptionError('empty', cause=EmptyTranscriptCause.NO_GENERATED_TOKENS if self.kind == 'zero' else EmptyTranscriptCause.EMPTY_TEXT)
        elif self.kind == 'unparseable':
            raise EmptyTranscriptionError('bad format', cause=EmptyTranscriptCause.UNPARSEABLE_TEXT, text='not compact', generated_tokens=4)
        elif self.kind == 'raw_unparseable':
            text, tokens = 'not compact', 4
        else:
            text, tokens = '', 0
        return TranscriptionResult(text=text, prompt_len=0, generated_tokens=tokens, elapsed_sec=0,
                                   model=self.model_path, audio=str(path), decoding='greedy', temperature=None)


@pytest.mark.parametrize('kind', ['zero', 'blank', 'raw'])
@pytest.mark.parametrize('seconds', [2.0000625, 150])
def test_silent_empty_window_succeeds_and_retains_diagnostics(tmp_path, kind, seconds):
    result = WindowedRunner(Decoder(kind)).transcribe(wav(tmp_path / 'silence.wav', bytes(int(seconds*16000)*2)))
    assert result.text == ''
    assert result.completed_windows == result.window_count
    assert len(result.window_diagnostics) == result.window_count
    assert all(d['condition'] == 'speechless_window_empty' and d['voiced_fraction'] == 0 for d in result.window_diagnostics)


@pytest.mark.parametrize('kind', ['zero', 'blank', 'raw'])
def test_speech_with_empty_decoder_remains_failure(tmp_path, kind):
    with pytest.raises(WindowTranscriptionError) as caught:
        WindowedRunner(Decoder(kind)).transcribe(wav(tmp_path / 'speech.wav', voiced_pcm()))
    assert caught.value.condition in ('no_generated_tokens', 'empty_text')


@pytest.mark.parametrize('kind', ['zero', 'unparseable', 'raw_unparseable'])
def test_mixed_windows_and_terminal_long_silent_tail_finalize(tmp_path, kind):
    pcm = voiced_pcm().ljust(300*32000, b'\0')
    tape = CompleteMixedTape(
        epoch=0, capacity_bytes=len(pcm), storage_root=tmp_path
    )
    tape.append(start_sample=0, pcm=pcm)
    decoder = Decoder(kind, first_text=True)
    final = TerminalTranscriptFinalizer(runner=WindowedRunner(decoder)).finalize(
        plan=plan_for(len(pcm)//2), tape=tape, base_text_revision_version=0)
    assert final.accounting.outcome.value == 'finalized'
    assert final.proposal is not None
    from moss_transcribe_diarize.app.live_session import LiveSession
    from tests.test_live_session import publish_prepared
    session = LiveSession(max_retained_samples=len(pcm)//2)
    publish_prepared(session, len(pcm)//2, 0, text='[0][S01]Initial[1]',
                     canonical_speakers=('speaker-a',), local_speakers=('S01',))
    outcome = session.apply_text_revision(final.proposal)
    assert outcome.applied and session.snapshot().finalization_status == 'final'
    assert session.snapshot().effective_transcript[0].text == 'Hello'
    assert decoder.calls == 3
    assert final.accounting.completed_windows == 3
    diagnostics = final.accounting.to_dict()['window_diagnostics']
    assert [d['window_index'] for d in diagnostics] == [1, 2]
    assert all(d['condition'] == ('speechless_window_empty' if kind == 'zero' else 'unparseable_speechless') for d in diagnostics)


def test_voiced_later_window_still_fails_mixed_job(tmp_path):
    pcm = bytes(120*32000) + voiced_pcm()
    with pytest.raises(WindowTranscriptionError) as caught:
        WindowedRunner(Decoder(first_text=True)).transcribe(wav(tmp_path / 'mixed.wav', pcm))
    assert caught.value.window_index == 1


@pytest.mark.parametrize('kind', ['zero', 'unparseable'])
def test_speechless_checkpoint_resumes_without_redecoding(tmp_path, kind):
    class Interrupt(Decoder):
        def transcribe(self, path, **kwargs):
            if self.calls == 2:
                raise RuntimeError('interrupted')
            return super().transcribe(path, **kwargs)
    pcm = voiced_pcm().ljust(300*32000, b'\0')
    source = wav(tmp_path / 'tape.wav', pcm)
    checkpoint = tmp_path / 'checkpoint'
    with pytest.raises(WindowTranscriptionError, match='decoder_exception'):
        WindowedRunner(Interrupt(kind, first_text=True)).transcribe(source, checkpoint_dir=checkpoint)
    decoder = Decoder(kind)
    result = WindowedRunner(decoder).transcribe(source, checkpoint_dir=checkpoint)
    assert decoder.calls == 1  # Speech window and first silent window came from checkpoint.
    assert result.completed_windows == 3 and 'Hello' in result.text
    assert [d['window_index'] for d in result.window_diagnostics] == [1, 2]


@pytest.mark.parametrize('kind', ['zero', 'unparseable', 'raw_unparseable'])
def test_unavailable_vad_cannot_turn_empty_decode_into_success(tmp_path, monkeypatch, kind):
    import sys
    monkeypatch.setitem(sys.modules, 'webrtcvad', None)
    with pytest.raises(WindowTranscriptionError, match='no_generated_tokens|unparseable_text'):
        WindowedRunner(Decoder(kind)).transcribe(wav(tmp_path / 'silent.wav', bytes(32000)))


@pytest.mark.parametrize('seconds, expected', [(120.5, 1), (240.5, 2), (121.0, 2)])
def test_short_redundant_tail_is_owned_by_previous_window(seconds, expected):
    from moss_transcribe_diarize.app.windowed_transcription import plan_windows
    windows = plan_windows(seconds)
    assert len(windows) == expected
    assert windows[0].own_start == 0 and windows[-1].own_end == seconds
    assert all(w.duration <= 150 for w in windows)
    assert all(a.own_end == b.own_start for a, b in zip(windows, windows[1:]))


def test_overload_tape_terminal_merges_half_second_tail(tmp_path):
    pcm = voiced_pcm().ljust(int(120.5*32000), b'\0')
    tape = CompleteMixedTape(
        epoch=0, capacity_bytes=len(pcm), storage_root=tmp_path
    )
    tape.append(start_sample=0, pcm=pcm)
    decoder = Decoder('unparseable', first_text=True)
    final = TerminalTranscriptFinalizer(runner=WindowedRunner(decoder)).finalize(
        plan=plan_for(len(pcm)//2), tape=tape, base_text_revision_version=0)
    assert final.accounting.outcome.value == 'finalized'
    assert decoder.calls == 1
    assert final.accounting.window_count == final.accounting.completed_windows == 1
    assert final.accounting.window_diagnostics[0]['condition'] == 'short_tail_window_merged'


@pytest.mark.parametrize('kind', ['unparseable', 'raw_unparseable'])
@pytest.mark.parametrize('seconds', [.5, 2])
def test_unparseable_speech_remains_failure_even_when_short(tmp_path, seconds, kind):
    pcm = voiced_pcm()[:int(seconds*32000)]
    with pytest.raises(WindowTranscriptionError, match='unparseable_text'):
        WindowedRunner(Decoder(kind)).transcribe(wav(tmp_path / 'speech.wav', pcm))


@pytest.mark.parametrize('kind', ['unparseable', 'raw_unparseable'])
@pytest.mark.parametrize('seconds', [.5, 2])
def test_unparseable_speechless_is_success_with_diagnostics(tmp_path, seconds, kind):
    result = WindowedRunner(Decoder(kind)).transcribe(
        wav(tmp_path / 'silence.wav', bytes(int(seconds*32000))))
    assert result.text == ''
    assert result.window_diagnostics[0]['condition'] == 'unparseable_speechless'
    assert result.window_diagnostics[0]['voiced_samples'] == 0
    assert 'not compact' not in str(result.window_diagnostics)
