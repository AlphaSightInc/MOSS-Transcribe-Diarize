// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import { SettingsDialog } from "./SettingsDialog";

const root = document.createElement("div");
document.body.append(root);
afterEach(() => { render(null, root); vi.unstubAllGlobals(); });

it("shows transcription defaults from the real descriptor envelope", async () => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key) });
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ descriptor: {
    engine_options: { speaker_windows: ["balanced", "economy", "max"], default_speaker_window: "balanced",
      cleanup_after_stop: { available: true, default: true } } } }) });
  vi.stubGlobal("fetch", fetcher);
  await act(async () => render(<SettingsDialog />, root));
  await act(async () => root.querySelector<HTMLButtonElement>(".settings-trigger")!.click());
  await vi.waitFor(() => expect(root.querySelector<HTMLSelectElement>('[aria-label="Speaker window"]')).not.toBeNull());
  expect(root.querySelector<HTMLSelectElement>('[aria-label="Speaker window"]')?.value).toBe("balanced");
  expect(root.querySelector<HTMLInputElement>('.settings-checkbox input')?.checked).toBe(true);
  expect(fetcher.mock.calls[0][0]).toContain("/api/live/descriptor");
});
