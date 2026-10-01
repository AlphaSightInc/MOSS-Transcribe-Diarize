"""Run one engine cell and score it against the truth of where the local person spoke (throwaway, $0 to score).

    PYTHON f2/cells.py <run> [...]      # score existing runs under the f2 evidence folder
Recall = units of each spoken phrase found in the microphone rows that overlap it in time (a unit = a word, or
one CJK character; traditional characters folded to simplified). Extra = microphone units that match no phrase:
invented or echoed text.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(HERE)]
import ledger  # noqa: E402

S = 16000
PY = sys.executable
_FOLD = dict(zip("這個問題學院計算機經網絡訓練會議頻道專訪從頭講為什麼開願術們視頻對實現時間後來說話還沒與業務數據長發進沒問題週討論覺測遲遍嗎確認復覆謝請見對",
                 "这个问题学院计算机经网络训练会议频道专访从头讲为什么开愿术们视频对实现时间后来说话还没与业务数据长发进没问题周讨论觉测迟遍吗确认复复谢请见对"))


def units(text: str) -> list[str]:
    from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units
    return [unit for unit, _, _ in _preview_units("".join(_FOLD.get(ch, ch) for ch in text))]


def lcs(a, b) -> int:
    row = [0] * (len(b) + 1)
    for x in a:
        prior = 0
        for j, y in enumerate(b, 1):
            prior, row[j] = row[j], prior + 1 if x == y else max(row[j], row[j - 1])
    return row[-1]


def truth_of(mic_wav: str) -> list[dict]:
    path = Path(mic_wav)
    sidecar = path.with_suffix(".json")
    if sidecar.is_file():
        return json.loads(sidecar.read_text())["truth"]
    import fixtures                                   # an R5-D wav: the same turns, rebuilt for their times
    kind = path.stem.split("-")[1]
    return fixtures.local(fixtures.KINDS[kind], -27.0)[1]


def run(out: str, mic_wav, *, system_wav=None, answers=None, candidate=None, donor=None, record=False, w3=None,
        w3_system_from=None, key=False) -> dict:
    import fixtures
    command = [PY, str(HERE / "replay_f2.py"), out, str(system_wav or fixtures.D_FIX / "sys-zhlatin-en.wav"), str(mic_wav)]
    if answers:
        command += ["--answers", answers]
    if donor:
        command += ["--donor", donor]
    if record:
        command += ["--record"]
    if w3:
        command += ["--w3", w3]
    if w3_system_from:
        command += ["--w3-system-from", w3_system_from]
    if candidate is not None:
        command += ["--candidate", json.dumps(candidate)]
    if key:
        command = [str(HERE.parent / "with_key.sh")] + command
    done = subprocess.run(command, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if done.returncode:
        raise SystemExit(f"{out}: {done.stdout[-1500:]}\n{done.stderr[-3000:]}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def score(out: str) -> dict:
    folder = ledger.EV / "runs" / out
    receipt = json.loads((folder / "receipt.json").read_text())
    snaps = [json.loads(line) for line in (folder / "snapshots.jsonl").read_text().splitlines()]
    gates = [json.loads(line) for line in (folder / "gates.jsonl").read_text().splitlines()]
    prefix = receipt["prefix_s"]
    truth = truth_of(receipt["mic_wav"])
    by_note = {snap["note"]: snap for snap in snaps if snap["note"]}

    def mic_rows(snap):
        return [row for row in snap["effective"] if row.get("source_lane") == "microphone"]

    def judge(snap):
        """recall: units of each phrase found in the microphone rows overlapping it. outside: units of microphone
        rows that overlap no phrase (invented or echoed rows). echo_inside: units inside an overlapping row that
        are not the phrase's and are words the tab said within 2 s (echo committed inside a real local row)."""
        rows = mic_rows(snap)
        tab_rows = [row for row in snap["effective"] if row.get("source_lane") == "system"]
        spoken = matched = echo_inside = 0
        phrases, claimed = [], set()
        for phrase in truth:
            lo, hi = (phrase["start"] + prefix - .7) * S, (phrase["end"] + prefix + .7) * S
            mine = [row for row in rows if row["start_sample"] < hi and row["end_sample"] > lo]
            claimed.update(id(row) for row in mine)
            heard = [u for row in mine for u in units(row["text"])]
            want = units(phrase["text"])
            got = lcs(want, heard)
            spoken, matched = spoken + len(want), matched + got
            phrases.append(f"{got}/{len(want)}")
            tab = {u for row in tab_rows if row["start_sample"] < hi + 2 * S and row["end_sample"] > lo - 2 * S
                   for u in units(row["text"])}
            left = list(heard)
            for unit in want:
                if unit in left:
                    left.remove(unit)
            echo_inside += sum(1 for unit in left if unit in tab)
        outside = sum(len(units(row["text"])) for row in rows if id(row) not in claimed)
        total = sum(len(units(row["text"])) for row in rows)
        return {"rows": len(rows), "recall": f"{matched}/{spoken}", "phrases": phrases, "outside_units": outside,
                "echo_inside_units": echo_inside, "extra_units": max(0, total - matched),
                "text": [row["text"] for row in rows]}
    diag = by_note["settled"]["diag"]
    summaries = [g for g in gates if g["stage"] == "window_summary"]
    return {
        "run": out, "mic": Path(receipt["mic_wav"]).stem, "candidate": bool(receipt["candidate"]),
        "truth": [(round(p["start"], 1), round(p["end"] - p["start"], 2), p["text"]) for p in truth],
        "live_solid": judge(by_note["before Stop"]), "saved_at_stop": judge(by_note["completed (live transcript saved)"]),
        "saved": judge(by_note["settled"]),
        "grey_mic_texts": sorted({seg["text"] for snap in snaps if snap["provisional"]
                                  for seg in snap["provisional"]["segments"] if seg["source_lane"] == "microphone"}),
        "grey_mic_snapshots": sum(1 for snap in snaps if snap["provisional"] and any(
            seg["source_lane"] == "microphone" for seg in snap["provisional"]["segments"])),
        "counters": {"level": diag["mic_words_dropped_by_acoustic_gate"], "voice": diag["mic_echo_dropped_by_voice"],
                     "text": diag["mic_words_dropped_by_text_guard"], "unanchored": diag["mic_words_dropped_unanchored"],
                     "lane_withheld": diag["mic_words_withheld_unanchored_lane"],
                     **({k: v for k, v in receipt["candidate_counts"].items() if k != "added_ms"}
                        if receipt["candidate_counts"] else {})},
        "provider_words_per_mic_call": [s["after_voice_activity_gate"] for s in summaries],
        "added_ms": receipt["candidate_counts"]["added_ms"] if receipt["candidate_counts"] else None,
        "gate_ms": [g["gate_ms"] for g in gates if g["stage"] in ("mic_window", "mic_cleanup")],
        "finalization": receipt["finalization_status"]}


def line(s: dict) -> str:
    return (f"{s['run']:34s} live {s['live_solid']['recall']:>6s} out {s['live_solid']['outside_units']} echo {s['live_solid']['echo_inside_units']} "
            f"saved {s['saved']['recall']:>6s} out {s['saved']['outside_units']} echo {s['saved']['echo_inside_units']} phrases live {s['live_solid']['phrases']} "
            f"saved {s['saved']['phrases']}  {s['counters']}")


if __name__ == "__main__":
    for name in (arg for arg in sys.argv[1:] if not arg.startswith("--")):
        result = score(name)
        print(json.dumps(result, ensure_ascii=False, indent=1) if "--full" in sys.argv else line(result))
