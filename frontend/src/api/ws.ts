import type { WsEvent } from "./types";
import {
  applySessionStateEvent,
  applyTranscriptUpdate,
  provisionalSegments,
  replaceTranscript,
  sessionStopRequested
} from "../state/session";

/**
 * The reference event seam. MOSS polling translates its transport vocabulary before calling
 * this function, so components and transcript state stay transport-agnostic.
 */
export function dispatchWsEvent(event: WsEvent): void {
  switch (event.type) {
    case "session_state":
      applySessionStateEvent(event);
      return;
    case "transcript_update":
      if (event.provisional_segments !== undefined) provisionalSegments.value = event.provisional_segments;
      if (event.metadata?.operation === "snapshot") {
        replaceTranscript(event.items);
      } else {
        applyTranscriptUpdate(event.items, event.metadata);
      }
      return;
    case "transcript_relabeled":
    case "refinement_complete":
      applyTranscriptUpdate(event.items, event.metadata);
      return;
    case "stop_progress":
      // Stop was requested; the session may still report "active" while the server drains its tail.
      sessionStopRequested.value = event.session_id;
      return;
  }
}
