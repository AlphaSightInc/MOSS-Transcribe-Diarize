export interface SpeakerNameResult {
  meeting_id: string;
  speaker_id: string;
  label: string;
  enrollment: "pending" | "enrolled";
}

export async function nameMeetingSpeaker(
  meetingId: string,
  speakerId: string,
  label: string,
  fetcher: typeof fetch = fetch
): Promise<SpeakerNameResult> {
  const response = await fetcher(
    `/api/meetings/${encodeURIComponent(meetingId)}/speakers/${encodeURIComponent(speakerId)}/name`,
    {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label })
    }
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === "string" ? payload.detail : `Speaker naming failed (${response.status}).`);
  }
  if (payload?.meeting_id !== meetingId || payload?.speaker_id !== speakerId ||
      typeof payload?.label !== "string" || !["pending", "enrolled"].includes(payload?.enrollment)) {
    throw new Error("Speaker naming response is invalid.");
  }
  return payload;
}
