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
import { captureMeetingId, replaceTranscript, resetSessionState, sessionId, sessionMode, sessionNeedsReview, sessionStatus, transcript } from "../state/session";

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
  expect(root.querySelector("dialog")?.textContent).not.toContain("Applies to this speaker throughout this meeting.");
  const checkbox = root.querySelector<HTMLInputElement>('dialog input[type="checkbox"]')!;
  expect(checkbox.checked).toBe(true);
  expect(root.querySelector('dialog .speaker-rename-form .hint')).toBeNull();
  if (!saveVoiceprint) act(() => checkbox.click());
  act(() => {
    const input = root.querySelector<HTMLInputElement>('#speaker-name-input')!;
    input.value = "After"; input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { root.querySelector('dialog .speaker-rename-form')!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  const assertNames = () => {
    // J5: live rows name their source; File/URL rows have none.
    expect([...root.querySelectorAll('.utt-source')].map(n => n.textContent))
      .toEqual(sessionMode.value === "live" ? ["Shared", "Mic"] : []);
    expect([...root.querySelectorAll('.utt-speaker-label')].map(n => n.textContent)).toEqual(["After", "Other"]);
    expect([...root.querySelectorAll('.utt-text')].map(n => n.textContent)).toEqual(["Words 0", "Words 2", "Words 1"]);
    expect([...root.querySelectorAll('.legend-chip-name')].map(n => n.textContent)).toEqual(["After", "Other"]);
    if (status === "completed") {
      const body = providerBody(meeting(), {endpoint:"", model:"test", apiKey:"", prompt:"Summarize", language:"English", timeoutSeconds:60});
      expect(body).toContain("After"); expect(body).not.toContain("Before");
    }
    for (const format of ["md", "txt"] as const) {
      const file = serializeTranscriptExport(format, groupSegmentsIntoTurns(transcript.value), t => t.display_name,
        { sessionId: "m", exportedAt: new Date(0) });
      expect(file.content).toContain("After"); expect(file.content).not.toContain("Before");
    }
  };
  await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());
  expect(root.querySelector(".tr-notice")?.textContent ?? null).toBe(saveVoiceprint && status === "completed"
    ? "Voiceprint not saved — not enough clear speech" : null);
  assertNames();
  await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="m"]')!.click());
  await vi.waitFor(assertNames);
});

it.each(["active", "after Stop"])("saves the name in one action after a %s voiceprint refusal", async phase => {
  const requests: Array<{ label: string; save_voiceprint?: boolean }> = [];
  const serverMessage = "Save voiceprint needs at least 2 seconds of clear speech from this speaker. You can name the speaker without saving a voiceprint.";
  vi.stubGlobal("fetch", vi.fn(async (_url, init) => {
    const body = JSON.parse(init.body);
    requests.push(body);
    return body.save_voiceprint !== false
      ? Response.json({ detail: { code: "voiceprint_evidence_not_admitted", message: serverMessage } }, { status: 400 })
      : Response.json({ meeting_id: "m", speaker_id: "person-a", label: "Alex",
          enrollment: "not_requested" });
  }));
  await act(async () => {
    sessionId.value = "m";
    sessionStatus.value = phase === "active" ? "active" : "closed";
    captureMeetingId.value = phase === "active" ? "m" : null;
    replaceTranscript([{ segment_id: "one", start: 0, end: 1, text: "Short speech", speaker: "S01",
      speaker_entity_id: "person-a", display_name: "S01", state: "confirmed" }]);
    render(<TranscriptPane />, root);
  });
  act(() => root.querySelector<HTMLButtonElement>('.utt-speaker')!.click());
  expect(root.querySelector<HTMLInputElement>('dialog input[type="checkbox"]')?.checked).toBe(true);
  act(() => {
    const input = root.querySelector<HTMLInputElement>('#speaker-name-input')!;
    input.value = "Alex";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { root.querySelector('dialog .speaker-rename-form')!.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true })); });
  await vi.waitFor(() => expect(root.querySelector('dialog')).toBeNull());
  expect(requests).toEqual([{ label: "Alex" }, { label: "Alex", save_voiceprint: false }]);
  expect(transcript.value[0]?.display_name).toBe("Alex");
  expect(root.querySelector(".tr-notice")?.textContent).toBe("Voiceprint not saved — not enough clear speech");
  expect(root.textContent).not.toContain(serverMessage);
  act(() => root.querySelector<HTMLButtonElement>('.utt-speaker')!.click());
  expect(root.querySelector<HTMLInputElement>('dialog input[type="checkbox"]')?.checked).toBe(true);
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

it("reassigns only a selected settled passage to a new recording-local person", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url, init) => {
    expect(String(url)).toBe("/api/meetings/m/passages/speaker");
    expect(JSON.parse(init.body)).toEqual({ segment_ids: ["two"], label: "Blair" });
    return Response.json({
      meeting_id: "m", segment_ids: ["two"], speaker_id: "manual-one", label: "Blair",
      transcript_version: 2, needs_review: false
    });
  }));
  await act(async () => {
    sessionId.value = "m";
    sessionStatus.value = "closed";
    sessionNeedsReview.value = true;
    replaceTranscript([
      {segment_id:"one",start:0,end:1,text:"First",speaker:"person-a",speaker_entity_id:"person-a",display_name:"Alex",state:"final"},
      {segment_id:"two",start:1,end:2,text:"Selected",speaker:"person-b",speaker_entity_id:"person-b",display_name:"Casey",state:"final"},
      {segment_id:"three",start:2,end:3,text:"Other",speaker:"person-c",speaker_entity_id:"person-c",display_name:"Devon",state:"final"}
    ]);
    render(<TranscriptPane />, root);
  });
  const action = root.querySelector<HTMLButtonElement>('[data-section-speaker="two"]')!;
  expect(action.getAttribute("aria-label")).toBe("Speaker Casey");
  expect(action.title).toBe("");
  expect(action.closest(".utt")?.querySelector(".utt-text")?.textContent).toBe("Selected");

  action.focus();
  expect(document.activeElement).toBe(action);
  act(() => action.click());
  expect(root.querySelector("#speaker-name-title")?.textContent).toBe("Speaker");
  openNewSpeaker();
  act(() => {
    const input = root.querySelector<HTMLInputElement>('dialog input[aria-label="New Speaker"]')!;
    input.value = "Blair";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => {
    root.querySelector('dialog .speaker-assignment-form')!.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true })
    );
  });
  await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());
  expect(transcript.value.map(row => [row.text, row.display_name, row.speaker_entity_id])).toEqual([
    ["First", "Alex", "person-a"],
    ["Selected", "Blair", "manual-one"],
    ["Other", "Devon", "person-c"]
  ]);
  expect(sessionNeedsReview.value).toBe(false);
});

it("keeps adjacent unknown passages as separate correction targets", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url, init) => {
    expect(String(url)).toBe("/api/meetings/m/passages/speaker");
    expect(JSON.parse(init.body)).toEqual({ segment_ids: ["unknown-two"], label: "Blair" });
    return Response.json({
      meeting_id: "m", segment_ids: ["unknown-two"], speaker_id: "manual-two", label: "Blair",
      transcript_version: 2, needs_review: true
    });
  }));
  await act(async () => {
    sessionId.value = "m";
    sessionStatus.value = "closed";
    sessionNeedsReview.value = true;
    replaceTranscript([
      {segment_id:"unknown-one",start:0,end:1,text:"First unknown",speaker:"S00",speaker_entity_id:"S00",display_name:"Speaker TBD",state:"final"},
      {segment_id:"unknown-two",start:1,end:2,text:"Second unknown",speaker:"S00",speaker_entity_id:"S00",display_name:"Speaker TBD",state:"final"}
    ]);
    render(<TranscriptPane />, root);
  });

  expect(root.querySelectorAll(".utt")).toHaveLength(2);
  expect(root.querySelector('[data-edit-passage="unknown-one"]')).not.toBeNull();
  expect(root.querySelector('[data-edit-passage="unknown-two"]')).not.toBeNull();
  act(() => root.querySelector<HTMLButtonElement>('[data-section-speaker="unknown-two"]')!.click());
  act(() => {
    const input = root.querySelector<HTMLInputElement>('dialog input[aria-label="New Speaker"]')!;
    input.value = "Blair";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => {
    root.querySelector('dialog .speaker-assignment-form')!.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true })
    );
  });

  await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());
  expect(transcript.value.map(row => [row.segment_id, row.display_name, row.speaker_entity_id])).toEqual([
    ["unknown-one", "Speaker TBD", "S00"],
    ["unknown-two", "Blair", "manual-two"]
  ]);
  expect(sessionNeedsReview.value).toBe(true);

  expect(groupSegmentsIntoTurns([
    {segment_id:"known-one",start:0,end:1,text:"First known",speaker:"person-a",speaker_entity_id:"person-a",display_name:"Alex",state:"final"},
    {segment_id:"known-two",start:1,end:2,text:"Second known",speaker:"person-a",speaker_entity_id:"person-a",display_name:"Alex",state:"final"}
  ])).toHaveLength(1);
});

it("closes an A correction opened during delayed B Open and never sends A passages to B", async () => {
  const openedB = deferred<Response>();
  const correctionRequests: string[] = [];
  const meeting = (id: string, speaker: string, text: string) => ({
    id,
    title: id,
    title_source: "manual" as const,
    mode: "live" as const,
    status: "completed" as const,
    created_at_ms: 1,
    transcript_version: 1,
    audio: null,
    transcript: { segments: [{
      id: "seg_0001",
      start: 0,
      end: 1,
      speaker_entity_id: speaker,
      speaker,
      text
    }] }
  });
  const meetingA = meeting("meeting-a", "Alex", "A words");
  const meetingB = meeting("meeting-b", "Blair", "B words");
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/meetings") return Response.json({ meetings: [meetingA, meetingB] });
    if (path === "/api/meetings/meeting-b") return openedB.promise;
    if (path.endsWith("/summary")) return Response.json({ summary: null });
    if (init?.method === "PUT") {
      correctionRequests.push(path);
      return Response.json({
        meeting_id: path.includes("meeting-b") ? "meeting-b" : "meeting-a",
        segment_ids: ["seg_0001"],
        speaker_id: "manual-person",
        label: "Casey",
        transcript_version: 2,
        needs_review: false
      });
    }
    throw new Error(`unexpected request: ${path}`);
  }));
  await act(async () => {
    sessionId.value = "meeting-a";
    sessionStatus.value = "closed";
    replaceTranscript([{
      segment_id: "seg_0001",
      start: 0,
      end: 1,
      text: "A words",
      speaker: "person-a",
      speaker_entity_id: "person-a",
      display_name: "Alex",
      state: "final"
    }]);
    render(<><TranscriptPane /><MeetingHistory /></>, root);
  });
  await vi.waitFor(() =>
    expect(root.querySelector('[data-open-meeting="meeting-b"]')).not.toBeNull()
  );
  act(() => root.querySelector<HTMLButtonElement>('[data-open-meeting="meeting-b"]')!.click());
  act(() => root.querySelector<HTMLButtonElement>('[data-section-speaker="seg_0001"]')!.click());
  openNewSpeaker();
  act(() => {
    const input = root.querySelector<HTMLInputElement>('dialog input[aria-label="New Speaker"]')!;
    input.value = "Casey";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  await act(async () => openedB.resolve(Response.json(meetingB)));
  await vi.waitFor(() => expect(sessionId.value).toBe("meeting-b"));
  const staleForm = root.querySelector<HTMLFormElement>("dialog .speaker-assignment-form");
  if (staleForm) {
    await act(async () => {
      staleForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
  }

  expect(root.querySelector("dialog")).toBeNull();
  expect(correctionRequests).not.toContain("/api/meetings/meeting-b/passages/speaker");
  expect(transcript.value.map(item => item.text)).toEqual(["B words"]);
});

it.each(["correction-first", "open-first", "open-first-error"] as const)(
  "keeps delayed A correction owned by A when B Open resolves %s",
  async order => {
    const openedB = deferred<Response>();
    const correctedA = deferred<Response>();
    const requests: string[] = [];
    const meetingB = {
      id: "meeting-b", title: "B", title_source: "manual" as const,
      mode: "live" as const, status: "completed" as const, created_at_ms: 1,
      transcript_version: 1, audio: null,
      transcript: { segments: [{ id: "seg_0001", start: 0, end: 1,
        speaker_entity_id: "person-b", speaker: "Blair", text: "B words" }] }
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/meetings") return Response.json({ meetings: [meetingB] });
      if (path === "/api/meetings/meeting-b") return openedB.promise;
      if (path === "/api/meetings/meeting-a/passages/speaker") {
        requests.push(path);
        return correctedA.promise;
      }
      if (path.endsWith("/summary")) return Response.json({ summary: null });
      if (init?.method === "PUT") requests.push(path);
      throw new Error(`unexpected request: ${path}`);
    }));
    await act(async () => {
      sessionId.value = "meeting-a";
      sessionStatus.value = "closed";
      replaceTranscript([{ segment_id: "seg_0001", start: 0, end: 1, text: "A words",
        speaker: "person-a", speaker_entity_id: "person-a", display_name: "Alex", state: "final" }]);
      render(<><TranscriptPane /><MeetingHistory /></>, root);
    });
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="meeting-b"]')).not.toBeNull());
    act(() => root.querySelector<HTMLButtonElement>('[data-open-meeting="meeting-b"]')!.click());
    act(() => root.querySelector<HTMLButtonElement>('[data-section-speaker="seg_0001"]')!.click());
    openNewSpeaker();
    act(() => {
      const input = root.querySelector<HTMLInputElement>('dialog input[aria-label="New Speaker"]')!;
      input.value = "Casey";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    act(() => {
      root.querySelector<HTMLFormElement>("dialog .speaker-assignment-form")!.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true })
      );
    });
    const correctionResponse = order === "open-first-error"
      ? Response.json({ detail: "controlled correction failure" }, { status: 500 })
      : Response.json({
      meeting_id: "meeting-a", segment_ids: ["seg_0001"], speaker_id: "manual-a",
      label: "Casey", transcript_version: 2, needs_review: false
    });
    if (order === "correction-first") {
      await act(async () => correctedA.resolve(correctionResponse));
      await vi.waitFor(() =>
        expect(transcript.value.map(item => item.display_name)).toEqual(["Casey"])
      );
      await act(async () => openedB.resolve(Response.json(meetingB)));
    } else {
      await act(async () => openedB.resolve(Response.json(meetingB)));
      await act(async () => correctedA.resolve(correctionResponse));
    }
    const expectedMeeting = order === "correction-first" ? "meeting-a" : "meeting-b";
    await vi.waitFor(() => expect(sessionId.value).toBe(expectedMeeting));

    expect(requests).toEqual(["/api/meetings/meeting-a/passages/speaker"]);
    expect(transcript.value.map(item => [item.text, item.display_name])).toEqual(
      order === "correction-first" ? [["A words", "Casey"]] : [["B words", "Blair"]]
    );
    expect(root.querySelector("[role='alert']")).toBeNull();
  }
);

it.each(["S00", "UNKNOWN"])("never offers persisted unknown id %s as an existing person", async (unknownId) => {
  await act(async () => {
    sessionId.value = "m";
    sessionStatus.value = "closed";
    sessionNeedsReview.value = true;
    replaceTranscript([
      {segment_id:"known",start:0,end:1,text:"Known",speaker:"person-a",speaker_entity_id:"person-a",display_name:"Alex",state:"final"},
      {segment_id:"unknown",start:1,end:2,text:"Unknown",speaker:unknownId,speaker_entity_id:unknownId,display_name:"Speaker TBD",state:"final"}
    ]);
    render(<TranscriptPane />, root);
  });

  act(() => root.querySelector<HTMLButtonElement>('[data-section-speaker="known"]')!.click());
  const control = root.querySelector<HTMLButtonElement>('[role="combobox"]')!;
  if (control.getAttribute('aria-expanded') !== 'true') act(() => control.click());
  const options = [...root.querySelectorAll<HTMLElement>('dialog [role="option"]')];
  expect(options).toHaveLength(1);
  expect(options.map(option => option.dataset.speakerId)).not.toContain(unknownId);
  expect(options.map(option => option.textContent)).not.toContain("Speaker TBD");
  press(control,"Escape"); press(control,"Escape");
  act(() => root.querySelector<HTMLButtonElement>('[data-section-speaker="unknown"]')!.click());
  expect(root.querySelector(".speaker-assignment-form")).not.toBeNull();
  expect(root.querySelector<HTMLFieldSetElement>(".speaker-rename-form fieldset")?.disabled).toBe(true);
});

it("keeps closed-but-finalizing identity provisional and passage correction unavailable", async () => {
  await act(async () => {
    sessionId.value = "m";
    sessionStatus.value = "closed";
    replaceTranscript([
      {segment_id:"one",start:0,end:1,text:"Settling",speaker:"person-a",speaker_entity_id:"person-a",display_name:"Alex",state:"confirmed"}
    ]);
    render(<TranscriptPane />, root);
  });

  expect(root.textContent).not.toContain("Identity settling");
  expect(root.querySelector('[data-edit-passage="one"]')).toBeNull();

  act(() => replaceTranscript([
    {segment_id:"one",start:0,end:1,text:"Settled",speaker:"person-a",speaker_entity_id:"person-a",display_name:"Alex",state:"final"}
  ]));
  expect(root.textContent).not.toContain("Identity settling");
  expect(root.querySelector('[data-edit-passage="one"]')).not.toBeNull();
});


it("allows the same voiceprint result for independent speakers on both lanes", async () => {
  const named: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url, init) => {
    const id = String(url).includes("/speakers/system-person/") ? "system-person" : "mic-person";
    named.push(id);
    expect(JSON.parse(init.body)).toEqual(named.length === 1 || named.length === 3 ? {label:"Alex"} : {label:"Alex",save_voiceprint:false});
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
    await act(async()=>{ root.querySelector('dialog .speaker-rename-form')!.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})); });
    await vi.waitFor(()=>expect(root.querySelector('dialog')).toBeNull());
  }
  expect(named).toEqual(["system-person","mic-person","mic-person","system-person"]);
  expect(transcript.value.map(s=>s.speaker_entity_id)).toEqual(["system-person","mic-person"]);
  expect(root.querySelectorAll('.legend-chip')).toHaveLength(2);
});

it("renames all equal display names while keeping identities independent", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url) => Response.json({
    meeting_id: "m",
    speaker_id: String(url).includes("speaker-a") ? "speaker-a" : "speaker-b",
    label: "E2E Morgan",
    enrollment: "not_requested"
  })));
  await act(async () => {
    sessionId.value = "m";
    sessionStatus.value = "active";
    replaceTranscript([
      {start:0,end:1,text:"First",speaker:"speaker-a",speaker_entity_id:"speaker-a",display_name:"E2E Rowan",state:"confirmed"},
      {start:1,end:2,text:"Second",speaker:"speaker-b",speaker_entity_id:"speaker-b",display_name:"E2E Rowan",state:"confirmed"},
      {start:2,end:3,text:"Third",speaker:"speaker-c",speaker_entity_id:"speaker-c",display_name:"Other",state:"confirmed"}
    ]);
    render(<TranscriptPane />, root);
  });

  act(() => root.querySelector<HTMLButtonElement>('[data-speaker-id="speaker-a"].utt-speaker')!.click());
  act(() => {
    const input = root.querySelector<HTMLInputElement>('#speaker-name-input')!;
    input.value = "E2E Morgan";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => {
    root.querySelector('dialog .speaker-rename-form')!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());

  expect([...root.querySelectorAll('[data-speaker-id="speaker-a"] .utt-speaker-label, [data-speaker-id="speaker-a"].legend-chip .legend-chip-name')]
    .map(node => node.textContent)).toEqual(["E2E Morgan", "E2E Morgan"]);
  expect([...root.querySelectorAll('[data-speaker-id="speaker-b"] .utt-speaker-label, [data-speaker-id="speaker-b"].legend-chip .legend-chip-name')]
    .map(node => node.textContent)).toEqual(["E2E Morgan", "E2E Morgan"]);
  expect(transcript.value.find(item => item.speaker_entity_id === "speaker-c")?.display_name).toBe("Other");
});

it("disables This Section Only during recording while Rename All stays enabled", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch",fetcher);
  await act(async () => {
    sessionId.value="m";sessionStatus.value="active";
    replaceTranscript([{segment_id:"one",start:0,end:1,text:"Recording",speaker:"a",speaker_entity_id:"a",display_name:"Alex",state:"confirmed"}]);
    render(<TranscriptPane />,root);
  });
  act(() => root.querySelector<HTMLButtonElement>(".utt-speaker")!.click());
  expect(root.querySelector<HTMLFieldSetElement>(".speaker-assignment-form fieldset")?.disabled).toBe(true);
  expect(root.querySelector<HTMLFieldSetElement>(".speaker-rename-form fieldset")?.disabled).toBe(false);
  expect(root.querySelector("dialog")?.textContent).toContain("Available after the recording stops.");
  await act(async () => {root.querySelector(".speaker-assignment-form")!.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}));});
  expect(fetcher.mock.calls.filter(call => call[1]?.method === "PUT")).toHaveLength(0);
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(accept => {
    resolve = accept;
  });
  return { promise, resolve };
}

function openNewSpeaker() {
  const control = root.querySelector<HTMLButtonElement>('dialog [role="combobox"]')!;
  if (control.getAttribute("aria-expanded") !== "true") act(() => control.click());
  act(() => root.querySelector<HTMLInputElement>('dialog input[aria-label="New Speaker"]')!.focus());
}

async function openCorrection(others = true) {
  await act(async () => {
    sessionId.value = "m"; sessionStatus.value = "closed";
    replaceTranscript([
      {segment_id:"one",start:0,end:1,text:"Selected",speaker:"person-a",speaker_entity_id:"person-a",display_name:"Alex",state:"final"},
      ...(others ? [
        {segment_id:"two",start:1,end:2,text:"Second",speaker:"person-b",speaker_entity_id:"person-b",display_name:"Blair",state:"final" as const},
        {segment_id:"three",start:2,end:3,text:"Third",speaker:"person-c",speaker_entity_id:"person-c",display_name:"Casey",state:"final" as const}
      ] : [])
    ]);
    render(<TranscriptPane />, root);
  });
  const pencil = root.querySelector<HTMLButtonElement>('[data-section-speaker="one"]')!;
  pencil.focus(); act(() => pencil.click()); return pencil;
}

function press(element: Element, key: string) {
  act(() => { element.dispatchEvent(new KeyboardEvent("keydown", {key, bubbles:true, cancelable:true})); });
}

it("uses one dropdown without radios, excludes the current speaker and saves an existing id", async () => {
  const fetch = vi.fn(async (_url, init) => {
    if (!init) return Response.json({summary:null});
    expect(JSON.parse(init.body)).toEqual({segment_ids:["one"], speaker_id:"person-c"});
    return Response.json({meeting_id:"m",segment_ids:["one"],speaker_id:"person-c",label:"Casey",transcript_version:2,needs_review:false});
  });
  vi.stubGlobal("fetch", fetch); await openCorrection();
  expect(root.querySelectorAll('dialog input[type="radio"]')).toHaveLength(0);
  expect(root.querySelectorAll('dialog [role="combobox"]')).toHaveLength(1);
  expect(root.querySelector<HTMLButtonElement>('dialog .speaker-assignment-form button[type="submit"]')!.disabled).toBe(true);
  act(() => root.querySelector<HTMLButtonElement>('[role="combobox"]')!.click());
  const options = [...root.querySelectorAll<HTMLElement>('[role="option"]')];
  expect(options.map(option => option.textContent?.trim() || option.querySelector('input')?.getAttribute('placeholder'))).toEqual(["Blair", "Casey", "New Speaker"]);
  expect(options.slice(0,2).every(option => option.querySelector('.legend-chip-dot'))).toBe(true);
  act(() => options[1].click());
  expect(root.querySelector('[role="listbox"]')).toBeNull();
  expect(root.querySelector('[role="combobox"]')!.textContent).toContain("Casey");
  expect(root.querySelector<HTMLButtonElement>('dialog .speaker-assignment-form button[type="submit"]')!.disabled).toBe(false);
  await act(async () => { root.querySelector('dialog .speaker-assignment-form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})); });
  await vi.waitFor(() => expect(root.querySelector('dialog')).toBeNull());
  expect(fetch.mock.calls.filter(call => call[1]?.method === "PUT")).toHaveLength(1);
});

it("types a new name in the list, rejects whitespace and confirms with Enter without saving", async () => {
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch); await openCorrection(); openNewSpeaker();
  const input = root.querySelector<HTMLInputElement>('dialog input[aria-label="New Speaker"]')!;
  for (const [name, disabled] of [["   ",true],["Dana",false]] as const) {
    act(() => {input.value=name; input.dispatchEvent(new Event('input',{bubbles:true}));});
    expect(root.querySelector('[role="listbox"]')).not.toBeNull();
    expect(root.querySelector<HTMLButtonElement>('dialog .speaker-assignment-form button[type="submit"]')!.disabled).toBe(disabled);
  }
  press(input,"Enter");
  expect(root.querySelector('[role="listbox"]')).toBeNull();
  expect(root.querySelector('[role="combobox"]')!.textContent).toContain("Dana");
  expect(fetch.mock.calls.filter(call => call[1]?.method === "PUT")).toHaveLength(0); expect(document.activeElement).toBe(root.querySelector('[role="combobox"]'));
});

it("moves through every line by keyboard, closes list before dialog and returns focus to pencil", async () => {
  const pencil = await openCorrection(); const control = root.querySelector('[role="combobox"]')!;
  expect(document.activeElement).toBe(control); press(control,"ArrowDown");
  expect(document.activeElement?.textContent).toBe("Blair"); press(document.activeElement!,"ArrowDown");
  expect(document.activeElement?.textContent).toBe("Casey"); press(document.activeElement!,"Enter");
  expect(root.querySelector('[role="listbox"]')).toBeNull(); press(control,"ArrowUp");
  expect(document.activeElement?.getAttribute("aria-label")).toBe("New Speaker"); press(document.activeElement!,"ArrowUp");
  expect(document.activeElement?.textContent).toBe("Casey"); press(document.activeElement!,"Escape");
  expect(root.querySelector('[role="listbox"]')).toBeNull(); expect(root.querySelector('dialog')).not.toBeNull();
  press(control,"Escape"); expect(root.querySelector('dialog')).toBeNull(); expect(document.activeElement).toBe(pencil);
});

it("opens on the inline new speaker field when no other identified person exists", async () => {
  await openCorrection(false);
  expect(root.querySelector('[role="combobox"]')?.getAttribute('aria-expanded')).toBe('true');
  expect(document.activeElement?.getAttribute('aria-label')).toBe('New Speaker');
  expect(root.querySelectorAll('[role="option"]')).toHaveLength(1);
  expect(root.querySelector<HTMLButtonElement>('dialog .speaker-assignment-form button[type="submit"]')!.disabled).toBe(true);
});
