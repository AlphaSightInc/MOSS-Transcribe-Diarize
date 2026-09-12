"""Content-free identity diagnosis must preserve unknowns and never advance evidence."""
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.phase2_acceptance_external import _quality_surface_observations


def test_album_counts_distinguish_admitted_from_provisional_without_reconciliation():
    provider = object.__new__(WeSpeakerLiveEvidenceProvider)
    provider._album = FingerprintAlbum()
    for speaker, duration in [('speaker-1', 1.1), ('speaker-2', 2.1)]:
        provider._album.observe(canonical_speaker=speaker, vector=(1., 0.), duration_sec=duration, span_id=1)
    provider._pending_vectors = {2: {'S01': ((0., 1.), 3.)}}
    expected = {'album_admitted_count': 1, 'provisional_only_count': 1}
    assert provider.identity_counts() == expected
    assert provider.identity_counts() == expected
    assert provider._pending_vectors == {2: {'S01': ((0., 1.), 3.)}}
    provider._album.observe(canonical_speaker='speaker-1', vector=(1., 0.), duration_sec=2.2, span_id=3)
    assert provider.identity_counts() == {'album_admitted_count': 2, 'provisional_only_count': 0}


def test_quality_projection_counts_labels_not_segments_and_retains_only_counts():
    capture = {'snapshot': {'identity_counts': {'identities_born_count': 3, 'album_admitted_count': 1,
        'provisional_only_count': 2, 'abstention_count': 4}, 'session': {'effective_transcript': [
            {'canonical_speaker': 'speaker-private', 'text': 'private words'},
            {'canonical_speaker': 'speaker-private', 'text': 'more private words'},
            {'canonical_speaker': None, 'text': 'unattributed words'},
        ]}}}
    captures = {key: capture for key in ['pre_stop_immediate', 'pre_stop_settled', 'post_stop_final']}
    result = _quality_surface_observations(captures, reference_speaker_count=2)
    for value in result.values():
        assert value['identity_counts'] == {'emitted_speaker_count': 1, 'reference_speaker_count': 2,
            'identities_born_count': 3, 'album_admitted_count': 1, 'provisional_only_count': 2,
            'abstention_count': 4, 'unattributed_segment_count': 1}
    assert 'private' not in str(result)


def test_missing_album_instrumentation_is_unknown_not_zero():
    capture = {'snapshot': {'session': {}}}
    captures = {key: capture for key in ['pre_stop_immediate', 'pre_stop_settled', 'post_stop_final']}
    counts = _quality_surface_observations(captures)['pre_stop_settled']['identity_counts']
    assert counts['album_admitted_count'] is None
    assert counts['provisional_only_count'] is None
    assert counts['abstention_count'] is None
