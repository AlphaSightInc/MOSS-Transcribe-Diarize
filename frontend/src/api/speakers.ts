export interface SpeakerNameResult {
  meeting_id: string;
  speaker_id: string;
  label: string;
  enrollment: "pending" | "enrolled" | "not_requested" | "unavailable";
}

export interface Voiceprint {
  id: string;
  label: string;
  sample_count: number;
  compatibility?: "compatible" | "re_enrollment_required";
}

export async function listVoiceprints(): Promise<Voiceprint[]> {
  const response = await fetch("/api/voiceprints", { cache: "no-store", credentials: "same-origin" });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not load voiceprints.");
  if (!Array.isArray(payload?.voiceprints) || payload.voiceprints.some((v: Voiceprint) =>
    typeof v?.id !== "string" || typeof v?.label !== "string" || typeof v?.sample_count !== "number")) {
    throw new Error("Voiceprint list is invalid.");
  }
  return payload.voiceprints;
}

export async function changeVoiceprint(id: string, label: string | null): Promise<void> {
  const response = await fetch(`/api/voiceprints/${encodeURIComponent(id)}${label === null ? "" : "/name"}`, {
    method: label === null ? "DELETE" : "PUT", credentials: "same-origin",
    ...(label === null ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label }) })
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Voiceprint change failed.");
  if (payload?.id !== id || payload?.deleted !== (label === null)) throw new Error("Voiceprint change response is invalid.");
}

export async function nameMeetingSpeaker(
  meetingId: string,
  speakerId: string,
  label: string,
  fetcher: typeof fetch = fetch,
  saveVoiceprint = true
): Promise<SpeakerNameResult> {
  const response = await fetcher(
    `/api/meetings/${encodeURIComponent(meetingId)}/speakers/${encodeURIComponent(speakerId)}/name`,
    {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(saveVoiceprint ? { label } : { label, save_voiceprint: false })
    }
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === "string" ? payload.detail : `Speaker naming failed (${response.status}).`);
  }
  if (payload?.meeting_id !== meetingId || payload?.speaker_id !== speakerId ||
      typeof payload?.label !== "string" || !["pending", "enrolled", "not_requested", "unavailable"].includes(payload?.enrollment)) {
    throw new Error("Speaker naming response is invalid.");
  }
  return payload;
}
