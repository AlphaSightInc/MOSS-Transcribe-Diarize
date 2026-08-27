from importlib import import_module

from .subtitle import (
    SubtitleSegment,
    SubtitleStyle,
    coerce_subtitle_segments,
    export_ass,
    export_json,
    export_srt,
    normalize_segments,
    subtitle_segments_from_transcript,
)
from .transcript_parser import (
    TranscriptParseError,
    TranscriptSegment,
    TranscriptStreamParser,
    iter_transcript_segments,
    parse_transcript,
)

__all__ = [
    "SubtitleSegment",
    "SubtitleStyle",
    "TranscriptParseError",
    "TranscriptSegment",
    "TranscriptStreamParser",
    "MossTranscribeDiarizeConfig",
    "MossTranscribeDiarizeForConditionalGeneration",
    "MossTranscribeDiarizeModel",
    "MossTranscribeDiarizePreTrainedModel",
    "MossTranscribeDiarizeProcessor",
    "VQAdaptor",
    "coerce_subtitle_segments",
    "export_ass",
    "export_json",
    "export_srt",
    "iter_transcript_segments",
    "normalize_segments",
    "parse_transcript",
    "subtitle_segments_from_transcript",
]

_LAZY_EXPORTS = {
    "MossTranscribeDiarizeConfig": ".configuration_moss_transcribe_diarize",
    "MossTranscribeDiarizeForConditionalGeneration": ".modeling_moss_transcribe_diarize",
    "MossTranscribeDiarizeModel": ".modeling_moss_transcribe_diarize",
    "MossTranscribeDiarizePreTrainedModel": ".modeling_moss_transcribe_diarize",
    "MossTranscribeDiarizeProcessor": ".processing_moss_transcribe_diarize",
    "VQAdaptor": ".modeling_moss_transcribe_diarize",
}


def __getattr__(name: str):
    """Keep public remote-code imports compatible without making admin require Torch."""

    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
