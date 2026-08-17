import { describe, expect, it } from "vitest";
import type { TranscriptTurn } from "./mergeTranscript";
import { buildTranscriptExportText, serializeTranscriptExport } from "./transcriptExport";

describe("transcriptExport", () => {
  it("places speaker labels on their own line with blank lines between turns", () => {
    const turns: TranscriptTurn[] = [
      makeTurn(0, "SPEAKER_01", "First turn"),
      makeTurn(36, "SPEAKER_02", "Second turn")
    ];

    expect(buildTranscriptExportText(turns, (turn) => turn.display_name)).toBe(
      [
        "[00:00:00] SPEAKER_01:",
        "First turn",
        "",
        "[00:00:36] SPEAKER_02:",
        "Second turn"
      ].join("\n")
    );
  });

  it("serializes Markdown, text, and versioned JSON with resolved labels", () => {
    const turns = [makeTurn(36, "SPEAKER_02", "Second turn")];
    const resolveLabel = () => "Jamie";

    expect(serializeTranscriptExport("md", turns, resolveLabel)).toEqual({
      content: "## [00:00:36] Jamie\n\nSecond turn",
      filename: "transcript.md",
      mediaType: "text/markdown;charset=utf-8"
    });
    expect(serializeTranscriptExport("txt", turns, resolveLabel)).toEqual({
      content: "[00:00:36] Jamie:\nSecond turn",
      filename: "transcript.txt",
      mediaType: "text/plain;charset=utf-8"
    });

    const json = serializeTranscriptExport("json", turns, resolveLabel);
    expect(json.filename).toBe("transcript.json");
    expect(json.mediaType).toBe("application/json;charset=utf-8");
    expect(JSON.parse(json.content)).toEqual({
      version: 1,
      turns: [expect.objectContaining({
        start: 36,
        end: 37,
        speaker: "SPEAKER_02",
        speaker_label: "Jamie",
        state: "final",
        text: "Second turn"
      })]
    });
  });
});

function makeTurn(start: number, displayName: string, text: string): TranscriptTurn {
  return {
    start,
    end: start + 1,
    speaker: displayName,
    speaker_entity_id: displayName,
    display_name: displayName,
    state: "final",
    text,
    segment_ids: [],
    target_segment_keys: [],
    provisional_stale: false
  };
}
