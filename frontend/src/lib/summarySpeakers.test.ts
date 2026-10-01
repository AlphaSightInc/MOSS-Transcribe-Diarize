import { describe, expect, it } from "vitest";
import type { SummaryDocument } from "./finalSummary";
import { renameSummarySpeakers, transcriptSpeakerNames } from "./summarySpeakers";

const doc = (summary: string, extra: Partial<SummaryDocument> = {}): SummaryDocument =>
  ({ summary, topics: [], details: [], speaker_background: [], data_references: [], ...extra });
const read = (summary: string, given: Record<string, string> | undefined, now: Record<string, string>) =>
  renameSummarySpeakers(doc(summary), given, now).summary;

/** The names a two-lane meeting's generator is given before anyone is named. */
const GIVEN = { "speaker-0001": "Speaker 1", "speaker-0002": "Speaker 2", "local-1": "You" };

describe("renameSummarySpeakers", () => {
  it("shows a renamed speaker in every prose field and leaves timestamps and values alone", () => {
    const stored = doc("Speaker 1 asked Speaker 2 about the plan.", {
      topics: [{ title: "Speaker 1's plan", description: "Speaker 1 wants ten hires." }],
      details: [{ title: "Speaker 1 objects", description: "Speaker 2 answers Speaker 1.", timestamp: "00:00:01" }],
      speaker_background: ["Speaker 1: host", "Speaker 2: guest"],
      data_references: [{ item: "Hires (Speaker 1)", value: "10", context: "Speaker 1 said ten." }]
    });
    expect(renameSummarySpeakers(stored, GIVEN, { ...GIVEN, "speaker-0001": "Alice" })).toEqual({
      summary: "Alice asked Speaker 2 about the plan.",
      topics: [{ title: "Alice's plan", description: "Alice wants ten hires." }],
      details: [{ title: "Alice objects", description: "Speaker 2 answers Alice.", timestamp: "00:00:01" }],
      speaker_background: ["Alice: host", "Speaker 2: guest"],
      data_references: [{ item: "Hires (Alice)", value: "10", context: "Alice said ten." }]
    });
    // The stored document is never edited: the next rename starts from it again.
    expect(stored.summary).toBe("Speaker 1 asked Speaker 2 about the plan.");
  });

  it("does not rewrite Speaker 10 or Speaker 12 when Speaker 1 is renamed", () => {
    const given = { ...GIVEN, "speaker-0010": "Speaker 10", "speaker-0012": "Speaker 12" };
    expect(read("Speaker 1, Speaker 10 and Speaker 12 spoke; Speaker 1 led.", given,
      { ...given, "speaker-0001": "Alice" })).toBe("Alice, Speaker 10 and Speaker 12 spoke; Alice led.");
    // Also when the longer label belongs to nobody the generator was told about.
    expect(read("Speaker 1 quoted Speaker 13.", GIVEN, { ...GIVEN, "speaker-0001": "Alice" }))
      .toBe("Alice quoted Speaker 13.");
  });

  it("follows a second rename, two renames at once, a swap and a rename back to the default", () => {
    const text = "Speaker 1 and Speaker 2 agreed.";
    expect(read(text, GIVEN, { ...GIVEN, "speaker-0001": "Alice" })).toBe("Alice and Speaker 2 agreed.");
    expect(read(text, GIVEN, { ...GIVEN, "speaker-0001": "Bob" })).toBe("Bob and Speaker 2 agreed.");
    expect(read(text, GIVEN, { ...GIVEN, "speaker-0001": "Bob", "speaker-0002": "Carol" })).toBe("Bob and Carol agreed.");
    expect(read(text, GIVEN, { ...GIVEN, "speaker-0001": "Speaker 2", "speaker-0002": "Speaker 1" }))
      .toBe("Speaker 2 and Speaker 1 agreed.");
    const stored = doc(text);
    expect(renameSummarySpeakers(stored, GIVEN, GIVEN)).toBe(stored);
  });

  it("follows a rename of a name the speaker already had when the summary was written (A to B to C)", () => {
    // Searching for the default label cannot do this: the text never said "Speaker 1".
    const given = { "speaker-0001": "Alice", "speaker-0002": "Speaker 2" };
    expect(read("Alice proposed the budget.", given, { ...given, "speaker-0001": "Alicia" })).toBe("Alicia proposed the budget.");
    expect(read("Alice proposed the budget.", given, { ...given, "speaker-0001": "Bob" })).toBe("Bob proposed the budget.");
  });

  it("leaves a default label that names nobody in this summary", () => {
    // speaker-0001 was already "Alice" when the summary was written, so "Speaker 1" here is the
    // meeting's own words, not a mention of speaker-0001; "Speaker 2" is another speaker's name.
    const given = { "speaker-0001": "Alice", "speaker-0002": "Speaker 2" };
    expect(read("Alice said the label Speaker 1 was wrong; Speaker 2 agreed.", given, { ...given, "speaker-0001": "Bob" }))
      .toBe("Bob said the label Speaker 1 was wrong; Speaker 2 agreed.");
  });

  it("does not touch a name inside an ordinary word or inside another person's name", () => {
    const given = { a: "Al", b: "Ann", c: "Ann Lee", d: "张伟", e: "张伟明" };
    const now = { ...given, a: "Albert", b: "Anna", d: "李雷" };
    expect(read("Also Al met Alan and McAl; Al's notes.", given, now)).toBe("Also Albert met Alan and McAl; Albert's notes.");
    expect(read("Ann and Ann Lee met Annabel; Ann left.", given, now)).toBe("Anna and Ann Lee met Annabel; Anna left.");
    expect(read("张伟和张伟明讨论了预算，张伟同意。", given, now)).toBe("李雷和张伟明讨论了预算，李雷同意。");
    // "You" is the first microphone voice; "Your" and "YouTube" are ordinary words.
    expect(read("You asked about YouTube. Your budget matters to You.", GIVEN, { ...GIVEN, "local-1": "Gao" }))
      .toBe("Gao asked about YouTube. Your budget matters to Gao.");
  });

  it("renames in Chinese text, where a name touches the next word", () => {
    // Real summary lines (prototypes/gemini-live/live-summary): the label is followed by a Chinese verb.
    const now = { ...GIVEN, "speaker-0001": "王芳", "speaker-0002": "Lex" };
    expect(read("Speaker 2介绍了哈维尔·米莱上任时的情况，Speaker 1提出疯子和天才之间的区别。", GIVEN, now))
      .toBe("Lex介绍了哈维尔·米莱上任时的情况，王芳提出疯子和天才之间的区别。");
    const given = { a: "王芳", b: "李雷" };
    expect(read("王芳认为预算太高，李雷不同意王芳的看法。", given, { a: "陈静", b: "李雷" }))
      .toBe("陈静认为预算太高，李雷不同意陈静的看法。");
  });

  it("shows a summary saved without its speaker names exactly as stored", () => {
    const stored = doc("Speaker 1 asked Speaker 2 about the plan.", { speaker_background: ["Speaker 1: host"] });
    expect(renameSummarySpeakers(stored, undefined, { "speaker-0001": "Alice", "speaker-0002": "Bob" })).toBe(stored);
  });

  it("leaves a name alone when it cannot say whom it means or what to show", () => {
    // Two voices were given one name and now differ: a mention could be either of them.
    const shared = { "speaker-0001": "Alice", "speaker-0003": "Alice" };
    expect(read("Alice spoke first.", shared, { "speaker-0001": "Alice", "speaker-0003": "Bob" })).toBe("Alice spoke first.");
    expect(read("Alice spoke first.", shared, { "speaker-0001": "Bob", "speaker-0003": "Bob" })).toBe("Bob spoke first.");
    // A speaker who is no longer in the transcript keeps the name the summary was written with.
    expect(read("Speaker 2 left early.", GIVEN, { "speaker-0001": "Alice" })).toBe("Speaker 2 left early.");
  });
});

describe("transcriptSpeakerNames", () => {
  const item = (speaker_entity_id: string, display_name: string) =>
    ({ start: 0, end: 1, text: "Words", speaker: speaker_entity_id, speaker_entity_id, display_name, state: "final" as const });

  it("reads each speaker's name as the transcript shows it, and none for unattributed speech", () => {
    expect(transcriptSpeakerNames([item("speaker-0001", "Alice"), item("speaker-0002", "speaker-0002"),
      item("local-1", "local-1"), item("local-2", "Priya"), item("S03", "S03"), item("S00", "Speaker TBD"),
      item("UNKNOWN", "Preview")]))
      .toEqual({ "speaker-0001": "Alice", "speaker-0002": "Speaker 2", "local-1": "You", "local-2": "Priya", S03: "Speaker 3" });
  });
});
