"""PROTOTYPE (issue #15) - time a speaker rename on a long saved Live meeting.

Question: where does a post-Stop rename spend its time, and does the Account-wide
identity lock make other naming (and Live publication) wait for it?

Real paths: MeetingAudioArchive mp3 publish, Phase2Store SQLite, AccountSpeakerIdentity
name_speaker, AlbumIdentityResolver.enrollment_observation with the pinned WeSpeaker ONNX
(3 interval workers, as phase2_web_cli wires it). Audio: public long60 fixture tiled to N
minutes; rows: its reference split into <=5 s pieces (live rows average ~4.4 s). $0.

Run from the worktree root:
  PYTHONDONTWRITEBYTECODE=1 MOSS_TEST_REAL_SQLITE=1 <venv python> \
      prototypes/rename-latency/measure.py --minutes 60 150
"""
from __future__ import annotations

import argparse
import asyncio
import json
import resource
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app import windowed_transcription  # noqa: E402
from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver  # noqa: E402
from moss_transcribe_diarize.app.live_provider_bundle import (  # noqa: E402
    LiveProviderBundleConfig, _identity_encoder)
from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive  # noqa: E402
from moss_transcribe_diarize.app.phase2_speaker_identity import AccountSpeakerIdentity  # noqa: E402
from tests.phase2.test_manual_speaker_voiceprints import provision  # noqa: E402

LONG60 = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live/"
              "prototypes/gemini-live/.cache/long60/audio.wav")
REFERENCE = ROOT / "prototypes/gemini-live/window/long60/reference.jsonl"
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
R = 16000


def build(minutes: float, directory: Path):
    with wave.open(str(LONG60), "rb") as source:
        pcm = source.readframes(source.getnframes())
    base = len(pcm) / 2 / R
    reference = [json.loads(line) for line in REFERENCE.read_text().splitlines()]
    ids = {name: f"speaker-{i:04d}" for i, name in enumerate(dict.fromkeys(r["speaker"] for r in reference), 1)}
    total = minutes * 60
    wav = directory / "meeting.wav"
    rows = []
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(R)
        offset = 0.0
        while offset < total:
            take = min(base, total - offset)
            out.writeframes(pcm[: int(take * R) * 2])
            for row in reference:
                start = float(row["start"])
                while start < min(float(row["end"]), take):
                    end = min(start + 5.0, float(row["end"]), take)
                    rows.append({"id": f"seg_{len(rows):05d}", "start": round(offset + start, 3),
                                 "end": round(offset + end, 3), "speaker": row["speaker"],
                                 "speaker_entity_id": ids[row["speaker"]],
                                 "source_lane": "system", "text": "x " * 12})
                    start = end
            offset += take
    return wav, rows, ids


class Timed:
    def __init__(self):
        self.parts = {}

    def wrap(self, owner, name, key):
        original = getattr(owner, name)

        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.parts[key] = self.parts.get(key, 0.0) + time.perf_counter() - started
        setattr(owner, name, timed)


async def run(minutes: float) -> None:
    config = LiveProviderBundleConfig.from_manifest(MANIFEST)
    encoder = _identity_encoder(config, interval_workers=3)
    resolver = AlbumIdentityResolver(config=config, encoder=encoder)
    timed = Timed()
    timed.wrap(windowed_transcription, "extract_window_wav", "ffmpeg_decode_s")
    timed.wrap(encoder, "embed", "wespeaker_embed_s")
    encoder.preflight()  # load the ONNX session outside the timed request
    with tempfile.TemporaryDirectory(prefix="rename-latency-", dir=ROOT / ".wp9runtime") as tmp:
        tmp = Path(tmp)
        wav, rows, ids = build(minutes, tmp)
        store, workspace, _ = await provision(tmp / "db.sqlite")
        archive = MeetingAudioArchive(tmp / "meetings")
        identity = AccountSpeakerIdentity(store, None, audio_archive=archive,
                                          live_evidence=resolver.enrollment_observation)
        try:
            meeting = await workspace.create_meeting("live")
            started = time.perf_counter()
            audio = await meeting.publish_audio(archive, wav)
            publish_s = time.perf_counter() - started
            await meeting.finish_with_transcript({"segments": rows}, "completed")
            small = await workspace.create_meeting("live")
            await small.finish_with_transcript({"segments": rows[:4]}, "completed")
            per = {}
            for row in rows:
                per.setdefault(row["speaker_entity_id"], [0, 0.0])
                per[row["speaker_entity_id"]][0] += 1
                per[row["speaker_entity_id"]][1] += row["end"] - row["start"]
            target = max(per, key=lambda key: per[key][1])
            print(f"\n=== {minutes:g} min meeting: {len(rows)} rows, mp3 {audio.byte_count/1e6:.1f} MB "
                  f"(publish {publish_s:.1f}s); target {target}: {per[target][0]} rows, "
                  f"{per[target][1]/60:.1f} min speech", flush=True)
            bank = identity.bank(workspace)

            async def rename(label, save):
                t = time.perf_counter()
                named = await bank.name_speaker(meeting, target, label, save_voiceprint=save)
                return named, time.perf_counter() - t
            for attempt, save in ((1, True), (2, True), (3, False)):
                timed.parts.clear()
                rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
                other_wait = publication_wait = None
                if attempt == 1:
                    # Live publication of any active meeting enters the same identity lock.
                    async def publish():
                        await asyncio.sleep(0.5)
                        t = time.perf_counter()
                        async with identity.publication(small, ()):
                            pass
                        return time.perf_counter() - t
                    result, publication_wait = await asyncio.gather(
                        rename(f"Name{attempt}", save), publish())
                elif attempt == 2:
                    # A tiny rename of another meeting, queued 0.5 s later.
                    async def other():
                        await asyncio.sleep(0.5)
                        t = time.perf_counter()
                        await bank.name_speaker(small, rows[0]["speaker_entity_id"], "Other", save_voiceprint=False)
                        return time.perf_counter() - t
                    result, other_wait = await asyncio.gather(
                        rename(f"Name{attempt}", save), other())
                else:
                    result = await rename(f"Name{attempt}", save)
                if hasattr(identity, "_saved_enrollments"):  # after the fix: time the background work too
                    background = time.perf_counter()
                    await identity.shutdown()
                    timed.parts["background_s"] = time.perf_counter() - background
                result, elapsed = result
                voiceprints = [(v.label, v.sample_count) for v in await bank.list_voiceprints()]
                rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
                print(f"rename#{attempt} save_voiceprint={save}: {elapsed:.2f}s enrollment={result.enrollment} "
                      f"parts={ {k: round(v, 2) for k, v in timed.parts.items()} } "
                      f"other_meeting_rename_s={None if other_wait is None else round(other_wait, 2)} "
                      f"live_publication_wait_s={None if publication_wait is None else round(publication_wait, 2)} "
                      f"voiceprints={voiceprints} peak_rss_mb {rss0:.0f}->{rss1:.0f}", flush=True)
        finally:
            await store.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, nargs="+", default=[60.0])
    args = parser.parse_args()
    (ROOT / ".wp9runtime").mkdir(exist_ok=True)
    for minutes in args.minutes:
        asyncio.run(run(minutes))


if __name__ == "__main__":
    main()
