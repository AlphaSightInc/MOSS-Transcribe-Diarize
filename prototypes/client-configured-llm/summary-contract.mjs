// PROTOTYPE — pure summary prompt and output-contract logic; not production code.

const REQUIRED_KEYS = [
  "summary",
  "topics",
  "details",
  "data_references",
  "speaker_background",
];

export const REVISED_SUMMARY_SYSTEM_PROMPT = `Summarize one authoritative transcript into exactly one JSON object. Return JSON only: no prose or markdown fences.

Use only facts directly supported by the transcript. Never infer a role, motive, identity, or outside fact. Keep substantive supported names, claims, arguments, and quantities even when condensing. Write every string in English except names or verbatim quantities.

Return exactly these five keys:
- "summary": one sentence of at most 25 whitespace-separated words stating the central thesis.
- "topics": 2 to 4 objects with "title" and "description" strings. Use specific noun-phrase titles. Each description compactly preserves the major claim and support.
- "details": chronological objects with "title", "description", and "timestamp" strings. Use a transcript HH:MM:SS time for every detail. Do not invent a time beyond the transcript.
- "data_references": objects with "item", "value", and "context" strings. Include every digit-bearing quantity in the spoken words: counts, dates, years, money, percentages, and durations. Copy each digit-bearing token verbatim into "value". Never put a digit-bearing token in "value" unless it occurs verbatim in the spoken words. Transcript [HH:MM:SS] prefixes are navigation, not quantities.
- "speaker_background": strings in "Name: role/background" form only when explicitly stated; otherwise an empty array.

Before returning, silently check: exact schema; summary <=25 words; topics 2-4; every detail timestamp valid; every spoken digit-bearing token present verbatim in data_references.value; no unsupported digit-bearing value.`;

export function summaryMessages(transcript) {
  return [
    { role: "system", content: REVISED_SUMMARY_SYSTEM_PROMPT },
    {
      role: "user",
      content:
        "Create the first rolling summary from the complete authoritative transcript. " +
        "Full factual retention belongs in topics, details, and data_references even when the summary sentence is short.\n\n" +
        `TRANSCRIPT:\n${transcript}`,
    },
  ];
}

export function exactDigitTokens(text) {
  // A comma is part of a quantity only when it separates a three-digit group.
  // Sentence punctuation is not part of the spoken quantity token.
  const matches =
    text.match(
      /(?<![A-Za-z])[$€£]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:%|[xX]|s)?(?![A-Za-z])/g,
    ) ?? [];
  return [...new Set(matches)];
}

function violation(code, observed, required) {
  return { code, observed, required };
}

export function parseSummaryOutput(rawOutput) {
  let candidate = rawOutput.trim();
  if (candidate.startsWith("```")) {
    candidate = candidate.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  }
  const first = candidate.indexOf("{");
  const last = candidate.lastIndexOf("}");
  if (first >= 0 && last > first) candidate = candidate.slice(first, last + 1);

  let parsed;
  try {
    parsed = JSON.parse(candidate);
  } catch (error) {
    return {
      summary: null,
      schemaViolations: [violation("json_parse", error.message, "one valid JSON object")],
    };
  }

  const issues = [];
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {
      summary: null,
      schemaViolations: [violation("root_type", typeof parsed, "object")],
    };
  }

  const actualKeys = Object.keys(parsed).sort();
  const expectedKeys = [...REQUIRED_KEYS].sort();
  if (JSON.stringify(actualKeys) !== JSON.stringify(expectedKeys)) {
    issues.push(violation("exact_keys", actualKeys, expectedKeys));
  }
  if (typeof parsed.summary !== "string") {
    issues.push(violation("summary_type", typeof parsed.summary, "string"));
  }
  if (!Array.isArray(parsed.topics)) {
    issues.push(violation("topics_type", typeof parsed.topics, "array"));
  } else if (
    parsed.topics.some(
      (item) =>
        item === null ||
        typeof item !== "object" ||
        typeof item.title !== "string" ||
        typeof item.description !== "string",
    )
  ) {
    issues.push(violation("topic_item_schema", "invalid item", "{title:string, description:string}"));
  }
  if (!Array.isArray(parsed.details)) {
    issues.push(violation("details_type", typeof parsed.details, "array"));
  } else if (
    parsed.details.some(
      (item) =>
        item === null ||
        typeof item !== "object" ||
        typeof item.title !== "string" ||
        typeof item.description !== "string" ||
        typeof item.timestamp !== "string",
    )
  ) {
    issues.push(
      violation(
        "detail_item_schema",
        "invalid item",
        "{title:string, description:string, timestamp:string}",
      ),
    );
  }
  if (!Array.isArray(parsed.data_references)) {
    issues.push(violation("data_references_type", typeof parsed.data_references, "array"));
  } else if (
    parsed.data_references.some(
      (item) =>
        item === null ||
        typeof item !== "object" ||
        typeof item.item !== "string" ||
        typeof item.value !== "string" ||
        typeof item.context !== "string",
    )
  ) {
    issues.push(
      violation(
        "data_reference_item_schema",
        "invalid item",
        "{item:string, value:string, context:string}",
      ),
    );
  }
  if (!Array.isArray(parsed.speaker_background)) {
    issues.push(violation("speaker_background_type", typeof parsed.speaker_background, "array"));
  } else if (parsed.speaker_background.some((item) => typeof item !== "string")) {
    issues.push(violation("speaker_background_item_schema", "invalid item", "string"));
  }

  return { summary: parsed, schemaViolations: issues };
}

function validTimestamp(value, durationSeconds) {
  const match = /^(\d{2}):(\d{2}):(\d{2})$/.exec(value);
  if (!match) return false;
  const [, hours, minutes, seconds] = match.map(Number);
  if (minutes >= 60 || seconds >= 60) return false;
  return hours * 3600 + minutes * 60 + seconds <= durationSeconds + 1;
}

export function validateSummaryContract(summary, { sourceText, durationSeconds }) {
  const issues = [];
  const wordCount = summary.summary.trim().split(/\s+/).filter(Boolean).length;
  if (wordCount > 25) {
    issues.push(violation("summary_words", wordCount, "<=25"));
  }
  if (summary.topics.length < 2 || summary.topics.length > 4) {
    issues.push(violation("topic_count", summary.topics.length, "2..4"));
  }
  const invalidTimestamps = summary.details
    .map((item, index) => ({ index, value: item.timestamp }))
    .filter((item) => !validTimestamp(item.value, durationSeconds));
  if (invalidTimestamps.length > 0) {
    issues.push(
      violation(
        "invalid_detail_timestamps",
        invalidTimestamps,
        `HH:MM:SS within 00:00:00..${durationSeconds.toFixed(3)}s`,
      ),
    );
  }

  const requiredQuantityTokens = exactDigitTokens(sourceText);
  const outputQuantityTokens = exactDigitTokens(
    summary.data_references.map((item) => item.value).join(" "),
  );
  const missing = requiredQuantityTokens.filter((token) => !outputQuantityTokens.includes(token));
  const unsupported = outputQuantityTokens.filter((token) => !requiredQuantityTokens.includes(token));
  if (missing.length > 0) {
    issues.push(violation("missing_quantity_tokens", missing, requiredQuantityTokens));
  }
  if (unsupported.length > 0) {
    issues.push(violation("unsupported_quantity_tokens", unsupported, requiredQuantityTokens));
  }

  return {
    passed: issues.length === 0,
    violations: issues,
    summaryWordCount: wordCount,
    topicCount: summary.topics.length,
    invalidDetailTimestamps: invalidTimestamps,
    requiredQuantityTokens,
    outputQuantityTokens,
  };
}

export function contractFeedbackMessage(violations) {
  const lines = violations.map(
    (item) =>
      `- ${item.code}: observed ${JSON.stringify(item.observed)}; required ${JSON.stringify(item.required)}`,
  );
  return `Repair the same summary. Return only the complete five-key JSON object. Do not truncate text or invent facts. Preserve all supported content while correcting exactly these deterministic contract failures:\n${lines.join("\n")}`;
}

export const INSIGHT_SUMMARY_SYSTEM_PROMPT = `Create a compact, decision-useful briefing that lets a thoughtful reader understand what matters without reading the transcript.

Your goal is to capture the key takeaways, especially:
- insights and mental models that improve how the reader thinks about the topic;
- causal explanations, reasoning, trade-offs, disagreements, and implications;
- important but easily overlooked facts or metrics that materially change understanding.

Prioritize significance over exhaustiveness. Explain why an insight matters, not merely that it was mentioned. Attribute claims and opinions to their speakers. Preserve uncertainty and disagreement. Use only transcript-supported content; do not add outside facts or infer unstated roles, motives, or identities.

Return JSON only, with exactly this shape and these key names. Replace the placeholders with transcript-grounded content:
{
  "summary": "A concise synthesis of the central ideas and why they matter.",
  "topics": [
    {
      "title": "Specific insight-oriented heading",
      "description": "The key takeaway, supporting reasoning or mental model, and why it matters."
    }
  ],
  "details": [
    {
      "title": "Specific substantive moment",
      "description": "The supported claim, reasoning, disagreement, or implication.",
      "timestamp": "HH:MM:SS"
    }
  ],
  "speaker_background": [
    "Name: explicitly stated role or background"
  ],
  "data_references": [
    {
      "item": "What the metric measures",
      "value": "Important value copied with its unit",
      "context": "How the metric supports an important takeaway and why it matters"
    }
  ]
}

Content guidance:
- summary: a compact synthesis, normally 2 to 4 sentences. Lead with the central insight, then the most important implication or mental model.
- topics: include only substantive themes. Prefer a few high-signal topics over exhaustive coverage.
- details: preserve the most useful supporting reasoning and chronology. Use a transcript HH:MM:SS timestamp for every item.
- speaker_background: include only roles or background explicitly stated in the transcript; otherwise use [].
- data_references: an optional metric appendix at the end. Include only numbers, dates, money, percentages, counts, or durations that substantiate a major claim, reveal scale or change, expose a trade-off, or are important and under-appreciated. Copy the complete value and unit verbatim when practical and explain why it matters. Omit incidental numbers. Use [] when no metric materially improves understanding.

Metrics are encouraged evidence, not a completeness exercise. Never add a metric merely to satisfy a quota.`;

export function insightSummaryMessages(transcript) {
  return [
    { role: "system", content: INSIGHT_SUMMARY_SYSTEM_PROMPT },
    {
      role: "user",
      content:
        "Produce the first insight briefing from this complete authoritative transcript. " +
        "Optimize for reader understanding and decision value, not transcript coverage.\n\n" +
        `TRANSCRIPT:\n${transcript}`,
    },
  ];
}

export function validateInsightSummaryStructure(summary, { sourceText, durationSeconds }) {
  const issues = [];
  if (summary.summary.trim() === "") {
    issues.push(violation("summary_empty", "empty string", "non-empty synthesis"));
  }
  const invalidTimestamps = summary.details
    .map((item, index) => ({ index, value: item.timestamp }))
    .filter((item) => !validTimestamp(item.value, durationSeconds));
  if (invalidTimestamps.length > 0) {
    issues.push(
      violation(
        "invalid_detail_timestamps",
        invalidTimestamps,
        `HH:MM:SS within 00:00:00..${durationSeconds.toFixed(3)}s`,
      ),
    );
  }

  const sourceDigitTokens = exactDigitTokens(sourceText);
  const appendixDigitTokens = exactDigitTokens(
    summary.data_references.map((item) => item.value).join(" "),
  );
  return {
    passed: issues.length === 0,
    violations: issues,
    invalidDetailTimestamps: invalidTimestamps,
    metricAppendix: {
      acceptanceCriterion: false,
      itemCount: summary.data_references.length,
      sourceDigitTokens,
      appendixDigitTokens,
      omittedSourceDigitTokens: sourceDigitTokens.filter(
        (token) => !appendixDigitTokens.includes(token),
      ),
      unsupportedAppendixDigitTokens: appendixDigitTokens.filter(
        (token) => !sourceDigitTokens.includes(token),
      ),
    },
  };
}

export function insightStructureFeedbackMessage(violations) {
  const lines = violations.map(
    (item) =>
      `- ${item.code}: observed ${JSON.stringify(item.observed)}; required ${JSON.stringify(item.required)}`,
  );
  return `Repair only the unusable structure in the same briefing. Return the complete five-key JSON object. Preserve supported insights and do not add metrics merely to satisfy this repair:\n${lines.join("\n")}`;
}
