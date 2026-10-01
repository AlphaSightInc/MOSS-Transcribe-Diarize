export function trimString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function normalizeInlineWhitespace(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function normalizeCasefoldedWhitespace(value: string): string {
  return normalizeInlineWhitespace(value).toLowerCase();
}

// Characters of scripts written without spaces between words, and their punctuation: CJK symbols
// and punctuation, kana, bopomofo, Han and full-width forms. Hangul is left out: Korean puts
// spaces between words. Same set as `_UNSPACED` in moss_transcribe_diarize/app/gemini_provider.py.
const UNSPACED = "[\\u3000-\\u312f\\u31f0-\\u31ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff" +
  "\\uff00-\\uff9f\\uffe0-\\uffef\\u{20000}-\\u{3134f}]";
const ENDS_UNSPACED = new RegExp(`${UNSPACED}$`, "u");
const STARTS_UNSPACED = new RegExp(`^${UNSPACED}`, "u");

/**
 * The one rule for joining transcript text (the server's `join_text`): no space where either side
 * of the join is an unspaced-script character ("大家好", "我们用API做测试"), otherwise exactly one.
 */
export function joinTexts(parts: readonly string[]): string {
  const kept = parts.map(part => part.trim()).filter(part => part.length > 0);
  return kept.map((part, index) => {
    if (index === 0) return part;
    const unspaced = ENDS_UNSPACED.test(kept[index - 1]!.slice(-2)) || STARTS_UNSPACED.test(part.slice(0, 2));
    return unspaced ? part : ` ${part}`;
  }).join("");
}

export function joinText(left: string, right: string): string {
  return joinTexts([left, right]);
}
