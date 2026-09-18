// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import { TranscriptPane } from "./TranscriptPane";
import { MeetingHistory } from "./MeetingHistory";
import { createMossSessionPoller } from "../api/mossPoller";
import { SPEAKER_NAMED_EVENT } from "../lib/meetingEvents";
import { providerBody } from "../lib/finalSummary";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { serializeTranscriptExport } from "../lib/transcriptExport";
import { captureMeetingId, replaceTranscript, resetSessionState, sessionId, sessionStatus, transcript } from "../state/session";

const root = document.createElement("div");
document.body.append(root);
afterEach(() => { act(() => render(null, root)); resetSessionState(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it.each([
  [".utt-speaker", true, "active", "live"],
  [".legend-chip", false, "active", "live"],
  [".utt-speaker", true, "completed", "live"],
  [".legend-chip", false, "completed", "live"],
  [".utt-speaker", true, "completed", "file"],
  [".legend-chip", false, "completed", "file"],
] as const)("renames from %s save=%s status=%s mode=%s across history/export/summary", async (selector, saveVoiceprint, status, mode) => {
  let name = "Before";
  const meeting = () => ({ id: "m", title: "Meeting", title_source: "manual" as const, mode, status, created_at_ms: 1,
    transcript_version: name === "Before" ? 1 : 2, audio: null, transcript: { segments: ["a", "b", "a"].map((id, i) => ({
      id: String(i), start: i === 1 ? 0 : i, end: i + 1, source_lane: id === "a" ? "system" as const : "microphone" as const, speaker_entity_id: id, speaker: id === "a" ? name : "Other", text: `Words ${i}`
    })) } });
  vi.stubGlobal("fetch", vi.fn(async (url, init) => {
    if (String(url).endsWith("/speakers/a/name")) {
      const body = JSON.parse(init.body);
      expect(body).toEqual(saveVoiceprint ? { label: "After" } : { label: "After", save_voiceprint: false });
      name = body.label;
      return Response.json({ meeting_id: "m", speaker_id: "a", label: name, enrollment: saveVoiceprint ? (status === "active" ? "pending" : "unavailable") : "not_requested" });
    }
    return Response.json(String(url) === "/api/meetings" ? { meetings: [meeting()] } : meeting());
  }));
  await act(async () => {
    sessionId.value = "m"; captureMeetingId.value = status === "active" ? "m" : null; sessionStatus.value = status === "active" ? "active" : "closed";
    replaceTranscript(meeting().transcript.segments.map(s => ({ ...s, speaker: s.speaker_entity_id === "a" ? "S01" : "S02", display_name: s.speaker, state: "confirmed" })));
    render(<><TranscriptPane /><MeetingHistory /></>, root);
  });
  await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="m"]')).not.toBeNull());
  act(() => root.querySelector<HTMLButtonElement>(selector)!.click());
  expect(root.querySelector("dialog")?.textContent).toContain("Applies to this speaker throughout this meeting.");
  expect(root.querySelector("dialog")?.textContent).not.toContain("active meeting");
  const checkbox = root.querySelector<HTMLInputElement>('dialog input[type="checkbox"]')!;
  expect(checkbox.checked).toBe(true);
  if (!saveVoiceprint) act(() => checkbox.click());
  act(() => {
    const input = root.querySelector<HTMLInputElement>('#speaker-name-input')!;
    input.value = "After"; input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { root.querySelector('dialog form')!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  const assertNames = () => {
    expect([...root.querySelectorAll('.utt-lane')].map(n => n.textContent)).toEqual(["System", "Microphone", "System"]);
    expect([...root.querySelectorAll('.utt-speaker-label')].map(n => n.textContent)).toEqual(["After", "Other", "After"]);
    expect([...root.querySelectorAll('.legend-chip-name')].map(n => n.textContent)).toEqual(["After", "Other"]);
    if (status === "completed") {
      const body = providerBody(meeting(), {endpoint:"", model:"test", apiKey:"", prompt:"Summarize", language:"English", timeoutSeconds:60});
      expect(body).toContain("After"); expect(body).not.toContain("Before");
    }
    for (const format of ["md", "txt", "json", "srt", "vtt"] as const) {
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


it("allows the same voiceprint result for independent speakers on both lanes", async () => {
  const named: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url, init) => {
    const id = String(url).includes("/speakers/system-person/") ? "system-person" : "mic-person";
    named.push(id);
    expect(JSON.parse(init.body)).toEqual({label:"Alex"});
    return Response.json({meeting_id:"m",speaker_id:id,label:"Alex",voiceprint_id:"shared-person",enrollment:"enrolled"});
  }));
  await act(async () => {
    sessionId.value = captureMeetingId.value = "m"; sessionStatus.value = "active";
    replaceTranscript([
      {start:0,end:3,text:"System speech",source_lane:"system",speaker:"S01",speaker_entity_id:"system-person",display_name:"Alex",state:"confirmed"},
      {start:0,end:2,text:"Mic speech",source_lane:"microphone",speaker:"S02",speaker_entity_id:"mic-person",display_name:"Alex",state:"confirmed"}
    ]);
    render(<TranscriptPane />,root);
  });
  for (const index of [0,1]) {
    act(()=>root.querySelectorAll<HTMLButtonElement>('.utt-speaker')[index].click());
    await act(async()=>{ root.querySelector('dialog form')!.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})); });
    await vi.waitFor(()=>expect(root.querySelector('dialog')).toBeNull());
  }
  expect(named).toEqual(["system-person","mic-person"]);
  expect(transcript.value.map(s=>s.speaker_entity_id)).toEqual(["system-person","mic-person"]);
  expect(root.querySelectorAll('.legend-chip')).toHaveLength(2);
});
