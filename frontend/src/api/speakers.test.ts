import { describe, expect, it, vi } from "vitest";
import { nameMeetingSpeaker } from "./speakers";

describe("speaker naming API", () => {
  it.each(["pending", "enrolled"])("accepts owner-bound %s results", async enrollment => {
    const payload = { meeting_id: "m", speaker_id: "s", label: "Alex", enrollment };
    expect(await nameMeetingSpeaker("m", "s", "Alex", vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))))).toEqual(payload);
  });

  it.each([
    { meeting_id: "other", speaker_id: "s", label: "Alex", enrollment: "pending" },
    { meeting_id: "m", speaker_id: "other", label: "Alex", enrollment: "pending" },
    { meeting_id: "m", speaker_id: "s", label: "Alex", enrollment: "maybe" }
  ])("rejects an unbound or malformed success", async payload => {
    await expect(nameMeetingSpeaker("m", "s", "Alex", vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))))).rejects.toThrow("response is invalid");
  });

  it("reports invalid JSON on a failed request without inventing success", async () => {
    await expect(nameMeetingSpeaker("m", "s", "Alex", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })))).rejects.toThrow("Speaker naming failed (503)");
  });
});
