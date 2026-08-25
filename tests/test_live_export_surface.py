"""T3 tests for the live export (plan §10.5 step 7, §14 T3 "export text equals visible
effective text").

The export is `hypothesis_from_live_snapshot`: the one place that turns a served live snapshot
into the transcript downstream consumers score, save and read. Since step 7 it reads the
`effective_transcript` surface -- the words a reader was actually shown -- rather than
re-deriving a transcript from the committed spans, which is what makes the plan's §1.2 promise
("export and the visible transcript use the same terminal surface") checkable rather than
aspirational.

Two of these tests drive the real thing end to end: a real runtime with a scripted rolling
witness produces the payload, and the portal page the service serves renders it in the T2
tier's headless browser. The rest are the boundary conditions that payload cannot reach.
"""

from __future__ import annotations

import unittest

from test_live_portal import _run_node_probe
from test_live_rolling_wiring import (
    ONE_WINDOW_FRAMES,
    _decoders,
    _run_meeting,
    _runtime,
)

# Long enough that one rolling window has replaced the opening and the base still owns the
# tail: the surface then carries both authorities, which is the shape a reader of a live
# meeting is looking at most of the time and the only one where "replaced" and "appended"
# differ.
MIXED_SURFACE_FRAMES = ONE_WINDOW_FRAMES + 8

from moss_transcribe_diarize.app.live_portal import LIVE_PORTAL_HTML
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE, UNATTRIBUTED_SPEAKER
from moss_transcribe_diarize.live_speaker_accuracy import hypothesis_from_live_snapshot
from moss_transcribe_diarize.transcript_parser import parse_transcript


def served_snapshot(*, rolling: bool, frames: int = ONE_WINDOW_FRAMES) -> dict:
    """One real meeting through the real runtime, as the snapshot route would serve it."""

    base, witness = _decoders(rolling=rolling)
    runtime = _runtime(base=base, rolling=witness)
    session_id = _run_meeting(runtime, frames=frames)
    return runtime.snapshot(session_id).to_dict()


def export(payload: dict, *, duration_sec: float = 60.0, start_sample: int = 0):
    return hypothesis_from_live_snapshot(
        {"snapshot": payload}, corpus_start_sample=start_sample, corpus_duration_sec=duration_sec
    )


def rendered_transcript(payload: dict) -> str:
    """What the served portal puts in the transcript node for this snapshot."""

    served = [
        {"payload": {"snapshot": payload}, "ok": True, "status": 200},
        {"payload": {"events": []}, "ok": True, "status": 200},
    ]
    probe = _run_node_probe(LIVE_PORTAL_HTML, "servedPolls", served)
    return probe["transcriptAfterEachPoll"][-1]


def snapshot_payload(
    surface: list[dict] | None,
    *,
    committed: list[dict] | None = None,
    canonical_speakers: tuple[str, ...] = ("speaker-0001", "speaker-0002"),
) -> dict:
    session: dict = {
        "identity_snapshot": {"version": 1, "canonical_speakers": list(canonical_speakers)},
        "committed": committed if committed is not None else [],
    }
    if surface is not None:
        session["effective_transcript"] = surface
    return {"session": session}


def surface_segment(
    start: int, end: int, text: str, speaker: str | None, authority: str = "rolling"
) -> dict:
    return {
        "start_sample": start,
        "end_sample": end,
        "text": text,
        "canonical_speaker": speaker,
        "authority": authority,
    }


def commit(start: int, end: int, transcript: str, revised: str | None = None) -> dict:
    return {
        "span_id": start // LIVE_SAMPLE_RATE,
        "start_sample": start,
        "end_sample": end,
        "transcript": transcript,
        "revised_transcript": revised,
    }


class ExportIsTheVisibleSurfaceTest(unittest.TestCase):
    def test_the_export_is_what_the_reader_saw(self):
        """Plan §14 T3: export text equals visible effective text.

        One meeting, two readers: the export reads the served snapshot, the portal page
        renders the same one in the headless browser, and the screen is parsed back with the
        production parser. Speaker, words and seconds must agree segment for segment --
        anything else means the file and the screen disagree about a meeting that happened.
        """

        payload = served_snapshot(rolling=True, frames=MIXED_SURFACE_FRAMES)
        self.assertGreater(payload["session"]["text_revision_version"], 0)
        # Not a vacuous comparison: a surface of one authority could not tell a page that
        # replaces its prefix from one that appends to it.
        self.assertEqual(
            {segment["authority"] for segment in payload["session"]["effective_transcript"]},
            {"rolling", "provisional"},
        )

        exported = export(payload)
        on_screen = [
            item
            for row in rendered_transcript(payload).split("\n\n")
            for item in parse_transcript(row)
        ]

        self.assertEqual(len(exported), len(on_screen))
        self.assertGreater(len(exported), 0)
        for shown, written in zip(on_screen, exported):
            self.assertEqual(written.speaker, shown.speaker)
            self.assertEqual(written.text, shown.text)
            self.assertAlmostEqual(written.start, shown.start, places=6)
            self.assertAlmostEqual(written.end, shown.end, places=6)

    def test_the_export_publishes_the_revision_and_not_the_words_it_replaced(self):
        """A reader watched the words change; the file must not restore the old ones."""

        payload = snapshot_payload(
            [surface_segment(0, LIVE_SAMPLE_RATE, "what the witness heard", "speaker-0001")],
            committed=[commit(0, LIVE_SAMPLE_RATE, "[0][S01]what the short span heard[1]")],
        )
        exported = export(payload)

        self.assertEqual([item.text for item in exported], ["what the witness heard"])

    def test_a_session_with_no_revision_exports_what_its_committed_spans_always_did(self):
        """The surface reading is not a second opinion: with no witness, the two agree.

        The same real meeting is exported twice -- once as served, once with the surface
        removed so the export falls back to re-parsing the committed spans. Sample-derived
        seconds and parsed seconds are not the same arithmetic, so the tolerance is one
        sample; the words and the speakers must match exactly.
        """

        payload = served_snapshot(rolling=False)
        self.assertEqual(payload["session"]["text_revision_version"], 0)

        from_surface = export(payload)
        without_surface = dict(payload)
        without_surface["session"] = {
            key: value
            for key, value in payload["session"].items()
            if key != "effective_transcript"
        }
        from_commits = export(without_surface)

        self.assertGreater(len(from_surface), 0)
        self.assertEqual(len(from_surface), len(from_commits))
        for surfaced, committed in zip(from_surface, from_commits):
            self.assertEqual(surfaced.text, committed.text)
            self.assertEqual(surfaced.speaker, committed.speaker)
            self.assertLessEqual(abs(surfaced.start - committed.start), 1.0 / LIVE_SAMPLE_RATE)
            self.assertLessEqual(abs(surfaced.end - committed.end), 1.0 / LIVE_SAMPLE_RATE)

    def test_an_older_snapshot_without_a_surface_still_exports_its_corrected_labels(self):
        """The fallback is the whole of the old reading, `revised_transcript` first."""

        payload = snapshot_payload(
            None,
            committed=[
                commit(
                    0,
                    LIVE_SAMPLE_RATE,
                    "[0][S01]who spoke was wrong[1]",
                    revised="[0][S02]who spoke was wrong[1]",
                )
            ],
        )
        exported = export(payload)

        self.assertEqual([(item.speaker, item.text) for item in exported], [("S02", "who spoke was wrong")])

    def test_nobody_attributed_and_nobody_established_both_export_as_the_unattributed_token(self):
        """Two ways of not knowing who spoke, one honest answer, never a guess."""

        payload = snapshot_payload(
            [
                surface_segment(0, LIVE_SAMPLE_RATE, "nobody attributed", None),
                surface_segment(LIVE_SAMPLE_RATE, 2 * LIVE_SAMPLE_RATE, "never established", "speaker-0009"),
                surface_segment(2 * LIVE_SAMPLE_RATE, 3 * LIVE_SAMPLE_RATE, "second speaker", "speaker-0002"),
            ]
        )
        exported = export(payload)

        self.assertEqual(
            [item.speaker for item in exported],
            [UNATTRIBUTED_SPEAKER, UNATTRIBUTED_SPEAKER, "S02"],
        )

    def test_the_export_is_clamped_to_the_corpus_and_drops_what_falls_outside_it(self):
        """A corpus window is what the reference covers; the export may not run past it."""

        payload = snapshot_payload(
            [
                surface_segment(0, LIVE_SAMPLE_RATE, "before the window", "speaker-0001"),
                surface_segment(LIVE_SAMPLE_RATE, 3 * LIVE_SAMPLE_RATE, "across the end", "speaker-0001"),
                surface_segment(4 * LIVE_SAMPLE_RATE, 5 * LIVE_SAMPLE_RATE, "past the end", "speaker-0001"),
            ]
        )
        exported = export(payload, duration_sec=2.0, start_sample=LIVE_SAMPLE_RATE)

        self.assertEqual(
            [(item.start, item.end, item.text) for item in exported],
            [(0.0, 2.0, "across the end")],
        )

    def test_whitespace_only_words_are_not_a_segment(self):
        payload = snapshot_payload(
            [
                surface_segment(0, LIVE_SAMPLE_RATE, "   ", "speaker-0001"),
                surface_segment(LIVE_SAMPLE_RATE, 2 * LIVE_SAMPLE_RATE, "said something", "speaker-0001"),
            ]
        )

        self.assertEqual([item.text for item in export(payload)], ["said something"])

    def test_a_malformed_surface_is_refused_by_name(self):
        malformed_list = snapshot_payload(None)
        malformed_list["session"]["effective_transcript"] = {"segments": []}
        cases = {
            "not a list": malformed_list,
            "item not an object": snapshot_payload(["a segment"]),
            "negative sample": snapshot_payload(
                [surface_segment(-1, LIVE_SAMPLE_RATE, "x", None)]
            ),
            "empty interval": snapshot_payload(
                [surface_segment(LIVE_SAMPLE_RATE, LIVE_SAMPLE_RATE, "x", None)]
            ),
            "text not a string": snapshot_payload(
                [{"start_sample": 0, "end_sample": 1, "canonical_speaker": None, "text": 7}]
            ),
            "speaker not a string": snapshot_payload(
                [{"start_sample": 0, "end_sample": 1, "canonical_speaker": 7, "text": "x"}]
            ),
        }
        for name, payload in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                export(payload)

    def test_a_surface_without_an_identity_snapshot_is_refused(self):
        payload = snapshot_payload([surface_segment(0, LIVE_SAMPLE_RATE, "x", "speaker-0001")])
        del payload["session"]["identity_snapshot"]

        with self.assertRaises(ValueError):
            export(payload)


if __name__ == "__main__":
    unittest.main()
