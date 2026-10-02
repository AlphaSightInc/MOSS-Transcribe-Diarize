// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TranscriptPane } from "./TranscriptPane";
import { recordingInterruptions, replaceTranscript, resetSessionState, sessionId, sessionStatus, transcript } from "../state/session";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { serializeTranscriptExport } from "../lib/transcriptExport";

let root: HTMLDivElement;
let fetcher: ReturnType<typeof vi.fn<(url: string, init?: RequestInit) => Promise<Response>>>;
beforeEach(() => {
  resetSessionState();
  root = document.createElement("div"); document.body.append(root);
  fetcher = vi.fn(async () => Response.json({ meeting_id: "m", segment_ids: ["one"],
    speaker_id: "a", label: "Alex", transcript_version: 2, needs_review: false }));
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => init?.method === "PUT" ? fetcher(url, init) : Promise.resolve(Response.json({summary:null})));
  act(() => {
    sessionId.value = "m"; sessionStatus.value = "closed";
    replaceTranscript(["one", "two"].map((id, i) => ({ segment_id: id, start: i, end: i + 1,
      text: `Words ${id}`, speaker: i ? "b" : "a", speaker_entity_id: i ? "b" : "a",
      display_name: i ? "Blair" : "Alex", state: "final" })));
    render(<TranscriptPane />, root);
  });
});
afterEach(() => { act(() => render(null, root)); root.remove(); resetSessionState(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function open(index = 0) {
  const pencil = root.querySelectorAll<HTMLButtonElement>('[aria-label="Edit text"]')[index];
  act(() => { pencil.focus(); pencil.click(); });
  return pencil;
}
function draft(text: string) {
  const input = root.querySelector<HTMLTextAreaElement>('textarea[aria-label="Section text"]')!;
  act(() => { input.value = text; input.dispatchEvent(new Event("input", { bubbles: true })); });
  return input;
}
function button(label: string) { return [...root.querySelectorAll<HTMLButtonElement>(".text-editor button")].find(b => b.textContent === label)!; }
function outside() { act(() => {document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));}); }
it("pencil opens the in-place editor with caret at end and returns focus on Esc", () => {
  const pencil = open(); const input = root.querySelector<HTMLTextAreaElement>("textarea")!;
  expect(document.activeElement).toBe(input); expect(input.selectionStart).toBe(input.value.length);
  expect(input.value).toBe("Words one"); expect(root.querySelector("dialog")).toBeNull();
  act(() => { input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  expect(root.querySelector("textarea")).toBeNull(); expect(document.activeElement).toBe(pencil); expect(fetcher).not.toHaveBeenCalled();
});
it.each(["Save", "Meta", "Control", "outside"])("%s saves the changed text once and marks it Edited", async path => {
  open(); const input = draft("  Corrected words  ");
  await act(async () => {
    if (path === "Save") button("Save").click();
    else if (path === "outside") outside();
    else input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", metaKey: path === "Meta", ctrlKey: path === "Control", bubbles: true }));
  });
  await vi.waitFor(() => expect(root.querySelector("textarea")).toBeNull());
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher).toHaveBeenCalledWith("/api/meetings/m/passages/one/text", expect.objectContaining({method:"PUT",credentials:"same-origin",body:JSON.stringify({text:"Corrected words"})}));
  expect(transcript.value[0]).toMatchObject({ text: "Corrected words", edited: true, start: 0, end: 1, speaker_entity_id: "a" });
  expect(root.querySelector(".utt-time")?.textContent).toContain("Edited");
});
it("unchanged outside click closes without a request", () => { open(); outside(); expect(root.querySelector("textarea")).toBeNull(); expect(fetcher).not.toHaveBeenCalled(); });
it.each(["Cancel", "Escape"])("%s restores without triggering outside-save", path => {
  open(); const input = draft("Unsaved");
  if (path === "Cancel") act(() => { button("Cancel").dispatchEvent(new MouseEvent("mousedown",{bubbles:true})); button("Cancel").click(); });
  else act(() => { input.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true})); });
  expect(root.querySelector("textarea")).toBeNull(); expect(transcript.value[0].text).toBe("Words one"); expect(fetcher).not.toHaveBeenCalled();
});
it("empty text cannot save or close on outside click", () => {
  open(); draft("   "); expect(button("Save").disabled).toBe(true); expect(root.textContent).toContain("Text cannot be empty.");
  outside(); expect(root.querySelector("textarea")).not.toBeNull(); expect(fetcher).not.toHaveBeenCalled();
});
it("failure keeps editor, text and server reason", async () => {
  fetcher.mockResolvedValue(Response.json({detail:"Transcript not settled"},{status:409}));
  open(); draft("Keep this draft"); await act(async () => button("Save").click());
  await vi.waitFor(() => expect(root.querySelector('[role="alert"]')?.textContent).toBe("Transcript not settled"));
  expect(root.querySelector<HTMLTextAreaElement>("textarea")?.value).toBe("Keep this draft"); expect(button("Save").disabled).toBe(false);
});
it("opening a second editor saves the first before opening the second", async () => {
  open(); draft("First corrected"); await act(async () => {open(1);});
  await vi.waitFor(() => expect(root.querySelector<HTMLTextAreaElement>("textarea")?.value).toBe("Words two"));
  expect(fetcher).toHaveBeenCalledTimes(1); expect(transcript.value[0].text).toBe("First corrected");
});
it("a failed first save prevents a second editor from replacing the draft", async () => {
  fetcher.mockResolvedValue(Response.json({detail:"Keep editing"},{status:409}));
  open(); draft("First draft"); await act(async () => {open(1);});
  await vi.waitFor(() => expect(root.querySelector('[role="alert"]')?.textContent).toBe("Keep editing"));
  expect(root.querySelector<HTMLTextAreaElement>("textarea")?.value).toBe("First draft");
});
it("keyboard focus leaving the editor saves once", async () => {
  open(); draft("Blur correction");
  await act(async () => {root.querySelector<HTMLButtonElement>('[title="Copy"]')!.focus();});
  await vi.waitFor(() => expect(root.querySelector("textarea")).toBeNull());
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it("separates settled passage editors within one speaker card and preserves edited repeated words in exports", () => {
  act(() => replaceTranscript(["one","two"].map((id, i) => ({segment_id:id,start:i,end:i+1,
    text:"One two three four five",speaker:"a",speaker_entity_id:"a",display_name:"Alex",state:"final",edited:i===1}))));
  expect(root.querySelectorAll(".utt")).toHaveLength(1);
  expect(root.querySelectorAll('[aria-label="Edit text"]')).toHaveLength(2);
  expect(groupSegmentsIntoTurns(transcript.value)[0].text).toBe("One two three four five One two three four five");
});
it("pending save disables controls and coalesces repeat save paths", async () => {
  let release!: (value: Response) => void;
  fetcher.mockImplementation(() => new Promise<Response>(resolve => { release = resolve; }));
  open(); const input = draft("Pending"); act(() => button("Save").click());
  expect(root.querySelector<HTMLButtonElement>(".text-editor button")?.disabled).toBe(true); expect(root.textContent).toContain("Saving…");
  outside(); act(() => { input.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",ctrlKey:true,bubbles:true})); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => release(Response.json({meeting_id:"m",segment_ids:["one"],speaker_id:"a",label:"Alex",transcript_version:2,needs_review:false})));
});
it("copy, search and every export format use edited text", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined); vi.stubGlobal("navigator",{clipboard:{writeText}});
  open(); draft("Unique correction"); await act(async () => button("Save").click());
  await vi.waitFor(() => expect(root.querySelector("textarea")).toBeNull());
  await act(async () => root.querySelector<HTMLButtonElement>('[title="Copy"]')!.click()); expect(writeText.mock.calls[0][0]).toContain("Unique correction");
  act(() => root.querySelector<HTMLButtonElement>('[title="Search transcript (⌘F)"]')!.click());
  const search = root.querySelector<HTMLInputElement>("#transcript-find-input")!;
  act(() => {search.value="Unique correction";search.dispatchEvent(new Event("input",{bubbles:true}));});
  expect(root.querySelector("mark")?.textContent).toBe("Unique correction");
  for (const format of ["md","txt"] as const) {
    const exported = serializeTranscriptExport(format,groupSegmentsIntoTurns(transcript.value),t=>t.display_name,{sessionId:"m",exportedAt:new Date(0)});
    expect(exported.content).toContain("Unique correction"); expect(exported.content).not.toContain("Words one");
  }
});

it("keeps a gap beside an edited passage in view, copy, exports and the Speaker popup", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  act(() => {
    replaceTranscript(["one", "two"].map((id, i) => ({ segment_id: id, start: i * 4, end: i * 4 + 1,
      text: `Words ${id}`, speaker: "a", speaker_entity_id: "a", display_name: "Alex", state: "final" })));
    recordingInterruptions.value = [{ start: 1, end: 4 }];
  });
  const line = "([00:00:01-00:00:04] Recording Interrupted)";
  const gap = () => root.querySelector('[data-recording-interruption]')!;
  expect(gap().querySelector("button, textarea, [data-speaker-id]")).toBeNull();
  act(() => { gap().dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  expect(root.querySelector("dialog, textarea")).toBeNull();
  fetcher.mockResolvedValue(Response.json({ meeting_id: "m", segment_ids: ["two"],
    speaker_id: "a", label: "Alex", transcript_version: 2, needs_review: false }));
  open(1); draft("Corrected after reload");
  await act(async () => button("Save").click());
  await vi.waitFor(() => expect(root.querySelector("textarea")).toBeNull());
  expect([...root.querySelector('[data-transcript-cards]')!.children].map(n => n.textContent)).toEqual([
    expect.stringContaining("Words one"), line, expect.stringContaining("Corrected after reload")]);
  await act(async () => root.querySelector<HTMLButtonElement>('[title="Copy"]')!.click());
  const turns = groupSegmentsIntoTurns(transcript.value, { interruptions: recordingInterruptions.value });
  const outputs = [writeText.mock.calls[0][0], ...(["md", "txt"] as const).map(format =>
    serializeTranscriptExport(format, turns, t => t.display_name,
      { sessionId: "m", exportedAt: new Date(0) }, null, recordingInterruptions.value).content)];
  for (const text of outputs) {
    expect(text.split(line)).toHaveLength(2);
    expect(text.indexOf("Words one")).toBeLessThan(text.indexOf(line));
    expect(text.indexOf(line)).toBeLessThan(text.indexOf("Corrected after reload"));
    expect(text).not.toContain("Words two");
  }
  act(() => root.querySelector<HTMLButtonElement>('[data-section-speaker="two"]')!.click());
  expect(root.querySelector("dialog")?.textContent).toContain("This Section Only");
  expect(root.querySelector("dialog")?.textContent).toContain("All Sections Named “Alex”");
  expect(root.querySelector("dialog")?.textContent).not.toContain("Recording Interrupted");
  expect(root.querySelector<HTMLButtonElement>('[data-section-speaker="one"]')).not.toBeNull();
  expect(gap().textContent).toBe(line);
});
