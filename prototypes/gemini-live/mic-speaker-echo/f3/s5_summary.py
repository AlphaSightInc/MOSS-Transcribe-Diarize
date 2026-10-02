"""Every table of the F3 notes from the recorded answers and runs ($0, throwaway).

    PY f3/s5_summary.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import f3lib  # noqa: E402
from f3lib import EV, RAW, RD_RAW, S  # noqa: E402

NAMES = ["media", "lab", "alan", "turing", "grace", "hopper", "microsoft", "google", "google", "computerphile"]


def request_table():
    print("== H1/H3 request variants: whole-recording draws (names kept of 10 in the Mandarin passage)")
    for path in sorted((EV / "runs").glob("request-*.json")):
        rows = json.loads(path.read_text())
        ok = [r for r in rows if "error" not in r]
        name = path.stem.replace("request-", "")
        if not ok:
            print(f"  {name:38s} REJECTED by the API: {rows[0]['error'][:110]}")
            continue
        if "names_kept_of_10" not in ok[0]:
            continue
        kept = [r["names_kept_of_10"] for r in ok]
        print(f"  {name:38s} draws {len(ok):2d}  names kept {kept}  all-10 in {sum(k == 10 for k in kept)}  "
              f"zh punctuation {min(r['zh_punctuation'] for r in ok)}-{max(r['zh_punctuation'] for r in ok)}  "
              f"traditional {sum(r['script'] == 'traditional' for r in ok)}/{len(ok)}  "
              f"parser dropped/clamped {sum(r['dropped'] for r in ok)}/{sum(r['clamped'] for r in ok)}  "
              f"word gate {sum(r['dropped_by_word_gate'] for r in ok)}  repaired {sum(r['repaired'] for r in ok)}  "
              f"zh speakers {sorted({r['zh_speakers'] for r in ok})} en speakers {sorted({r['en_speakers'] for r in ok})}")


def parser_table():
    files = [p for p in sorted(RAW.glob("*.json")) if not p.name.endswith(".error.json")]
    dropped = clamped = uncovered = 0
    hit = []
    for path in files:
        _, counts = f3lib.response_words(path)
        dropped += counts["dropped"]
        clamped += counts["clamped"]
        if counts["dropped"] or counts["clamped"]:
            hit.append((path.name, counts))
        data = json.loads(path.read_text())["response"]
        for step in data.get("steps") or ():
            for content in step.get("content") or ():
                raw = (content.get("text") or "").encode()
                cover = bytearray(len(raw))
                for a in content.get("annotations") or ():
                    for i in range(a.get("start_index", 0), min(len(raw), a.get("end_index", 0))):
                        cover[i] = 1
                uncovered += len(bytes(x for x, c in zip(raw, cover) if not c).decode(errors="replace").strip())
    print(f"== product-side losses on {len(files)} new answers: parser dropped {dropped} word(s), clamped {clamped}; "
          f"answer text not covered by a timed word: {uncovered} characters")
    for name, counts in hit:
        print("   ", name, counts)


def echo_lane_table():
    print("== R5-D's recorded 40 s answers for the microphone lane (system sound at -25 / -40 dB under local speech):")
    for cell in ("listen-echo25", "short-echo25", "long-echo25", "listen-aec40"):
        receipt = json.loads((EV / "runs" / f"base-{cell}" / "receipt.json").read_text())
        for call in receipt["batch_calls"]:
            if abs(call["seconds"] - 40) < 0.1 and call["file"] and "6679" not in call["file"]:
                words, _ = f3lib.response_words(RD_RAW / call["file"])
                zh = " ".join(w.text for w in words if w.start_sample < 23.6 * S)
                kept, missing = f3lib.kept_of(NAMES, f3lib.latin_tokens(zh))
                print(f"  {cell:14s} words {len(words):3d}  names kept {kept} of 10  zh punctuation {f3lib.punctuation(zh)}  "
                      f"script {f3lib.script_of(zh)}")


def restored_table():
    print("== every restored run in every rule-H engine run (text | uncovered s | gap to the nearer kept word s)")
    seen: dict[str, list] = {}
    for path in sorted((EV / "runs").glob("*/terminal.json")):
        if not (path.parent.name.endswith("-rule") or path.parent.name.startswith("rule-")):
            continue
        for lane, log in json.loads(path.read_text()).items():
            for r in log.get("restored") or ():
                gaps = [g for g in (r["left_gap_s"], r["right_gap_s"]) if g is not None]
                seen.setdefault(" ".join(r["text"]), []).append((r["uncovered_s"], min(gaps), lane))
    for text, rows in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(rows):3d} x  {text:28s} uncovered {min(r[0] for r in rows):.2f}-{max(r[0] for r in rows):.2f}  "
              f"nearer gap {min(r[1] for r in rows):.2f}-{max(r[1] for r in rows):.2f}  lanes {sorted({r[2] for r in rows})}")
    gaps = [r[1] for rows in seen.values() for r in rows]
    if gaps:
        print(f"  largest gap between a restored run and the nearer kept word: {max(gaps):.2f} s over {len(gaps)} runs")


def uncovered_left():
    """G1: the longest stretch of live committed words that the saved words leave uncovered, today vs rule."""
    import rule
    from rule import Word
    worst = {"today": [], "rule": []}
    for path in sorted((EV / "runs").glob("*/terminal.json")):
        name = path.parent.name
        kind = "rule" if name.endswith("-rule") or name.startswith("rule-") else "today"
        if kind == "today" and not (name.endswith("-today") or name.startswith("base-")):
            continue
        raw = json.loads((path.parent / "witness.json").read_text())
        for lane, log in json.loads(path.read_text()).items():
            if "final_words" not in log or not raw.get(lane):
                continue
            witness = rule.one_owner([Word(*w[:4]) for w in raw[lane]], [w[4] for w in raw[lane]])
            final = [Word(*w) for w in log["final_words"]]
            if not final:
                continue
            runs = rule.uncovered_runs(final, witness)
            worst[kind].append((max((n for _, n in runs), default=0) / S, name, lane))
    for kind, rows in worst.items():
        over = [r for r in rows if r[0] >= 0.15]
        top = max(rows)
        print(f"== G1 live words left without a saved word ({kind}): lanes {len(rows)}, lanes with a run >= 0.15 s: {len(over)}, "
              f">= 1 s: {sum(r[0] >= 1 for r in rows)}, longest {top[0]:.2f} s in {top[1]} ({top[2]})")


def extra_cells():
    print("== other engine cells (today -> rule)")
    truth = json.loads((f3lib.FIX / "en-k3.truth.json").read_text())["turns"]
    for p in (3.0, 0.0):
        line = []
        for kind in ("today", "rule"):
            rows = json.loads((EV / "runs" / f"en-k3-p{p:g}-{kind}" / "saved-meeting.json").read_text())["transcript"]["segments"]
            err = f3lib.speaker_error([(r["start"], r["end"], r["speaker"]) for r in rows],
                                      [(a + p, b + p, s) for a, b, s in truth], 29.2 + p)
            line.append(f"DER {err['der']:.4f} (miss {err['miss_s']:.2f} s, confusion {err['confusion_s']:.2f} s)")
        log = json.loads((EV / "runs" / f"en-k3-p{p:g}-rule" / "terminal.json").read_text())["system"]
        print(f"  English 3 speakers with truth, leading silence {p:g}: {line[0]} -> {line[1]}; restored "
              f"{[' '.join(r['text']) for r in log['restored']]}")
    for name in ("chunk-p3", "noise5-base", "noise5-lang2", "noise10-base", "noise10-lang2", "inj-sys2s", "inj-mic-en", "inj-mic-zh",
                 "inv-music", "inv-events"):
        today = json.loads((EV / "runs" / f"{name}-today" / "terminal.json").read_text())
        ruled = json.loads((EV / "runs" / f"{name}-rule" / "terminal.json").read_text())
        for lane in ruled:
            if "final_words" not in ruled[lane] or "final_words" not in today.get(lane, {}):
                continue
            kept, final = [tuple(w) for w in today[lane]["final_words"]], [tuple(w) for w in ruled[lane]["final_words"]]
            it = iter(final)
            same = all(any(w == f for f in it) for w in kept)
            restored = ruled[lane]["restored"]
            if not restored and lane == "microphone" and not name.startswith("inv-"):
                continue
            zh = lambda words: f3lib.kept_of(NAMES, f3lib.latin_tokens(" ".join(w[0] for w in words if w[2] < 23.6 * S)))[0]
            rows = json.loads((EV / "runs" / f"{name}-rule" / "saved-meeting.json").read_text())["transcript"]["segments"]
            mine = [r for r in rows if r["source_lane"] == lane]
            print(f"  {name:14s} {lane:10s} kept words identical {same} ({len(kept)}); names {zh(kept)} -> {zh(final)}; "
                  f"rows sorted/one owner {all(a['end'] <= b['start'] + 1e-9 for a, b in zip(mine, mine[1:]))}; "
                  f"restored {[' '.join(r['text']) for r in restored]}")


def spend_table():
    rows = [json.loads(line) for line in f3lib.LEDGER.read_text().splitlines()]
    kinds: dict[str, float] = {}
    for r in rows:
        label = r["label"]
        kind = ("request variants (H1/H3)" if any(f"-{v}-p" in label for v in ("lang", "lang2", "text", "vocab", "sys"))
                else "reproduction attempts" if any(k in label for k in ("zhstart", "-tw-", "noise", "music", "quiet")) and "-base-p" in label
                else "live samples and engine recordings" if any(label.startswith(k) for k in ("live-p", "en-k3", "chunk", "noise"))
                else "invented-word attack cells" if label.startswith("inv-")
                else "same-bytes check" if label.startswith("same-bytes") else "other")
        kinds[kind] = kinds.get(kind, 0) + r["usd"]
    total = sum(r["usd"] for r in rows)
    out = {"cap_usd": f3lib.CAP, "total_with_output_usd": round(total, 4), "by_kind": {k: round(v, 4) for k, v in kinds.items()},
           "paid_calls": sum(r["usd"] > 0 for r in rows), "rejected_or_failed_unbilled": sum(r["usd"] == 0 for r in rows),
           "method": "R5-D / P69: measured metered input rate + $0.002/min output estimate per audio second sent"}
    (EV / "spend.json").write_text(json.dumps(out, indent=1) + "\n")
    print("== spend", json.dumps(out))


if __name__ == "__main__":
    request_table()
    parser_table()
    echo_lane_table()
    restored_table()
    uncovered_left()
    extra_cells()
    spend_table()
