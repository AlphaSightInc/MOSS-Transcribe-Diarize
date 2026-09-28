import { describe, expect, it, vi } from "vitest";
import { nameMeetingSpeaker, reassignMeetingPassages } from "./speakers";

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

  it("shows a structured server message, including a voiceprint refusal", async () => {
    const plain = "Save voiceprint needs more clear speech. You can name the speaker without it.";
    const refused = vi.fn().mockResolvedValue(Response.json({ detail: {
      code: "voiceprint_evidence_not_admitted", message: plain
    } }, { status: 400 }));
    await expect(nameMeetingSpeaker("m", "s", "Alex", refused)).rejects.toThrow(plain);
    const other = vi.fn().mockResolvedValue(Response.json({ detail: {
      code: "another_refusal", message: "This name cannot be saved yet."
    } }, { status: 400 }));
    await expect(nameMeetingSpeaker("m", "s", "Alex", other)).rejects.toThrow("This name cannot be saved yet.");
  });

  it("keeps plain refusal copy if a coded response omits its message", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ detail: {
      code: "voiceprint_evidence_not_admitted"
    } }, { status: 400 }));
    await expect(nameMeetingSpeaker("m", "s", "Alex", fetcher)).rejects.toThrow("at least 2 seconds of finished, clear speech");
  });
});

describe("settled passage correction API", () => {
  it.each([
    [{ speaker_id: "person-a" }, { speaker_id: "person-a" }],
    [{ label: "Blair" }, { label: "Blair" }]
  ] as const)("sends an exact recording-local target", async (target, expectedTarget) => {
    const payload = {
      meeting_id: "m",
      segment_ids: ["seg_0002"],
      speaker_id: "speaker_id" in target ? target.speaker_id : "manual-one",
      label: "label" in target ? target.label : "Alex",
      transcript_version: 2,
      needs_review: false
    };
    const fetcher = vi.fn().mockResolvedValue(Response.json(payload));
    expect(await reassignMeetingPassages("m", ["seg_0002"], target, fetcher)).toEqual(payload);
    expect(fetcher).toHaveBeenCalledWith("/api/meetings/m/passages/speaker", expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ segment_ids: ["seg_0002"], ...expectedTarget })
    }));
  });

  it("keeps the settled-only refusal visible", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json(
      { detail: "Wait for automatic processing to settle before correcting speakers." },
      { status: 409 }
    ));
    await expect(reassignMeetingPassages("m", ["seg"], { label: "Blair" }, fetcher))
      .rejects.toThrow("Wait for automatic processing to settle");
  });
});
