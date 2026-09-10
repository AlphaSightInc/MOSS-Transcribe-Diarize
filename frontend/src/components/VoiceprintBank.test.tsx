// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { VoiceprintBank } from "./VoiceprintBank";

let root: HTMLDivElement;
beforeEach(() => { root = document.createElement("div"); document.body.append(root); });
afterEach(() => { act(() => render(null, root)); root.remove(); vi.unstubAllGlobals(); });

it("loads only when opened and targets duplicate names by opaque ID", async () => {
  let rows = [{ id: "a", label: "Alex", sample_count: 1 }, { id: "b", label: "Alex", sample_count: 2 }];
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (init?.method === "DELETE") {
      rows = rows.filter(row => row.id !== "b");
      return new Response(JSON.stringify({ id: "b", deleted: true }));
    }
    return new Response(JSON.stringify({ voiceprints: rows }));
  }));
  await act(async () => render(<VoiceprintBank />, root));
  expect(calls).toHaveLength(0);
  await act(async () => root.querySelector<HTMLButtonElement>("button")!.click());
  await vi.waitFor(() => expect(root.querySelectorAll("li")).toHaveLength(2));
  act(() => root.querySelectorAll<HTMLButtonElement>('[data-voiceprint-id="b"] button')[1].click());
  expect(root.textContent).toContain("Recorded names stay");
  await act(async () => { root.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  await vi.waitFor(() => expect(root.querySelectorAll("li")).toHaveLength(1));
  expect(root.querySelector("li")?.getAttribute("data-voiceprint-id")).toBe("a");
  expect(calls.filter(call => call.init?.method === "DELETE").map(call => call.url)).toEqual(["/api/voiceprints/b"]);
});

it("explains incompatible entries and retains a failed rename for retry", async () => {
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => new Response(JSON.stringify(
    init?.method === "PUT" ? { detail: "Workspace credential is unavailable." }
      : { voiceprints: [{ id: "a", label: "Alex", sample_count: 1, compatibility: "re_enrollment_required" }] }
  ), { status: init?.method === "PUT" ? 401 : 200 })));
  await act(async () => render(<VoiceprintBank />, root));
  await act(async () => root.querySelector<HTMLButtonElement>("button")!.click());
  await vi.waitFor(() => expect(root.textContent).toContain("Re-enrollment required"));
  act(() => root.querySelector<HTMLButtonElement>("li button")!.click());
  await act(async () => { root.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  await vi.waitFor(() => expect(root.querySelector("[role='alert']")?.textContent).toBe("Workspace credential is unavailable."));
  expect(root.querySelector<HTMLInputElement>("form input")?.value).toBe("Alex");
});
