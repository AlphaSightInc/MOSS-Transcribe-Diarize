"""File-window identity composed from ADR-0002's existing live album and sweep.

A local label identifies a voice only within its window. Match it to one canonical
album entry, retain the evidence, then revisit earlier labels with the final album.
The encoder also retains each interval vector before reducing that local label to a
mean. Once the album is final, those already-computed vectors get one terminal match:
confident evidence may repair a mixed decoder label; ambiguous evidence becomes S00.
No audio is re-embedded and a window-level abstention remains authoritative.
The resolver owns per-call state; shared runners never share meeting identities.
"""
from __future__ import annotations

from array import array
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
from typing import Any

from .live_identity import LiveIdentityError, LiveSpeakerEvidence, assign_speakers
from .live_identity_album import cosine_similarity
from .live_identity_sweep import LiveIdentitySweeper
from .live_provider_bundle import (
    LiveProviderBundleConfig, _birth_min_seconds, _fingerprint_album,
    _identity_config, _identity_encoder, _vector_values,
)
from .speaker_identity import IdentityResolution, _mean_unit_vector


class AlbumIdentityResolver:
    requires_window_audio = True

    def __init__(self, *, manifest_path: str | Path | None = None,
                 config: LiveProviderBundleConfig | None = None, encoder: Any = None):
        self.manifest_path = Path(manifest_path) if manifest_path is not None else (
            Path.home() / '.local/share/moss-transcribe-diarize/live/live-provider-manifest.json'
        )
        self._config = config
        self._encoder = encoder

    def _providers(self):
        if self._config is None:
            self._config = LiveProviderBundleConfig.from_manifest(self.manifest_path)
        if self._encoder is None:
            # WP28 measured four independent probes at once; identity stays serial.
            self._encoder = _identity_encoder(self._config, interval_workers=4)
        return self._config, self._encoder

    def contract(self) -> dict[str, Any]:
        config, encoder = self._providers()
        return {
            'schema_version': 3, 'resolver': 'album',
            'config': dict(config.identity_config),
            'provider': dict(config.identity_provider),
            'encoder': dict(encoder.descriptor),
        }

    def enrollment_observation(self, audio_path, segments):
        """Reconstruct requested file evidence from retained audio; no saved schema change."""
        from .live_provider_bundle import LiveSpeakerJournalObservation
        from .windowed_transcription import extract_window_wav

        config, encoder = self._providers()
        intervals = [(max(0.0, s['start']), s['end']) for s in segments
                     if round((s['end'] - max(0.0, s['start'])) * 16000)
                     >= config.identity_provider['min_segment_samples']]
        duration = sum(end - start for start, end in intervals)
        album = _fingerprint_album(config.identity_provider)
        if duration < album.admission_seconds:
            return None
        with tempfile.TemporaryDirectory(prefix='file-enrollment-') as directory:
            wav = Path(directory) / 'audio.wav'
            extract_window_wav(audio_path, wav, start_seconds=0,
                               duration_seconds=max(end for _, end in intervals))
            vector = encoder.embed(wav, intervals)
        album.observe(canonical_speaker='requested', vector=vector,
                      duration_sec=duration, span_id=0)
        reference = album.reference('requested')
        if reference is None:
            return None
        spec = encoder.spec
        return LiveSpeakerJournalObservation(
            speaker_label='requested', centroid=reference, sample_seconds=duration,
            exemplar_count=album.exemplar_count('requested'), provisional=False,
            embedder_id=f'{spec.provider}:{spec.revision}', embedder_state_sha=spec.state_sha256,
        )

    def resolve(self, windows, local_results, *, window_audio_paths) -> IdentityResolution:
        config, encoder = self._providers()
        policy = _identity_config(config.identity_config)
        album = _fingerprint_album(config.identity_provider)
        sweeper = LiveIdentitySweeper(album=album, config=policy)
        labels = {}
        interval_vectors = {}
        states = []
        for window, segments, path in zip(windows, local_results, window_audio_paths, strict=True):
            local = tuple(dict.fromkeys(s.speaker for s in segments if s.speaker != 'S00'))
            vectors = {}
            durations = {}
            evidence = []
            reason = 'ok'
            try:
                for speaker in local:
                    selected = [
                        (index, max(0.0, s.start), min(window.duration, s.end))
                        for index, s in enumerate(segments) if s.speaker == speaker
                        and round((min(window.duration, s.end) - max(0.0, s.start)) * 16000)
                        >= config.identity_provider['min_segment_samples']
                    ]
                    intervals = [(start, end) for _, start, end in selected]
                    durations[speaker] = sum(end - start for start, end in intervals)
                    if not intervals:
                        continue
                    embedded = [_vector_values(vector) for vector in encoder.embed_intervals(path, intervals)]
                    if len(embedded) != len(selected):
                        raise ValueError('identity encoder omitted an eligible interval')
                    vectors[speaker] = _vector_values(_mean_unit_vector(embedded))
                    for (segment_index, _, _), vector in zip(selected, embedded, strict=True):
                        # This map lives until the final album exists. Float32 keeps a
                        # 200-minute file near 4 MiB instead of retaining Python-float tuples.
                        interval_vectors[window.index, segment_index] = array('f', vector)
                    for canonical in album.speakers():
                        score = cosine_similarity(vectors[speaker], album.reference(canonical))
                        if score is not None:
                            evidence.append(LiveSpeakerEvidence(speaker, canonical, score))
            except Exception as exc:
                # Same failure boundary as the live preparer: keep words, abstain on
                # this window, and retain no partial evidence as canonical authority.
                vectors = {}
                for key in [key for key in interval_vectors if key[0] == window.index]:
                    del interval_vectors[key]
                durations = {speaker: 0.0 for speaker in local}
                reason = f'evidence_provider_failed:{type(exc).__name__}'
            try:
                if reason != 'ok':
                    raise LiveIdentityError(reason)
                if len(local) > policy.max_speakers:
                    raise LiveIdentityError('speaker_capacity_exceeded')
                mapping = dict(assign_speakers(
                    local_speakers=local, canonical_speakers=album.speakers(),
                    evidence=tuple(evidence), config=policy,
                ))
                births = [s for s in local if s not in mapping
                          and durations[s] >= _birth_min_seconds(config.identity_provider)]
                if len(album.speakers()) + len(births) > policy.max_speakers:
                    raise LiveIdentityError('speaker_capacity_exceeded')
                for index, speaker in enumerate(births, start=len(album.speakers()) + 1):
                    mapping[speaker] = f'S{index:02d}'
            except LiveIdentityError as exc:
                mapping = {}
                reason = str(exc)
            admissions = {}
            for speaker, vector in vectors.items():
                if speaker in mapping:
                    admissions[speaker] = album.observe(
                        canonical_speaker=mapping[speaker], vector=vector,
                        duration_sec=durations[speaker], span_id=window.index,
                    )
                sweeper.record(
                    span_id=window.index, local_speaker=speaker,
                    canonical_speaker=mapping.get(speaker), vector=vector,
                    duration_sec=durations[speaker],
                )
            labels.update({(window.index, s): mapping.get(s, 'S00') for s in local})
            states.append(dict(
                window=window.index, reason=reason, mapping=mapping, durations=durations,
                admissions=admissions, scores=[asdict(item) for item in evidence],
                album={s: dict(exemplars=album.exemplar_count(s), provisional=album.has_provisional(s))
                       for s in album.speakers()},
            ))
        revision = sweeper.sweep_now()
        for correction in revision.corrections:
            labels[correction.span_id, correction.local_speaker] = correction.canonical_speaker
        references = {speaker: album.reference(speaker) for speaker in album.speakers()}
        refinement = dict(evaluated=0, reassigned=0, abstained=0, unchanged=0)
        relabeled = []
        state_by_window = {state['window']: state for state in states}
        for window, segments in zip(windows, local_results, strict=True):
            group = []
            for index, segment in enumerate(segments):
                current = labels.get((window.index, segment.speaker), 'S00')
                vector = interval_vectors.get((window.index, index))
                # A whole-window abstention is a stronger ruling than one interval score.
                # Refinement repairs mixed labels only after the causal window was accepted.
                if vector is None or not references or state_by_window[window.index]['reason'] != 'ok':
                    group.append(replace(segment, speaker=current))
                    continue
                refinement['evaluated'] += 1
                evidence = tuple(
                    LiveSpeakerEvidence('__interval__', canonical, score)
                    for canonical, reference in references.items()
                    if (score := cosine_similarity(vector, reference)) is not None
                )
                try:
                    terminal = dict(assign_speakers(
                        local_speakers=('__interval__',), canonical_speakers=tuple(references),
                        evidence=evidence, config=policy,
                    )).get('__interval__')
                except LiveIdentityError:
                    terminal = None
                final = terminal or 'S00'
                if terminal is None:
                    refinement['abstained'] += 1
                elif terminal == current:
                    refinement['unchanged'] += 1
                else:
                    refinement['reassigned'] += 1
                group.append(replace(segment, speaker=final))
            relabeled.append(group)
        return IdentityResolution(
            relabeled_results=relabeled,
            summary=dict(resolver='album', canonical_speakers=len({s.speaker for g in relabeled for s in g if s.speaker != 'S00'}),
                         unattributed_segments=sum(s.speaker == 'S00' for g in relabeled for s in g)),
            diagnostics=dict(schema_version=3, contract=self.contract(), windows=states,
                             sweep=revision.to_dict(), interval_refinement=refinement),
        )
