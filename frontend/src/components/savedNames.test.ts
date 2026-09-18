import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import type { Meeting } from "../api/meetings";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { serializeTranscriptExport } from "../lib/transcriptExport";
import { providerBody } from "../lib/finalSummary";

// Actual ASGI/store replay output: each rename is followed by GET and history.
const cases: { case: string; status: number; meeting: Meeting; history: Meeting }[] = JSON.parse(
  readFileSync(new URL("../../../evidence/mvpfix/wp9/prototype-latest.json", import.meta.url), "utf8")
);
it.each(cases)("preserves saved $case names in five exports and summary input", row => {
  expect(row.status).toBe(200);
  expect(row.history).toEqual(row.meeting);
  const label = `WP9 ${row.case}`;
  const items = row.meeting.transcript!.segments.map(s => ({ ...s,
    speaker_entity_id: s.speaker_entity_id ?? s.speaker,
    display_name: s.speaker, state: "confirmed" as const
  }));
  const turns = groupSegmentsIntoTurns(items);
  for (const format of ["md", "txt", "json", "srt", "vtt"] as const) {
    expect(serializeTranscriptExport(format, turns, t => t.display_name,
      {sessionId: row.meeting.id, exportedAt: new Date(0)}).content).toContain(label);
  }
  if (row.meeting.status === "completed") {
    expect(providerBody(row.meeting, {endpoint:"", model:"test", apiKey:"", prompt:"Summarize",
      language:"English", timeoutSeconds:60})).toContain(label);
  }
});
