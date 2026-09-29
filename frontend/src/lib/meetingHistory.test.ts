import { describe, expect, it } from "vitest";
import type { Meeting } from "../api/meetings";
import {
  filterMeetings,
  formatMeetingDuration,
  groupMeetings,
  meetingDayBucket,
  reconcileSelectedMeeting
} from "./meetingHistory";

const now = new Date(2026, 7, 28, 12, 0, 0);

function meeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: "meeting-a",
    mode: "live",
    title: null,
    title_source: "automatic",
    status: "completed",
    created_at_ms: now.getTime(),
    transcript: null,
    transcript_version: 0,
    audio: null,
    ...overrides
  };
}

describe("Meeting history projection", () => {
  it("puts every active Meeting first, then terminal local-day groups, newest-first", () => {
    const groups = groupMeetings([
      meeting({ id: "terminal-new", status: "completed", created_at_ms: now.getTime() - 1_000 }),
      meeting({ id: "active-old", status: "active", created_at_ms: now.getTime() - 4 * 86_400_000 }),
      meeting({ id: "active-new", status: "active", created_at_ms: now.getTime() - 500 }),
      meeting({ id: "a-token", status: "failed", created_at_ms: now.getTime() - 2_000 }),
      meeting({ id: "_token", status: "interrupted", created_at_ms: now.getTime() - 2_000 }),
      meeting({ id: "Z-token", status: "failed", created_at_ms: now.getTime() - 2_000 }),
      meeting({ id: "-token", status: "interrupted", created_at_ms: now.getTime() - 2_000 }),
      meeting({ id: "yesterday", created_at_ms: new Date(2026, 7, 27, 9).getTime() }),
      meeting({ id: "earlier", created_at_ms: new Date(2026, 7, 20, 9).getTime() })
    ], now);

    expect(groups.map((group) => group.label)).toEqual(["Active", "Today", "Yesterday", "Earlier"]);
    expect(groups[0].meetings.map(({ id }) => id)).toEqual(["active-new", "active-old"]);
    expect(groups[1].meetings.map(({ id }) => id)).toEqual([
      "terminal-new",
      "a-token",
      "_token",
      "Z-token",
      "-token"
    ]);
  });

  it("shows recorded duration first, then transcript extent, and leaves unknown blank", () => {
    expect(formatMeetingDuration(meeting())).toBeNull();
    expect(formatMeetingDuration(meeting({ transcript: { segments: [
      { start: 0, end: 61, speaker: "S01", text: "hello" }
    ] } }))).toBe("1:01");
    expect(formatMeetingDuration(meeting({ audio: {
      state: "available", relative_path: "meeting.mp3", byte_count: 1, duration_ms: 3_661_000,
      format: "mp3", sample_rate_hz: 16_000, channels: 1, bit_rate_bps: 48_000
    }, transcript: { segments: [{ start: 0, end: 12, speaker: "S01", text: "hello" }] } }))).toBe("1:01:01");
  });

  it("uses local calendar boundaries rather than elapsed 24-hour windows", () => {
    const shortlyBeforeMidnight = new Date(2026, 7, 27, 23, 45).getTime();
    expect(meetingDayBucket(shortlyBeforeMidnight, new Date(2026, 7, 28, 0, 15))).toBe("yesterday");
  });

  it("searches all shared fields and repairs a stale selected record", () => {
    const selected = meeting({ id: "url", title: "Old title" });
    const refreshed = meeting({
      id: "url",
      mode: "file",
      title: "Customer review",
      title_source: "manual",
      transcript: {
        segments: [{ start: 0, end: 1, speaker: "S01", text: "URL sentinel" }]
      }
    });
    expect(filterMeetings([refreshed], "url SENTINEL")).toEqual([refreshed]);
    expect(reconcileSelectedMeeting([refreshed], selected)).toBe(refreshed);
    expect(reconcileSelectedMeeting([], selected)).toBeNull();
  });
});
