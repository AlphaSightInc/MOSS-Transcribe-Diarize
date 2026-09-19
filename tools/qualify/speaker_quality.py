"""Source-reference speaker measurements for qualification, not model-derived truth."""
from collections import defaultdict

from moss_transcribe_diarize.lane_word_oracle import normalize_segment
from moss_transcribe_diarize.live_speaker_accuracy import Segment, score_live_speaker_accuracy

UNKNOWN = frozenset(('', 'S00', 'speaker-0000', 'unassigned'))


def score_speakers(reference_rows, hypothesis_rows):
    """Score stable source-time rows; unknown attribution cannot match a person.

    No offset fitting or forgiveness collar. References must be independently
    adjudicated. Coarse turn references are not a fine acoustic DER benchmark.
    The zero-participant witness is necessary, not sufficient, for release.
    """
    def segments(rows):
        return [Segment(r['start'], r['end'], r['speaker'], r.get('text', ''))
                for r in map(normalize_segment, rows) if r['end'] > r['start']]

    reference, hypothesis = segments(reference_rows), segments(hypothesis_rows)
    unknown = [s for s in hypothesis if s.speaker in UNKNOWN]
    assigned = [s for s in hypothesis if s.speaker not in UNKNOWN]
    result = score_live_speaker_accuracy(reference, assigned)
    seconds = defaultdict(float)
    for segment in reference:
        seconds[segment.speaker] += segment.end - segment.start
    result['reference_seconds_by_speaker'] = dict(seconds)
    result['unassigned_segments'] = len(unknown)
    result['unassigned_segment_seconds'] = sum(s.end - s.start for s in unknown)
    result['zero_correct_reference_speakers'] = [
        speaker for speaker, accuracy in result['speaker_correctness'].items() if accuracy == 0]
    result['participant_presence_witness'] = (
        'FAIL' if result['zero_correct_reference_speakers'] else 'PASS')
    result['qualification_scope'] = (
        'Source-time turn references; no collar or offset fitting; unknown identity '
        'counts as missing identity coverage. Participant presence alone is not quality acceptance.')
    return result
