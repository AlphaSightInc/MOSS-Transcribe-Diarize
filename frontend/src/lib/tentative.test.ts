import { describe, expect, it } from "vitest";
import { projectTentativeBlocks } from "./tentative";

const samples = (seconds: number) => seconds * 16_000;

describe("Gemini preview guesses", () => {
  it("shows a guessed name with a question mark and keeps abstention honest", () => {
    const words = [
      { start: 1, end: 1.5, text: "hello", source_lane: "system" },
      { start: 1.5, end: 2, text: "there", source_lane: "system" },
      { start: 2, end: 2.5, text: "stranger", source_lane: "system" }
    ];
    const spans = [
      { start_sample: samples(1), end_sample: samples(1.5), source_lane: "system", speaker: "speaker-1" },
      { start_sample: samples(1.5), end_sample: samples(2), source_lane: "system", speaker: "speaker-1" }
    ];
    expect(projectTentativeBlocks(words, spans, { "speaker-1": "Ben" })).toEqual([
      { speakerId: "speaker-1", label: "Ben?", tentative: true, lane: "system",
        start: 1, end: 2, text: "hello there" },
      { speakerId: null, label: "Speaker TBD", tentative: false, lane: "system",
        start: 2, end: 2.5, text: "stranger" }
    ]);
  });
});
