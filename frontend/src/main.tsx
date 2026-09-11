import { render } from "preact";
import { App } from "./App";
import { VoiceprintBank } from "./components/VoiceprintBank";
import { MeetingHistory } from "./components/MeetingHistory";
import "./styles/index.css";
import { MEETING_CREATED, watchCreatedMeeting } from "./lib/finalSummary";

document.addEventListener(MEETING_CREATED, event => {
  const id = (event as CustomEvent).detail?.meeting_id;
  if (typeof id === "string") watchCreatedMeeting(id, true);
});

const root = document.getElementById("app");

if (root) {
  render(<App />, root);
}

const historyRoot = document.getElementById("meeting-history-app");
if (historyRoot) {
  render(<MeetingHistory />, historyRoot);
  historyRoot.setAttribute("data-history-boot", "ready");
}

const voiceprintRoot = document.getElementById("voiceprint-bank-app");
if (voiceprintRoot) render(<VoiceprintBank />, voiceprintRoot);

if (!root && !historyRoot && !voiceprintRoot) {
  throw new Error("Missing MOSS application root");
}
