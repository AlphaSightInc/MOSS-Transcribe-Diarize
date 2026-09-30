import { browserStorage, type StorageLike } from "./persistence";

/** What the person chose in Chrome's share dialog (`displaySurface` of the video track). */
export type CaptureSurface = "browser" | "window" | "monitor";

const STORAGE_PREFIX = "moss.captureSurface.";
const SURFACE_LABELS: Readonly<Record<CaptureSurface, string>> = {
  browser: "Browser",
  window: "Window",
  monitor: "Screen"
};

function asSurface(value: unknown): CaptureSurface | null {
  return value === "browser" || value === "window" || value === "monitor" ? value : null;
}

export function displaySurfaceOf(stream: MediaStream): CaptureSurface | null {
  const track = stream.getVideoTracks?.()[0];
  return asSurface((track?.getSettings?.() as { displaySurface?: unknown } | undefined)?.displaySurface);
}

/** History is per browser (ADR-0006), so the share choice is kept beside it, per meeting. */
export function rememberCaptureSurface(meetingId: string, surface: CaptureSurface | null,
                                       storage?: StorageLike): void {
  if (!surface) return;
  try {
    (storage ?? browserStorage()).setItem(STORAGE_PREFIX + meetingId, surface);
  } catch {
    // Storage refused: the shared lane then reads "Shared".
  }
}

export function recallCaptureSurface(meetingId: string, storage?: StorageLike): CaptureSurface | null {
  try {
    return asSurface((storage ?? browserStorage()).getItem(STORAGE_PREFIX + meetingId));
  } catch {
    return null;
  }
}

/** Row source label: live meetings only; File/URL transcripts have no source. */
export function transcriptSourceLabel(lane: string | undefined, surface: CaptureSurface | null,
                                      mode: "live" | "file"): string | null {
  if (mode !== "live") return null;
  if (lane === "microphone") return "Mic";
  if (lane === "system") return surface ? SURFACE_LABELS[surface] : "Shared";
  return null;
}
