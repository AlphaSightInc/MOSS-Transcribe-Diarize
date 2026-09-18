import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import type { Meeting } from "../api/meetings";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { serializeTranscriptExport } from "../lib/transcriptExport";

// Actual file task -> album -> MP3 archive -> restart -> rename + enrollment output.
const meeting: Meeting = JSON.parse(readFileSync(new URL(
  "../../../evidence/mvpfix/wp19/saved-file-fixture.json", import.meta.url), "utf8"));
it.each(["md", "txt", "json", "srt", "vtt"] as const)("exports saved file album identities as %s", format => {
  const items = meeting.transcript!.segments.map(s => ({ ...s,
    speaker_entity_id: s.speaker_entity_id ?? s.speaker,
    display_name: s.speaker, state: "confirmed" as const,
  }));
  const turns = groupSegmentsIntoTurns(items);
  expect(turns).toHaveLength(6);
  const file = serializeTranscriptExport(format, turns, t => t.display_name,
    {sessionId: meeting.id, exportedAt: new Date(0)});
  const content = format === "json"
    ? JSON.parse(file.content).turns.map((turn: {text: string}) => turn.text).join("\n")
    : file.content;
  expect(content.match(/alpha words/g)).toHaveLength(3);
  expect(content.match(/beta words/g)).toHaveLength(3);
  expect(file.content).toContain("Alice renamed");
  expect(file.content).toContain("S02");
  if (format === "srt" || format === "vtt") {
    expect(file.content).toContain(format === "srt" ? "00:04:20,000" : "00:04:20.000");
  }
});
