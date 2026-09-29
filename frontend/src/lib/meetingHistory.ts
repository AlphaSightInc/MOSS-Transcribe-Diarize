import type { Meeting } from "../api/meetings";

export type TerminalDayBucket = "today" | "yesterday" | "earlier";

export interface MeetingHistoryGroup {
  key: "active" | `terminal-${TerminalDayBucket}`;
  label: "Active" | "Today" | "Yesterday" | "Earlier";
  meetings: Meeting[];
}

const TERMINAL_BUCKETS: Array<{
  bucket: TerminalDayBucket;
  label: "Today" | "Yesterday" | "Earlier";
}> = [
  { bucket: "today", label: "Today" },
  { bucket: "yesterday", label: "Yesterday" },
  { bucket: "earlier", label: "Earlier" }
];

export function meetingTitle(meeting: Pick<Meeting, "mode" | "title">): string {
  return meeting.title?.trim() || `${meeting.mode === "live" ? "Live" : "File"} meeting`;
}

export function filterMeetings(meetings: readonly Meeting[], query: string): Meeting[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [...meetings];
  return meetings.filter((meeting) =>
    [
      meetingTitle(meeting),
      meeting.mode,
      meeting.status,
      ...(meeting.transcript?.segments.map((segment) => segment.text) ?? [])
    ].join(" ").toLowerCase().includes(normalized)
  );
}

export function groupMeetings(
  meetings: readonly Meeting[],
  now: Date = new Date()
): MeetingHistoryGroup[] {
  const ordered = [...meetings].sort(compareMeetings);
  const active = ordered.filter((meeting) => meeting.status === "active");
  const terminal = ordered.filter((meeting) => meeting.status !== "active");
  const groups: MeetingHistoryGroup[] = active.length > 0
    ? [{ key: "active", label: "Active", meetings: active }]
    : [];
  for (const { bucket, label } of TERMINAL_BUCKETS) {
    const bucketMeetings = terminal.filter(
      (meeting) => meetingDayBucket(meeting.created_at_ms, now) === bucket
    );
    if (bucketMeetings.length > 0) {
      groups.push({ key: `terminal-${bucket}`, label, meetings: bucketMeetings });
    }
  }
  return groups;
}

export function reconcileSelectedMeeting(
  meetings: readonly Meeting[],
  selected: Meeting | null
): Meeting | null {
  if (selected === null) return null;
  return meetings.find((meeting) => meeting.id === selected.id) ?? null;
}

export function meetingDayBucket(createdAtMs: number, now: Date = new Date()): TerminalDayBucket {
  const created = new Date(createdAtMs);
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const createdStart = new Date(
    created.getFullYear(),
    created.getMonth(),
    created.getDate()
  ).getTime();
  const days = Math.round((todayStart - createdStart) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return "earlier";
}

export function formatMeetingDuration(meeting: Pick<Meeting, "audio" | "transcript">): string | null {
  const audioSeconds = meeting.audio?.duration_ms != null && meeting.audio.duration_ms > 0
    ? meeting.audio.duration_ms / 1000 : null;
  const transcriptSeconds = meeting.transcript?.segments.reduce(
    (latest, segment) => Math.max(latest, segment.end), 0
  ) ?? 0;
  const duration = audioSeconds ?? transcriptSeconds;
  if (!(duration > 0) || !Number.isFinite(duration)) return null;
  const seconds = Math.ceil(duration);
  const minutes = Math.floor(seconds / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  return minutes < 60 ? `${minutes}:${remainder}`
    : `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}:${remainder}`;
}

export function formatMeetingTimestamp(createdAtMs: number, now: Date = new Date()): string {
  const date = new Date(createdAtMs);
  const bucket = meetingDayBucket(createdAtMs, now);
  if (bucket === "earlier") {
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function compareMeetings(left: Meeting, right: Meeting): number {
  const leftRank = left.status === "active" ? 0 : 1;
  const rightRank = right.status === "active" ? 0 : 1;
  const ranked = leftRank - rightRank || right.created_at_ms - left.created_at_ms;
  if (ranked !== 0 || left.id === right.id) return ranked;
  // Meeting IDs use the ASCII base64url alphabet. Relational comparison preserves the same
  // binary/code-point order as SQLite's default BINARY collation; localeCompare does not.
  return left.id < right.id ? 1 : -1;
}
