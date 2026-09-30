"""J8: the preview never re-shows words the reader already sees in the same lane.

Texts are from recorded gemini-3.5-transcribe-live (W3) streams replayed at $0
(round-3 diagnosis): long W3 chunks restart 40-100 words before the committed frontier,
and an interim often restates the final before it.
"""
import hashlib

from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiBase, GeminiLiveRuntime, GeminiPreview, GeminiRolling, GeminiSegment, ScriptedGeminiEngine)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_session import AudioFrame

R = 16000


def _runtime(tmp_path, seconds=60, lanes=False):
    descriptor = LiveServiceDescriptor(
        source_revision="test", provider_name="gemini", provider_revision="phase1-fake",
        provider_manifest_hash=hashlib.sha256(b"gemini").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=16000, max_queue_depth=4,
                                 max_retained_samples=32000, max_identity_speakers=8,
                                 max_events=64, max_tape_bytes=seconds * 32000),
        frame_samples=16000)
    rt = GeminiLiveRuntime(descriptor=descriptor, tape_storage_root=tmp_path,
                           engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
                               publish, batches=(), terminal=()))
    rt.create(session_id="one")
    for second in range(seconds):
        pcm = b"\0" * 32000
        rt.accept_frame("one", AudioFrame(second, pcm, 16000, lane_pcm=(
            (("system", pcm), ("microphone", pcm)) if lanes else ())))
    return rt


INTRO = "Thank you for subscribing to this channel. And now, dear friends, here's Keyu Jin. "
COMMITTED = (
    INTRO +
    "What is the single biggest misconception the West has about China's economy today? The "
    "biggest misunderstanding is somehow that a group of people or even just one person runs "
    "the entire Chinese economy. It is far from the reality. It is a very complex, large "
    "economy, and even if there is an extreme form of political centralization, the economy is "
    "totally decentralized. The role that the local")
FRESH = ("mayors, I call this the mayor economy, plays in reforms but also driving the "
         "technological innovation that we're seeing right now.")


def _commit(rt, text, through_s=45):
    rt.publish_update("one", GeminiBase(through_s * R, ()))
    rt.publish_update("one", GeminiRolling(0, through_s * R, (
        GeminiSegment(0, through_s * R, text, "speaker-0001", "system"),),
        revision_lanes=("system",)))


def _preview(rt, *texts):
    start = rt.snapshot("one").to_dict()["session"]["committed_samples"]
    rt.publish_update("one", GeminiPreview(60 * R, tuple(
        GeminiSegment(start + i, 60 * R, text, source_lane="system")
        for i, text in enumerate(texts))))
    return " ".join(s["text"] for s in
                    rt.snapshot("one").to_dict()["session"]["provisional"]["segments"])


def test_preview_trims_committed_head_longer_than_sixty_words(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED)
    head = COMMITTED[len(INTRO):]  # 65 committed words repeated by one W3 chunk
    assert _preview(rt, head + " " + FRESH) == FRESH


def test_preview_trims_head_when_frontier_words_differ_between_models(tmp_path):
    # W3 fuses/drops words right at the frontier ("isdecentralized", "Therole", "thelocal").
    rt = _runtime(tmp_path)
    _commit(rt, COMMITTED)
    w3 = (COMMITTED[len(INTRO):].replace("is totally decentralized. The role that the local",
                                         "isdecentralized. Therole that thelocal"))
    shown = _preview(rt, w3 + " " + FRESH)
    assert "single biggest misconception" not in shown
    assert shown.endswith(FRESH)
    assert len(shown.split()) <= len(FRESH.split()) + 4  # at most the fused frontier words


def test_preview_does_not_repeat_a_final_that_the_next_interim_restates(tmp_path):
    rt = _runtime(tmp_path)
    _commit(rt, "Earlier words that are already settled in the transcript.", through_s=10)
    final = ("existence of monopolies concentrated structures and according to traditional "
             "neoclassical economic theory the presence of monopolies is not a good thing.")
    shown = _preview(rt, final, final + " Let's")
    assert shown.count("neoclassical") == 1 and shown.endswith("Let's")


def test_restated_final_keeps_fresh_words_after_a_fused_frontier_word(tmp_path):
    # Recorded (acquired_rolex): the interim fuses "the very" -> "thevery"; the lone "the" of
    # "in the world" is chance, not repetition, and must not take the fresh words with it.
    rt = _runtime(tmp_path)
    _commit(rt, "Over a million people a year actually do buy one, and for an average price of",
            through_s=10)
    final = ("$13,000 each. That is until you walk out of the store and then they instantly "
             "become worth more, at least for a lot of the models these days. To your point "
             "about paradoxes of Rolex, this is one of the greatest ones. It is absolutely one "
             "of the")
    shown = _preview(rt, final, final + "very top top tier luxury brands in the")
    assert shown.count("paradoxes") == 1
    assert shown.endswith("top top tier luxury brands in the")


def test_new_interim_sharing_a_phrase_with_shown_text_is_kept_whole(tmp_path):
    # Recorded (lex_bill_ackman 5 m): the new interim's last five words also occur in the
    # preview kept before it; a match that leaves the head unmatched is not a repeated head.
    rt = _runtime(tmp_path)
    _commit(rt, "And basically, he says that you have to understand the difference between "
                "price and value, right? Price is what you pay, value is what you get.")
    earlier = ("makes you a great offer, you can take it. And that's the stock market. And the "
               "key is to figure out what something's worth, and you have to kind of weigh it.")
    new = "talked about the difference between between the stock market and the"
    assert _preview(rt, earlier, new) == earlier + " " + new


def test_degraded_commit_keeps_lanes_so_preview_and_rolling_replace_it(tmp_path):
    # R1: preview words committed by the lag fallback carry their capture lane.
    rt = _runtime(tmp_path, lanes=True)
    said = ("Andrew Scull has spent decades studying how societies have understood madness "
            "and its treatment")
    rt.publish_update("one", GeminiBase(20 * R, (
        GeminiSegment(0, 20 * R, said, None, "system"),), degraded=True))
    rows = rt.snapshot("one").to_dict()["session"]["effective_transcript"]
    assert [(row["text"], row["source_lane"]) for row in rows] == [(said, "system")]
    # The same W3 chunk is still in the preview: only its new words are shown.
    rt.publish_update("one", GeminiPreview(25 * R, (GeminiSegment(
        20 * R, 25 * R, said + ". In this conversation we trace", source_lane="system"),)))
    assert [row["text"] for row in
            rt.snapshot("one").to_dict()["session"]["provisional"]["segments"]] == [
        "In this conversation we trace"]
    # Rolling later covers that audio with a named speaker: no unattributed copy remains.
    rt.publish_update("one", GeminiBase(30 * R, ()))
    rt.publish_update("one", GeminiRolling(0, 30 * R, (
        GeminiSegment(0, 20 * R, said, "speaker-0001", "system"),),
        revision_lanes=("system", "microphone")))
    rows = rt.snapshot("one").to_dict()["session"]["effective_transcript"]
    assert [(row["text"], row["canonical_speaker"]) for row in rows] == [(said, "speaker-0001")]
