import { describe, expect, it } from "vitest";
import { buildTranscriptTargetKey, serializeTranscriptSegmentKey } from "./transcriptKeys";

describe("transcriptKeys", () => {
  it("prefers segment ids for target keys when available", () => {
    expect(
      buildTranscriptTargetKey({
        start: 0,
        end: 1.25,
        text: "Hello there",
        segment_id: "seg-123"
      })
    ).toBe("segment:seg-123");
  });

  it("falls back to rounded timing and normalized text", () => {
    expect(
      buildTranscriptTargetKey({
        start: 1.234,
        end: 3.456,
        text: "  Hello   there  ",
        segment_id: null
      })
    ).toBe("1.23|3.46|hello there");

    expect(serializeTranscriptSegmentKey(1.234, 3.456, "Hello   there")).toBe(
      "1.23|3.46|hello there"
    );
  });
});

it("keeps the legacy no-lane key even when speaker identity is present", () => {
  expect(buildTranscriptTargetKey({start: 0, end: 1, text: "Words", speaker: "S01", speaker_entity_id: "speaker-0001"}))
    .toBe("0.00|1.00|words");
});
it("retains lane and speaker disambiguation for lane-tagged rows", () => {
  for (const source_lane of ["system", "microphone"] as const) {
    expect(buildTranscriptTargetKey({start: 0, end: 1, text: "Words", source_lane, speaker: "S01", speaker_entity_id: "speaker-0001"}))
      .toBe(`0.00|1.00|words|${source_lane}|speaker-0001`);
  }
});
