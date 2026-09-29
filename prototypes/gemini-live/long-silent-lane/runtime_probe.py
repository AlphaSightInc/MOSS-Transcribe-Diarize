"""Same delayed lane probe via the real GeminiLiveRuntime/LiveSession."""
import hashlib
import tempfile
import time
from pathlib import Path

from probe import Diarizer, Source, Terminal, RATE
from moss_transcribe_diarize.app.gemini_hybrid_engine import (GeminiHybridEngine,
    GrowingContextWindowScheduler, OverlapRegistry)
from moss_transcribe_diarize.app.gemini_lane_engine import LaneGeminiEngine
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiLiveRuntime
from moss_transcribe_diarize.app.live_service_runtime import (LiveServiceBounds,
    LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_session import AudioFrame

def run(mode):
    system, mic = Diarizer(True, failure_mode=mode), Diarizer(False)
    frame_samples = 15*RATE
    descriptor = LiveServiceDescriptor(source_revision="probe", provider_name="gemini",
        provider_revision="fake", provider_manifest_hash=hashlib.sha256(b"fake").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=frame_samples, max_queue_depth=16,
            max_retained_samples=60*RATE, max_identity_speakers=16,
            max_events=10000, max_tape_bytes=2610*RATE*2), frame_samples=frame_samples)
    with tempfile.TemporaryDirectory() as root:
        engines = []
        def factory(_sid, publish, _usage):
            engine = LaneGeminiEngine(publish, tape_root=Path(root),
                system_factory=lambda callback: GeminiHybridEngine(callback,
                    word_source=Source(True), window_scheduler=GrowingContextWindowScheduler(
                        max_seconds=90, stride_seconds=15), registry=OverlapRegistry(),
                    diarizer=system, terminal=Terminal(), source_lane="system",
                    voiced_audio=lambda pcm: True),
                microphone_factory=lambda callback: GeminiHybridEngine(callback,
                    word_source=Source(False), window_scheduler=GrowingContextWindowScheduler(
                        max_seconds=30, stride_seconds=15), registry=OverlapRegistry(),
                    diarizer=mic, terminal=Terminal(), source_lane="microphone",
                    voiced_audio=lambda pcm: False, diarize_windows=False))
            engines.append(engine)
            return engine
        rt = GeminiLiveRuntime(descriptor=descriptor, engine_factory=factory,
            tape_storage_root=Path(root))
        rt.create(session_id="one")
        audio = b"\x01\x00"*frame_samples
        silence = bytes(len(audio))
        for i in range(174):
            rt.accept_frame("one", AudioFrame(i, audio, frame_samples,
                lane_pcm=(("system", audio), ("microphone", silence))))
            if mode and system.blocked.is_set() and not system.release.is_set() and i >= 52:
                system.release.set()
            time.sleep(.003)
        engine = engines[0]
        for lane in engine.LANES:
            future = engine._engines[lane]._future
            if future: future.result(timeout=60)
        snap = rt.snapshot("one").session
        print({"mode": mode, "status": snap.status, "accepted_s": snap.accepted_samples/RATE,
            "committed_s": snap.committed_samples/RATE, "public_frontier_s": engine._frontier/RATE,
            "last_label_s": max((r.end_sample for r in snap.effective_transcript
                if r.canonical_speaker), default=0)/RATE,
            "system_calls": system.calls, "mic_calls": mic.calls})
        engine.close()

if __name__ == "__main__":
    run("slow")
    run("raise")
