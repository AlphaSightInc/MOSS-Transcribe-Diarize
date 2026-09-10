// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { beforeEach, afterEach, it, vi, expect } from "vitest";
import { FinalSummary, FinalSummarySettings } from "./FinalSummary";
import type { Meeting } from "../api/meetings";
import { loadSummarySettings, SUMMARY_CHANGED } from "../lib/finalSummary";

let root: HTMLDivElement;
const meeting: Meeting = { id: "a", mode: "file", title: null, title_source: "automatic", status: "completed", created_at_ms: 0,
  transcript: { segments: [{ start: 0, end: 4, speaker: "Alex", text: "Hello" }] }, transcript_version: 1, audio: null };
beforeEach(() => {
  root = document.createElement("div"); document.body.append(root);
  const data = new Map();
  vi.stubGlobal("localStorage", { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => data.set(key, value), removeItem: (key: string) => data.delete(key) });
});
afterEach(() => { act(() => render(null, root)); root.remove(); vi.unstubAllGlobals(); });

it("saves settings without any server request and clears the key", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  await act(async () => render(<FinalSummarySettings />, root));
  await act(async () => root.querySelector<HTMLButtonElement>("button")!.click());
  const inputs = root.querySelectorAll<HTMLInputElement>("input");
  for (const [index, value] of [[0, "https://provider.test"], [1, "model"], [2, "secret"]] as const) {
    act(() => { inputs[index].value = value; inputs[index].dispatchEvent(new Event("input", { bubbles: true })); });
  }
  await act(async () => { root.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  expect(loadSummarySettings().apiKey).toBe("secret"); expect(fetcher).not.toHaveBeenCalled();
  await act(async () => [...root.querySelectorAll<HTMLButtonElement>("button")].find(b => b.textContent === "Clear settings")!.click());
  expect(loadSummarySettings().apiKey).toBe("");
});

it("history reads only, renders saved content as text and exposes orphan cancellation", async () => {
  const artifact = { state: "generating", attempt_id: "attempt-a", source_version: 1, artifact_version: 1, document: null, error_code: null };
  const fetcher = vi.fn(async () => new Response(JSON.stringify({ summary: artifact })));
  vi.stubGlobal("fetch", fetcher);
  await act(async () => render(<FinalSummary meeting={meeting} />, root));
  await vi.waitFor(() => expect(root.textContent).toContain("Cancel summary"));
  expect(fetcher.mock.calls).toHaveLength(1);
  await act(async () => { document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: { meeting_id: "a", artifact: {
    ...artifact, state: "current", document: { summary: "<script>do not execute</script>", topics: [], details: [], speaker_background: [], data_references: [] }
  } } })); });
  expect(root.querySelector("script")).toBeNull();
  expect(root.textContent).toContain("<script>do not execute</script>");
  expect(root.textContent).toContain("Regenerate summary");
  expect(fetcher.mock.calls).toHaveLength(1);
});
