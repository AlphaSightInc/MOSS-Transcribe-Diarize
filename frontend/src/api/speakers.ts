export interface SpeakerNameResult {
  meeting_id: string;
  speaker_id: string;
  label: string;
  enrollment: "pending" | "enrolled" | "not_requested" | "unavailable";
}

export interface PassageSpeakerResult {
  meeting_id: string;
  segment_ids: string[];
  speaker_id: string;
  label: string;
  transcript_version: number;
  needs_review: boolean;
}

export type PassageSpeakerTarget = { speaker_id: string } | { label: string };

export async function editMeetingPassageText(
  meetingId: string, passageId: string, text: string, fetcher: typeof fetch = fetch
): Promise<PassageSpeakerResult> {
  const response = await fetcher(
    `/api/meetings/${encodeURIComponent(meetingId)}/passages/${encodeURIComponent(passageId)}/text`,
    { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }) }
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail
    : payload?.code === "refinement_running" ? "Wait until the transcript finishes improving."
    : `Text edit failed (${response.status}).`);
  if (payload?.meeting_id !== meetingId || !Array.isArray(payload?.segment_ids) ||
      payload.segment_ids.length !== 1 || payload.segment_ids[0] !== passageId ||
      typeof payload?.speaker_id !== "string" || typeof payload?.label !== "string" ||
      typeof payload?.transcript_version !== "number" || typeof payload?.needs_review !== "boolean") {
    throw new Error("Text edit response is invalid.");
  }
  return payload;
}

const VOICEPRINT_EVIDENCE_NOT_ADMITTED = "voiceprint_evidence_not_admitted";
const VOICEPRINT_REFUSAL_COPY = "Save voiceprint needs at least 2 seconds of finished, clear speech from this speaker.";

export class VoiceprintEvidenceNotAdmittedError extends Error {
  readonly code = VOICEPRINT_EVIDENCE_NOT_ADMITTED;
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
    const detail = payload?.detail;
    const message = typeof detail?.message === "string" && detail.message.trim()
      ? detail.message
      : null;
    if (payload?.detail?.code === VOICEPRINT_EVIDENCE_NOT_ADMITTED) {
      throw new VoiceprintEvidenceNotAdmittedError(message || VOICEPRINT_REFUSAL_COPY);
    }
    throw new Error(message || (typeof detail === "string" ? detail : `Speaker naming failed (${response.status}).`));
  }
  if (payload?.meeting_id !== meetingId || payload?.speaker_id !== speakerId ||
      typeof payload?.label !== "string" || !["pending", "enrolled", "not_requested", "unavailable"].includes(payload?.enrollment)) {
    throw new Error("Speaker naming response is invalid.");
  }
  return payload;
}

export async function reassignMeetingPassages(
  meetingId: string,
  segmentIds: string[],
  target: PassageSpeakerTarget,
  fetcher: typeof fetch = fetch
): Promise<PassageSpeakerResult> {
  const response = await fetcher(
    `/api/meetings/${encodeURIComponent(meetingId)}/passages/speaker`,
    {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_ids: segmentIds, ...target })
    }
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === "string"
      ? payload.detail
      : `Passage correction failed (${response.status}).`);
  }
  if (payload?.meeting_id !== meetingId || !Array.isArray(payload?.segment_ids) ||
      payload.segment_ids.some((value: unknown) => typeof value !== "string") ||
      typeof payload?.speaker_id !== "string" || typeof payload?.label !== "string" ||
      typeof payload?.transcript_version !== "number" || typeof payload?.needs_review !== "boolean") {
    throw new Error("Passage correction response is invalid.");
  }
  return payload;
}
