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
