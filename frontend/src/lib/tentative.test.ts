import { describe, expect, it } from "vitest";
import { projectTentativeBlocks, projectTentativeSegments, tentativeTurns } from "./tentative";

const samples = (seconds: number) => seconds * 16_000;

describe("Gemini preview guesses", () => {
  it("keeps explicit lanes when preview words overlap in time", () => {
    expect(projectTentativeSegments([
      { start_sample: samples(1), end_sample: samples(1.5), text: "remote",
        source_lane: "system", tentative_speaker: "speaker-1" },
      { start_sample: samples(1), end_sample: samples(1.5), text: "local",
        source_lane: "microphone", tentative_speaker: "local-0001" }
    ], { "speaker-1": "Ben", "local-0001": "Sam" })).toEqual([
      { speakerId: "speaker-1", label: "Ben", tentative: true, lane: "system",
        start: 1, end: 1.5, text: "remote" },
      { speakerId: "local-0001", label: "Sam", tentative: true, lane: "microphone",
        start: 1, end: 1.5, text: "local" }
    ]);
  });

  it("shows a guessed name as the plain name (issue #7: no question mark) and keeps abstention honest", () => {
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
      { speakerId: "speaker-1", label: "Ben", tentative: true, lane: "system",
        start: 1, end: 2, text: "hello there" },
      { speakerId: null, label: "Speaker TBD", tentative: false, lane: "system",
        start: 2, end: 2.5, text: "stranger" }
    ]);
  });

  it("never shows a raw id or a questioned neutral label", () => {
    const blocks = projectTentativeSegments([
      { start_sample: 0, end_sample: samples(1), text: "unlabelled", source_lane: "system", tentative_speaker: "speaker-0007" },
      { start_sample: samples(1), end_sample: samples(2), text: "unknown", source_lane: "system", tentative_speaker: "speaker-0008" },
      { start_sample: samples(2), end_sample: samples(3), text: "none", source_lane: "system", tentative_speaker: null }
    ], { "speaker-0008": "Speaker TBD" });
    expect(blocks.map(block => block.label)).toEqual(["Speaker TBD", "Speaker TBD", "Speaker TBD"]);
  });

  it("shapes guess blocks as provisional transcript rows", () => {
    const [turn] = tentativeTurns([{ speakerId: "local-0001", label: "You", tentative: true, lane: "microphone",
      start: 1, end: 2, text: "hi there" }]);
    expect(turn).toMatchObject({ source_lane: "microphone", speaker_entity_id: "local-0001", display_name: "You",
      state: "provisional", segment_ids: [], target_segment_keys: ["tentative:microphone:1"],
      segments: [{ start: 1, end: 2, text: "hi there" }] });
    expect(tentativeTurns([{ speakerId: null, label: "Speaker TBD", tentative: false, lane: "system",
      start: 0, end: 1, text: "x" }])[0]?.speaker_entity_id).toBe("S00");
  });
});
