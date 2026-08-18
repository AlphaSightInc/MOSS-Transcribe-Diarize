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
    const identity = {
      sessionId: "session-42",
      exportedAt: new Date("2026-08-18T20:00:16.182Z")
    };

    expect(serializeTranscriptExport("md", turns, resolveLabel, identity)).toEqual({
      content: "## [00:00:36] Jamie\n\nSecond turn",
      filename: "transcript-session-42-2026-08-18T20:00:16.182Z.md",
      mediaType: "text/markdown;charset=utf-8"
    });
    expect(serializeTranscriptExport("txt", turns, resolveLabel, identity)).toEqual({
      content: "[00:00:36] Jamie:\nSecond turn",
      filename: "transcript-session-42-2026-08-18T20:00:16.182Z.txt",
      mediaType: "text/plain;charset=utf-8"
    });

    const json = serializeTranscriptExport("json", turns, resolveLabel, identity);
    expect(json.filename).toBe("transcript-session-42-2026-08-18T20:00:16.182Z.json");
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

  it.each(["confirmed", "provisional"] as const)(
    "marks %s exports in every format until finalization",
    (state) => {
      const turns = [makeTurn(36, "SPEAKER_02", "Second turn", { state })];
      const caveat = "Speaker attribution is provisional and may be revised by the retrospective sweep after the session ends.";
      const resolveLabel = () => "Jamie";
      const identity = {
        sessionId: "session-42",
        exportedAt: new Date("2026-08-18T20:00:16.182Z")
      };

      expect(serializeTranscriptExport("md", turns, resolveLabel, identity).content).toContain(
        `> **Provisional attribution:** ${caveat}`
      );
      expect(serializeTranscriptExport("txt", turns, resolveLabel, identity).content).toContain(
        `Provisional attribution: ${caveat}`
      );
      expect(JSON.parse(serializeTranscriptExport("json", turns, resolveLabel, identity).content)).toMatchObject({
        provisional_attribution_notice: `Provisional attribution: ${caveat}`
      });
    }
  );
});

function makeTurn(
  start: number,
  displayName: string,
  text: string,
  overrides: Partial<TranscriptTurn> = {}
): TranscriptTurn {
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
    provisional_stale: false,
    ...overrides
  };
}
