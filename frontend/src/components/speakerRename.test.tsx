// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import { TranscriptPane } from "./TranscriptPane";
import { MeetingHistory } from "./MeetingHistory";
import { createMossSessionPoller } from "../api/mossPoller";
import { SPEAKER_NAMED_EVENT } from "../lib/meetingEvents";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { serializeTranscriptExport } from "../lib/transcriptExport";
import { captureMeetingId, replaceTranscript, resetSessionState, sessionId, sessionStatus, transcript } from "../state/session";

const root = document.createElement("div");
document.body.append(root);
afterEach(() => { act(() => render(null, root)); resetSessionState(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it.each([".utt-speaker", ".legend-chip"])("renames from %s across repeated rows, legend, history reopen and export", async selector => {
  let name = "Before";
  const meeting = () => ({ id: "m", title: "Meeting", title_source: "manual", mode: "live", status: "active", created_at_ms: 1,
    transcript_version: name === "Before" ? 1 : 2, audio: null, transcript: { segments: ["a", "b", "a"].map((id, i) => ({
      id: String(i), start: i, end: i + 1, speaker_entity_id: id, speaker: id === "a" ? name : "Other", text: `Words ${i}`
    })) } });
  vi.stubGlobal("fetch", vi.fn(async (url, init) => {
    if (String(url).endsWith("/speakers/a/name")) {
      name = JSON.parse(init.body).label;
      return Response.json({ meeting_id: "m", speaker_id: "a", label: name, enrollment: "pending" });
    }
    return Response.json(String(url) === "/api/meetings" ? { meetings: [meeting()] } : meeting());
  }));
  await act(async () => {
    sessionId.value = captureMeetingId.value = "m"; sessionStatus.value = "active";
    replaceTranscript(meeting().transcript.segments.map(s => ({ ...s, speaker: s.speaker_entity_id === "a" ? "S01" : "S02", display_name: s.speaker, state: "confirmed" })));
    render(<><TranscriptPane /><MeetingHistory /></>, root);
  });
  await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="m"]')).not.toBeNull());
  act(() => root.querySelector<HTMLButtonElement>(selector)!.click());
  act(() => {
    const input = root.querySelector<HTMLInputElement>('#speaker-name-input')!;
    input.value = "After"; input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { root.querySelector('dialog form')!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  const assertNames = () => {
    expect([...root.querySelectorAll('.utt-speaker-label')].map(n => n.textContent)).toEqual(["After", "Other", "After"]);
    expect([...root.querySelectorAll('.legend-chip-name')].map(n => n.textContent)).toEqual(["After", "Other"]);
    for (const format of ["md", "txt", "json"] as const) {
      const file = serializeTranscriptExport(format, groupSegmentsIntoTurns(transcript.value), t => t.display_name,
        { sessionId: "m", exportedAt: new Date(0) });
      expect(file.content).toContain("After"); expect(file.content).not.toContain("Before");
    }
  };
  await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());
  assertNames();
  await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="m"]')!.click());
  await vi.waitFor(assertNames);
});

it("discards a pre-rename poll response and fetches the acknowledged labels", async () => {
  let release!: (value: Response) => void;
  let snapshots = 0;
  const dispatched: unknown[] = [];
  const payload = (label: string) => ({ speaker_label_revision: label === "Before" ? 0 : 1, speaker_labels: { a: label }, snapshot: {
    session_id: "m", descriptor: { sample_rate: 16000 }, session: { committed_samples: 16000, status: "active", version: 1,
      failure_reason: null, label_revision_version: 0, identity_snapshot: { canonical_speakers: ["a"] },
      committed: [{ span_id: 1, start_sample: 0, transcript: "[0][S01]Words[1]", revised_transcript: null }], provisional: null }
  } });
  const poller = createMossSessionPoller({ sessionId: "m", dispatch: event => dispatched.push(event), fetch: vi.fn(async url => {
    if (String(url).includes('/events')) return Response.json({ events: [] });
    if (++snapshots === 1) return new Promise<Response>(resolve => { release = resolve; });
    return Response.json(payload("After"));
  }) });
  try {
    poller.start();
    document.dispatchEvent(new CustomEvent(SPEAKER_NAMED_EVENT, { detail: { meetingId: "another" } }));
    expect(snapshots).toBe(1);
    document.dispatchEvent(new CustomEvent(SPEAKER_NAMED_EVENT, { detail: { meetingId: "m" } }));
    release(Response.json(payload("Before")));
    await vi.waitFor(() => expect(JSON.stringify(dispatched)).toContain('"display_name":"After"'));
    expect(JSON.stringify(dispatched)).not.toContain('"display_name":"Before"');
  } finally { poller.stop(); }
});
