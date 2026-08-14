// @vitest-environment jsdom

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App";

const currentSourceRoot = path.dirname(fileURLToPath(import.meta.url));
const referenceSourceRoot = process.env.MOSS_REFERENCE_FRONTEND_SRC
  ?? "/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend/src";

async function countSourceTree(root: string): Promise<{ files: number; lines: number }> {
  let files = 0;
  let lines = 0;

  for (const entry of await readdir(root, { withFileTypes: true })) {
    const entryPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      const nested = await countSourceTree(entryPath);
      files += nested.files;
      lines += nested.lines;
      continue;
    }
    if (entry.isFile()) {
      files += 1;
      lines += (await readFile(entryPath, "utf8")).match(/\n/g)?.length ?? 0;
    }
  }

  return { files, lines };
}

describe("App shell", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("renders the phase-one shell with an inert collapsed rail", () => {
    const root = document.createElement("div");
    document.body.append(root);

    render(<App />, root);

    expect(root.querySelector("#transcript-panel")).not.toBeNull();
    expect(root.querySelector(".main")?.getAttribute("data-right-collapsed")).toBe("true");
    expect(root.querySelector(".history-panel .panel-body")).toBeNull();
    expect(root.querySelectorAll("[data-transcript-segment]")).toHaveLength(0);
    expect(root.querySelector('a[href="/live"]')).toBeNull();
  });

  it("keeps only Live and File modes, and the File tab exposes browser file selection", () => {
    const root = document.createElement("div");
    document.body.append(root);

    render(<App />, root);

    const modeTabs = root.querySelectorAll('[role="tab"]');
    expect([...modeTabs].map((tab) => tab.textContent)).toEqual(["Live", "File"]);
    expect(root.textContent).not.toContain("URL");
    expect(root.textContent).not.toContain("Batch");

    const fileTab = [...modeTabs].find((tab) => tab.textContent === "File");
    if (!fileTab) {
      throw new Error("Missing File mode tab");
    }
    act(() => {
      (fileTab as HTMLButtonElement).click();
    });

    expect(root.querySelector('[data-mode="file"]')).not.toBeNull();
    expect(root.querySelector('input[type="file"]')).not.toBeNull();
  });

  it("records source-tree counts and rendered collapsed-rail evidence", async () => {
    const root = document.createElement("div");
    document.body.append(root);
    render(<App />, root);

    const [reference, current] = await Promise.all([
      countSourceTree(referenceSourceRoot),
      countSourceTree(currentSourceRoot)
    ]);
    const main = root.querySelector(".main");
    const historyRail = root.querySelector(".history-panel.collapsed");
    const railEvidence = {
      dataRightCollapsed: main?.getAttribute("data-right-collapsed"),
      historyRailPresent: historyRail !== null,
      historyRailInteractive: historyRail?.querySelector("button, input, select, textarea, a") !== null,
      historyBodyPresent: historyRail?.querySelector(".panel-body") !== null
    };

    expect(reference.files).toBeGreaterThan(0);
    expect(reference.lines).toBeGreaterThan(0);
    expect(railEvidence).toEqual({
      dataRightCollapsed: "true",
      historyRailPresent: true,
      historyRailInteractive: false,
      historyBodyPresent: false
    });
    console.info("REFERENCE_UI_COUNTS", JSON.stringify({ reference, current }));
    console.info("REFERENCE_UI_RENDERED_RAIL", JSON.stringify(railEvidence));
  });
});
