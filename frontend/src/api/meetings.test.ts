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

  it("loads attributed and unattributed Live rows without inventing canonical ownership", async () => {
    const mixed = { ...payload, transcript: { segments: [
      { id: "one", start: 0, end: 1, speaker: "Alex", speaker_entity_id: "canonical-a", text: "Named speech" },
      { id: "two", start: 1, end: 2, speaker: "S00", text: "Unattributed speech" }
    ] } };
    const fetcher = vi.fn().mockResolvedValue(response({ meetings: [mixed] }));
    expect(await listMeetings(fetcher)).toEqual([mixed]);
    expect((await listMeetings(fetcher))[0].transcript?.segments[1]).not.toHaveProperty("speaker_entity_id");
  });

  it("reads the content-free refinement state on list and detail", async () => {
    const running = { ...payload, status: "completed", refinement_state: "running" };
    const fetcher = vi.fn().mockResolvedValueOnce(response({ meetings: [running] })).mockResolvedValueOnce(response(running));
    expect((await listMeetings(fetcher))[0].refinement_state).toBe("running");
    expect((await openMeeting(running.id, fetcher)).refinement_state).toBe("running");
  });
});

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as Response;
}


it("preserves saved interruption metadata beside speech for History and exports", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...payload,
    transcript: { ...payload.transcript, sample_rate: 32000, capture_interruptions: [{ start_sample: 115_200_000, end_sample: 116_160_000 }] } }) });
  const meeting = await openMeeting("meeting/one", fetcher);
  expect(meeting.transcript?.interruptions).toEqual([{ start: 3600, end: 3630 }]);
  expect(meeting.transcript?.segments).toHaveLength(1);
  expect(meeting.transcript?.segments[0].text).toBe("hello");
});
