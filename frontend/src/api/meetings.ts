export type MeetingMode = "live" | "file";
export type MeetingStatus = "active" | "completed" | "failed" | "interrupted";
export type MeetingTitleSource = "automatic" | "manual";

export interface MeetingSegment {
  id?: string;
  start: number;
  end: number;
  speaker: string;
  speaker_entity_id?: string;
  text: string;
}

export interface MeetingAudio {
  state: "available" | "partial" | "unavailable";
  relative_path: string | null;
  byte_count: number | null;
  duration_ms: number | null;
  format: string | null;
  sample_rate_hz: number | null;
  channels: number | null;
  bit_rate_bps: number | null;
}

export interface Meeting {
  id: string;
  mode: MeetingMode;
  title: string | null;
  title_source: MeetingTitleSource;
  status: MeetingStatus;
  created_at_ms: number;
  transcript: { segments: MeetingSegment[] } | null;
  transcript_version: number;
  audio: MeetingAudio | null;
}

export async function listMeetings(fetcher: typeof fetch = fetch): Promise<Meeting[]> {
  const payload = await requestJson(fetcher, "/api/meetings");
  if (!isRecord(payload) || !Array.isArray(payload.meetings)) {
    throw new Error("Meeting history response is invalid.");
  }
  return payload.meetings.map(parseMeeting);
}

export async function openMeeting(
  meetingId: string,
  fetcher: typeof fetch = fetch
): Promise<Meeting> {
  return parseMeeting(await requestJson(fetcher, `/api/meetings/${encodeURIComponent(meetingId)}`));
}

export async function renameMeeting(
  meetingId: string,
  title: string,
  fetcher: typeof fetch = fetch
): Promise<{ id: string; title: string; title_source: "manual" }> {
  const payload = await requestJson(fetcher, `/api/meetings/${encodeURIComponent(meetingId)}/title`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title })
  });
  if (
    !isRecord(payload) ||
    typeof payload.id !== "string" ||
    typeof payload.title !== "string" ||
    payload.title_source !== "manual"
  ) {
    throw new Error("Meeting rename response is invalid.");
  }
  return { id: payload.id, title: payload.title, title_source: payload.title_source };
}

async function requestJson(
  fetcher: typeof fetch,
  input: string,
  init?: RequestInit
): Promise<unknown> {
  const response = await fetcher(input, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(payload) && typeof payload.detail === "string"
      ? payload.detail
      : `Meeting request failed (${response.status}).`;
    throw new Error(detail);
  }
  return payload;
}

function parseMeeting(value: unknown): Meeting {
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    (value.mode !== "live" && value.mode !== "file") ||
    (value.title !== null && typeof value.title !== "string") ||
    (value.title_source !== "automatic" && value.title_source !== "manual") ||
    !isMeetingStatus(value.status) ||
    typeof value.created_at_ms !== "number" ||
    typeof value.transcript_version !== "number"
  ) {
    throw new Error("Meeting response is invalid.");
  }
  return {
    id: value.id,
    mode: value.mode,
    title: value.title,
    title_source: value.title_source,
    status: value.status,
    created_at_ms: value.created_at_ms,
    transcript: parseTranscript(value.transcript),
    transcript_version: value.transcript_version,
    audio: parseAudio(value.audio)
  };
}

function parseTranscript(value: unknown): Meeting["transcript"] {
  if (value === null) return null;
  if (!isRecord(value) || !Array.isArray(value.segments)) {
    throw new Error("Meeting transcript is invalid.");
  }
  return {
    segments: value.segments.map((segment) => {
      if (
        !isRecord(segment) ||
        (segment.id !== undefined && typeof segment.id !== "string") ||
        typeof segment.start !== "number" ||
        typeof segment.end !== "number" ||
        typeof segment.speaker !== "string" ||
        (segment.speaker_entity_id !== undefined && typeof segment.speaker_entity_id !== "string") ||
        typeof segment.text !== "string"
      ) {
        throw new Error("Meeting transcript segment is invalid.");
      }
      return {
        ...(typeof segment.id === "string" ? { id: segment.id } : {}),
        start: segment.start,
        end: segment.end,
        speaker: segment.speaker,
        ...(typeof segment.speaker_entity_id === "string" ? { speaker_entity_id: segment.speaker_entity_id } : {}),
        text: segment.text
      };
    })
  };
}

function parseAudio(value: unknown): MeetingAudio | null {
  if (value === null || value === undefined) return null;
  if (
    !isRecord(value) ||
    (value.state !== "available" && value.state !== "partial" && value.state !== "unavailable")
  ) {
    throw new Error("Meeting audio response is invalid.");
  }
  const relativePath = nullableString(value.relative_path);
  const byteCount = nullableNumber(value.byte_count);
  const durationMs = nullableNumber(value.duration_ms);
  const format = nullableString(value.format);
  const sampleRateHz = nullableNumber(value.sample_rate_hz);
  const channels = nullableNumber(value.channels);
  const bitRateBps = nullableNumber(value.bit_rate_bps);
  if (
    relativePath === undefined ||
    byteCount === undefined ||
    durationMs === undefined ||
    format === undefined ||
    sampleRateHz === undefined ||
    channels === undefined ||
    bitRateBps === undefined
  ) {
    throw new Error("Meeting audio response is invalid.");
  }
  return {
    state: value.state,
    relative_path: relativePath,
    byte_count: byteCount,
    duration_ms: durationMs,
    format,
    sample_rate_hz: sampleRateHz,
    channels,
    bit_rate_bps: bitRateBps
  };
}

function isMeetingStatus(value: unknown): value is MeetingStatus {
  return value === "active" || value === "completed" || value === "failed" || value === "interrupted";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function nullableString(value: unknown): string | null | undefined {
  return value === null || typeof value === "string" ? value : undefined;
}

function nullableNumber(value: unknown): number | null | undefined {
  return value === null || typeof value === "number" ? value : undefined;
}
