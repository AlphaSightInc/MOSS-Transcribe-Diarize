"""Rule H on the recorded patterns, one small case each — the seeds of the regression tests ($0, throwaway).

    PY f3/s6_patterns.py        prints PASS/FAIL per pattern; exit 1 on any FAIL
Times are seconds as the provider returned them in the named recording.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent)]
import rule  # noqa: E402
from rule import S, Word  # noqa: E402


def w(text, a, b, speaker="t1"):
    return Word(text, speaker, int(round(a * S)), int(round(b * S)))


def run(cleanup, live, frontiers=None):
    live = rule.one_owner(live, frontiers) if frontiers else live
    out, restored = rule.fill_holes(cleanup, live)
    text = " ".join(x.text for x in sorted(out, key=lambda x: (x.start_sample, x.end_sample)))
    return text, restored, out


CASES = []


def case(name, expect):
    def add(fn):
        CASES.append((name, expect, fn))
        return fn
    return add


@case("omitted name leaves a hole (rp-short-aec40: 院 5.2-5.3 | 计 5.8-5.9)", "院 Media Lab 的 计")
def _():
    return run([w("院", 5.2, 5.3), w("计", 5.8, 5.9)], [w("院", 5.2, 5.3), w("Media", 5.3, 5.5), w("Lab", 5.5, 5.7), w("的", 5.7, 5.8), w("計", 5.8, 5.9)])


@case("the clean-up kept the word after the hole (p0 draw: 院 | 的 2.6-2.8): no doubled 的", "院 Media Lab 的 计")
def _():
    return run([w("院", 2.1, 2.3), w("的", 2.6, 2.8), w("计", 2.8, 2.9)], [w("Media", 2.3, 2.5), w("Lab", 2.5, 2.7), w("的", 2.7, 2.8)])


@case("abutting same word one step later (p5 draw: 的 7.8-7.9 vs live 的 7.7-7.8)", "院 Media Lab 的 計")
def _():
    return run([w("院", 7.2, 7.3), w("的", 7.8, 7.9), w("計", 7.9, 8.0)], [w("Media", 7.3, 7.5), w("Lab", 7.5, 7.7), w("的", 7.7, 7.8)])


@case("a replacement is kept, the live word is not added (Computer File for Computerphile)", "道 Computer File 10")
def _():
    return run([w("道", 15.8, 16.0), w("Computer", 16.0, 16.5), w("File", 16.5, 16.7), w("10", 16.7, 16.9)], [w("道", 15.8, 15.9), w("Computerphile", 15.9, 16.6), w("10", 16.6, 16.8)])


@case("name omitted, neighbour one step into it (lang2-p3: 道 15.8-16.0 | 10 16.7-16.8)", "道 Computerphile 10")
def _():
    return run([w("道", 15.8, 16.0), w("10", 16.7, 16.8)], [w("道", 15.8, 15.9), w("Computerphile", 15.9, 16.6), w("10", 16.6, 16.8)])


@case("the same number written two ways at the edge (noise5: live 10, clean-up 十)", "道 Computer File 十 月")
def _():
    return run([w("道", 15.8, 16.0), w("十", 16.7, 16.8), w("月", 16.8, 16.9)], [w("Computer", 15.9, 16.3), w("File", 16.3, 16.6), w("10", 16.6, 16.8)])


@case("one time step of jitter is not a hole (他 / 也 / At, 0.1 s)", "年。 他 研")
def _():
    return run([w("年。", 9.5, 9.9), w("他", 10.0, 10.1), w("研", 10.1, 10.3)], [w("年。", 9.4, 9.9), w("他", 9.9, 10.0), w("研", 10.1, 10.3)])


@case("a long live word over the same clean-up word is not doubled (Amazing. 27.4-28.5 vs 28.2-28.5)", "though. Amazing. Why")
def _():
    return run([w("though.", 26.8, 27.0), w("Amazing.", 28.2, 28.5), w("Why", 29.0, 29.2)], [w("though.", 26.8, 27.1), w("Amazing.", 27.4, 28.5)])


@case("frontier restatement overlapping (live-p1.5: Computer 14.4-14.8 then Computerphile 14.4-15.1)", "道 Computerphile 10")
def _():
    return run([w("道", 14.3, 14.4), w("10", 15.1, 15.3)], [w("道", 14.3, 14.4), w("Computer", 14.4, 14.8), w("Computerphile", 14.4, 15.1), w("10", 15.1, 15.3)],
               frontiers=[0, 0, int(15 * S), int(15 * S)])


@case("frontier restatement abutting, same text (zhlong mic: 要 14.8-14.9 then 要 14.9-15.1)", "们 要 先")
def _():
    return run([w("们", 14.4, 14.6), w("先", 15.1, 15.3)], [w("们", 14.4, 14.7), w("要", 14.8, 14.9), w("要", 14.9, 15.1), w("先", 15.1, 15.3)],
               frontiers=[0, 0, int(15 * S), int(15 * S)])


@case("frontier duplicate covered by the clean-up word stays removed (議。 14.8-14.9 + 议。 14.9-15.1)", "会 议。 这")
def _():
    return run([w("会", 14.7, 14.9), w("议。", 14.9, 15.1), w("这", 15.2, 15.3)], [w("會", 14.7, 14.8), w("議。", 14.8, 14.9), w("议。", 14.9, 15.1), w("这", 15.1, 15.3)],
               frontiers=[0, 0, int(15 * S), int(15 * S)])


@case("mis-timed live word far from its speech (zhlong mic: 我 0.1-0.2), 0.1 s", "我 觉")
def _():
    return run([w("我", 12.0, 12.1), w("觉", 12.1, 12.3)], [w("我", 0.1, 0.2), w("觉", 12.0, 12.3)])


@case("restored words take the nearer neighbour's speaker; kept words keep theirs (en-k3: there. 19.7-20.0)", "bard there. But")
def _():
    text, restored, out = run([w("bard", 19.2, 19.6, "t2"), w("But", 21.0, 21.2, "t3")], [w("there.", 19.7, 20.0, "live")])
    assert [x.speaker for x in sorted(out, key=lambda x: x.start_sample)] == ["t2", "t2", "t3"], out
    return text, restored, out


@case("trailing speech the clean-up stopped before (uh 37.5 | I 38.0-38.2 | I 38.2)", "and uh I I")
def _():
    return run([w("and", 37.3, 37.5)], [w("and", 37.4, 37.5), w("uh", 37.5, 37.5), w("I", 38.0, 38.2), w("I", 38.2, 38.2)])


@case("an interval the >= 10 s fallback owns is skipped", "a b")
def _():
    out, restored = rule.fill_holes([w("a", 1.0, 1.2), w("b", 30.0, 30.2)], [w("x", 10.0, 10.5), w("y", 10.5, 11.0)],
                                    skip=[(int(1.2 * S), int(30 * S))])
    return " ".join(x.text for x in out), restored, out


@case("LIMIT (stated, not a goal): a live-only word alone in a long quiet stretch is restored too", "a Oui. b")
def _():
    return run([w("a", 1.0, 1.2), w("b", 9.0, 9.2)], [w("Oui.", 5.0, 5.3)])


def main():
    failed = 0
    for name, expect, fn in CASES:
        text, restored, _ = fn()
        ok = text == expect
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}\n        -> {text}   restored {[' '.join(r['text']) for r in restored]}")
    print(f"{len(CASES) - failed} of {len(CASES)} patterns pass")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
