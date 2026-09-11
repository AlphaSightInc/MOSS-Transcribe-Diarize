"""Optional legacy torch-runtime compatibility, outside the required Phase-2 API gate."""
import pytest


def test_top_level_legacy_model_exports_remain_importable():
    pytest.importorskip("torch", reason="legacy model exports require the torch-runtime extra")
    from moss_transcribe_diarize import (
        MossTranscribeDiarizeConfig,
        MossTranscribeDiarizeForConditionalGeneration,
        MossTranscribeDiarizeModel,
        MossTranscribeDiarizePreTrainedModel,
        MossTranscribeDiarizeProcessor,
        VQAdaptor,
    )
    from moss_transcribe_diarize.configuration_moss_transcribe_diarize import (
        MossTranscribeDiarizeConfig as DirectConfig,
    )

    assert MossTranscribeDiarizeConfig is DirectConfig
    assert {
        MossTranscribeDiarizeForConditionalGeneration.__name__,
        MossTranscribeDiarizeModel.__name__,
        MossTranscribeDiarizePreTrainedModel.__name__,
        MossTranscribeDiarizeProcessor.__name__,
        VQAdaptor.__name__,
    } == {
        "MossTranscribeDiarizeForConditionalGeneration",
        "MossTranscribeDiarizeModel",
        "MossTranscribeDiarizePreTrainedModel",
        "MossTranscribeDiarizeProcessor",
        "VQAdaptor",
    }

