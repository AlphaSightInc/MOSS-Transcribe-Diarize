"""Does incremental event draining change the trace of a session that never overflows?

Question: the replay client now reads the service event stream once per accepted frame
instead of once after the session ends.  For a session whose event count stays inside
`bounds.max_events` the two policies must observe the same events, so the artifact must
be the same -- otherwise the fix has side effects on every 60-second case in the corpus.

Method: run the same scripted in-memory session three times with a scripted clock --
twice on the checked-in HEAD client, once on the working-tree client -- and compare
traces field by field.  Two HEAD runs establish which fields move on their own (the
runtime stamps a real monotonic clock into event payloads); the fix is side-effect free
iff HEAD-vs-working-tree differs in exactly those fields and nowhere else.

Run: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
       prototypes/streaming-diarization/live-convergence/probe_replay_trace_shape_identity.py
Exit 0 iff the fix changes nothing a second HEAD run would not also change.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CLIENT = REPO / "moss_transcribe_diarize/live_service_replay.py"
PYTHON = REPO / ".venv/bin/python"

RUNNER = '''
import sys
sys.path.insert(0, "tests")
from pathlib import Path
import test_live_service_replay as T
from moss_transcribe_diarize import live_service_replay as R

descriptor = T._descriptor(frame_samples=400)
service = T.RecordingService(
    T._runtime(
        descriptor=descriptor,
        speech=(True, True, False, True, True, False, True, True),
        session_ids=("s1",),
    )
)
clock = T.ScriptedClock()
root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
audio = root / "audio.wav"
T._write_wav(audio, samples=3200)
R.run_service_replay(
    service=service,
    audio_path=audio,
    out_dir=root / "out",
    pace=1.0,
    max_pacing_lag=0.5,
    runs=1,
    expect_revision=descriptor.source_revision,
    expect_provider_hash=descriptor.provider_manifest_hash,
    expect_config_hash=descriptor.config_hashes.combined_config_hash,
    monotonic=clock.monotonic,
    sleep=clock.sleep,
)
'''


def _run(out_dir: Path) -> list[dict]:
    proc = subprocess.run(
        [str(PYTHON), "-c", RUNNER, str(out_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
    )
    if proc.returncode:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"replay run failed in {out_dir}")
    trace = out_dir / "out/run-001/trace.jsonl"
    return [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]


def _paths(value, prefix=()):  # -> {json path: leaf value}
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out.update(_paths(item, prefix + (str(key),)))
        return out
    if isinstance(value, list):
        out = {}
        for index, item in enumerate(value):
            out.update(_paths(item, prefix + (str(index),)))
        return out
    return {".".join(prefix): value}


def _differing_paths(left: list[dict], right: list[dict]) -> set[str]:
    if len(left) != len(right):
        raise SystemExit(f"trace lengths differ: {len(left)} vs {len(right)}")
    differing = set()
    for index, (a, b) in enumerate(zip(left, right)):
        pa, pb = _paths(a), _paths(b)
        if pa.keys() != pb.keys():
            raise SystemExit(f"trace entry {index} has different fields")
        differing.update(key for key in pa if pa[key] != pb[key])
    return differing


def main() -> int:
    working_tree = CLIENT.read_text(encoding="utf-8")
    head = subprocess.run(
        ["git", "show", "HEAD:moss_transcribe_diarize/live_service_replay.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    tmp = Path(tempfile.mkdtemp(prefix="replay-trace-shape-"))
    try:
        CLIENT.write_text(head, encoding="utf-8")
        head_a = _run(tmp / "head-a")
        head_b = _run(tmp / "head-b")
        CLIENT.write_text(working_tree, encoding="utf-8")
        patched = _run(tmp / "working-tree")
    finally:
        CLIENT.write_text(working_tree, encoding="utf-8")

    self_noise = _differing_paths(head_a, head_b)
    fix_delta = _differing_paths(head_a, patched)
    extra = sorted(fix_delta - self_noise)

    print(f"trace entries: head={len(head_a)} working-tree={len(patched)}")
    print(f"service events: {sum(1 for item in patched if item['kind'] == 'service_event')}")
    print(f"fields that move between two HEAD runs: {sorted(self_noise)}")
    print(f"fields that move HEAD -> working tree:  {sorted(fix_delta)}")
    print(f"fields the fix moves on its own:        {extra}")
    if extra:
        print("VERDICT: the fix changes a non-overflowing trace. FAIL")
        return 1
    print("VERDICT: non-overflowing traces are unchanged by the fix. PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
