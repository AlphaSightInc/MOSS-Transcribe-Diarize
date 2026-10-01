"""How transcript text is joined, and how text saved before that rule is read."""
from __future__ import annotations

import re

# Characters of scripts written without spaces between words, and their punctuation: CJK
# symbols and punctuation, kana, bopomofo, Han (with extensions and compatibility forms) and
# full-width forms. Hangul is left out on purpose: Korean puts spaces between words.
_UNSPACED_SET = ("　-ㄯㇰ-ㇿ㐀-䶿一-鿿豈-﫿"
                 "＀-ﾟ￠-￯\U00020000-\U0003134f")
_UNSPACED = re.compile(f"[{_UNSPACED_SET}]")
_JOIN_SPACE = re.compile(f"(?<=[{_UNSPACED_SET}]) (?=[{_UNSPACED_SET}])")


def join_text(left: str, right: str) -> str:
    """The one rule for joining transcript text: words into turns, and turns into rows.

    Gemini returns one "word" per Chinese character, so a space between every pair of words
    printed "大 家 好". No space is written where either side of the join is an
    unspaced-script character; otherwise exactly one. Mixed text therefore reads
    "我们用API做测试" and "大概30万" (how the provider's own unspaced text writes numbers),
    while words of a spaced script keep their space ("Google Cloud", "Yeah. We").
    `joinText` in `frontend/src/lib/text.ts` is the same rule for the browser's joins.
    """
    left, right = left.rstrip(), right.lstrip()
    if not left or not right:
        return left or right
    gap = "" if _UNSPACED.match(left[-1]) or _UNSPACED.match(right[0]) else " "
    return left + gap + right


def without_join_spaces(text: str) -> str:
    """Read text that was saved when every word join wrote a space ("大 家 好").

    Only a single space standing between two unspaced-script characters is dropped. Text
    joined by `join_text` has none, so it comes back as the same string; a space beside a
    Latin letter, a digit or Hangul ("用 API 做", "30 万") is kept as stored, because
    nothing in the saved string says whether it was a join.
    """
    return _JOIN_SPACE.sub("", text) if " " in text else text
