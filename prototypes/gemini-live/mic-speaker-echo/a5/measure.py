"""Replay actual publication transitions; print full relevant state and frozen gates."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/gemini")]
import test_gemini_preview_duplication as tests
from moss_transcribe_diarize.app import gemini_live_runtime as rt
import replacement_candidate as candidate

EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX5A"
EV.mkdir(parents=True, exist_ok=True)
PRODUCT = rt.GeminiLiveRuntime


def state(runtime):
    snap = runtime.snapshot("one").session
    return {"cuts": list(runtime._sessions["one"].preview_cuts),
            "solid": [(r.source_lane, r.start_sample, r.end_sample, r.text)
                      for r in snap.effective_transcript],
            "preview": snap.provisional.segments if snap.provisional else None}


def attack(runtime_type, lane="system", empty=False, revision_lanes=None):
    tests.GeminiLiveRuntime = runtime_type
    with tempfile.TemporaryDirectory() as tmp:
        runtime = tests._runtime(Path(tmp), seconds=60, lanes=True)
        tests._commit(runtime, "Earlier settled discussion before this long turn", through_s=15, lane=lane)
        tests._advance_audio(runtime, 61)
        def preview(text, end):
            start = runtime.snapshot("one").session.committed_samples
            runtime.publish_update("one", rt.GeminiPreview(end * tests.R, (
                rt.GeminiSegment(start, end * tests.R, text, source_lane=lane),)))
        preview(tests.COMMITTED, 55)
        runtime.publish_update("one", rt.GeminiBase(21 * tests.R, (
            rt.GeminiSegment(15 * tests.R, 21 * tests.R, tests.COMMITTED, source_lane=lane),), degraded=True))
        before = state(runtime)
        runtime.publish_update("one", rt.GeminiBase(30 * tests.R, ()))
        replacement = " ".join(tests.COMMITTED.split()[:20])
        runtime.publish_update("one", rt.GeminiRolling(15 * tests.R, 30 * tests.R,
            () if empty else (rt.GeminiSegment(15 * tests.R, 30 * tests.R, replacement, "speaker-0001", lane),),
            revision_lanes=(lane,) if revision_lanes is None else revision_lanes))
        after = state(runtime)
        raw = tests.COMMITTED + " " + tests.FRESH
        row = rt.GeminiSegment(30 * tests.R, 60 * tests.R, raw, source_lane=lane)
        stateless = rt._trim_committed_preview((row,), runtime.snapshot("one").session.effective_transcript)
        preview(raw, 60)
        shown = state(runtime)
        text = " ".join(r["text"] for r in shown["preview"])
        expected = " ".join(r.text for r in stateless)
        stopped = asyncio.run(runtime.stop("one", 1))
        stop_cuts = list(runtime._sessions["one"].preview_cuts)
        runtime.create(session_id="two")
        assert runtime._sessions["two"].preview_cuts == []
        return {"lane": lane, "empty": empty, "revision_lanes": revision_lanes,
                "before": before, "after": after, "shown": shown,
                "stateless": expected, "same_as_stateless": text == expected,
                "stateless_extra_words": len(expected.split()) - len(text.split()),
                "unsupported_words_hidden": (0 if any(r.text == tests.COMMITTED for r in
                    runtime.snapshot("one").session.effective_transcript)
                    else len(expected.split()) - len(text.split())),
                "stop_preview_cleared": stopped.session.provisional is None,
                "stop_cuts": stop_cuts, "new_meeting_cuts": []}


def main():
    proto = candidate.runtime_class()
    report = {}
    for name, runtime_type in (("baseline", PRODUCT), ("prototype", proto)):
        report[name] = [attack(runtime_type, lane, empty)
                        for lane in ("system", "microphone") for empty in (False, True)]
        # Existing lane frontiers + an unscoped rolling append removes no base proof.
        report[name].append(attack(runtime_type, revision_lanes=()))
        tests.GeminiLiveRuntime = runtime_type
        controls = []
        for test_name, test in vars(tests).items():
            if test_name == "test_stop_clears_remembered_preview_cut":
                continue
            if test_name.startswith("test_") and ("remember" in test_name or
                    "proven_preview" in test_name or "degraded" in test_name):
                with tempfile.TemporaryDirectory() as tmp:
                    test(Path(tmp))
                controls.append(test_name)
        report[name + "_controls"] = controls
    tests.GeminiLiveRuntime = PRODUCT
    (EV / "transitions.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    assert all(r["unsupported_words_hidden"] == 0 and not r["stop_cuts"]
               for r in report["prototype"][:4])
    assert report["prototype"][4]["after"]["cuts"] == report["baseline"][4]["after"]["cuts"]
    assert report["baseline"][0]["unsupported_words_hidden"] == 61
    # Frozen code is unchanged; redirect every existing evidence writer.
    sys.path[:0] = [str(HERE.parent / "a3")]
    checker = (HERE.parent / "a3/verify_retained.py").read_text()
    checker = checker.replace('EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P73/a3/retained"',
                              'EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX5A/prototype-retained"')
    rt.GeminiLiveRuntime = proto
    try:
        exec(compile(checker, str(HERE.parent / "a3/verify_retained.py"), "exec"),
             {"__file__": str(HERE.parent / "a3/verify_retained.py"), "__name__": "__main__"})
    finally:
        rt.GeminiLiveRuntime = PRODUCT


if __name__ == "__main__":
    main()
