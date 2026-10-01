import { describe, expect, it } from "vitest";
import { joinText, joinTexts } from "./text";

// The same table as tests/gemini/test_gemini_provider.py::test_join_text_rule: one rule, two runtimes.
const cases: Array<[string, string[], string]> = [
  ["Chinese, one word per character", ["大", "家", "好，", "今", "天"], "大家好，今天"],
  ["Japanese", ["今日", "は", "会議", "です。", "ありがとう", "ございます。"], "今日は会議です。ありがとうございます。"],
  ["mixed Chinese and English", ["我", "们", "用", "API", "做", "测", "试，", "Google", "Cloud", "也", "行。"],
    "我们用API做测试，Google Cloud也行。"],
  ["a number inside Chinese", ["大", "概", "30", "万", "左", "右"], "大概30万左右"],
  ["English with punctuation", ["Well,", "it's", "fine.", "Right?", "(Yes.)"], "Well, it's fine. Right? (Yes.)"],
  ["a sentence end before a lowercase word", ["Yeah.", "researching", "it"], "Yeah. researching it"],
  ["never a double space", ["one ", " two", "", "  ", "three"], "one two three"],
  ["Korean keeps its word spaces", ["오늘", "회의를", "시작하겠습니다."], "오늘 회의를 시작하겠습니다."],
  ["full-width punctuation after English", ["OK", "，", "好"], "OK，好"],
  ["a Han character outside the basic plane", ["𠮷", "野", "家"], "𠮷野家"]
];

describe("joinTexts", () => {
  it.each(cases)("%s", (_name, parts, expected) => {
    expect(joinTexts(parts)).toBe(expected);
    expect(parts.reduce(joinText, "")).toBe(expected);
  });
});
