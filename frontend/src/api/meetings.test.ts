import { describe, expect, it, vi } from "vitest";
import { listMeetings, openMeeting, renameMeeting } from "./meetings";

const payload = {
  id: "meeting/one",
  mode: "live",
  title: null,
  title_source: "automatic",
  status: "active",
  created_at_ms: 10,
  transcript: {
    segments: [{ id: "seg_0001", start: 0, end: 1, speaker: "S01", text: "hello" }]
  },
  transcript_version: 1,
  audio: null
};

describe("Account Meeting API", () => {
  it("loads the one mixed-mode list and opens an encoded Meeting ID", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ meetings: [payload] }))
      .mockResolvedValueOnce(response(payload));

    expect(await listMeetings(fetcher)).toEqual([payload]);
    expect(await openMeeting("meeting/one", fetcher)).toEqual(payload);
    expect(fetcher.mock.calls[1][0]).toBe("/api/meetings/meeting%2Fone");
  });

  it("writes owner title through the dedicated route and exposes server detail", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ id: "meeting/one", title: "Owner title", title_source: "manual" }))
      .mockResolvedValueOnce(response({ detail: "Meeting not found." }, 404));

    expect(await renameMeeting("meeting/one", "Owner title", fetcher)).toEqual({
      id: "meeting/one",
      title: "Owner title",
      title_source: "manual"
    });
    expect(fetcher.mock.calls[0]).toEqual([
      "/api/meetings/meeting%2Fone/title",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ title: "Owner title" }) })
    ]);
    await expect(openMeeting("foreign", fetcher)).rejects.toThrow("Meeting not found.");
  });

  it("rejects malformed durable history instead of guessing", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ meetings: [{ ...payload, title_source: "unknown" }] }));
    await expect(listMeetings(fetcher)).rejects.toThrow("Meeting response is invalid.");
  });
});

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as Response;
}
