import { bindFileUpload } from "./lib/fileUpload";
import { render } from "preact";
import { App } from "./App";
import { VoiceprintBank } from "./components/VoiceprintBank";
import { MeetingHistory } from "./components/MeetingHistory";
import "./styles/index.css";
import { MEETING_CREATED } from "./lib/finalSummary";
import { watchMeetingSummary } from "./lib/summaryRequests";

document.addEventListener(MEETING_CREATED, event => {
  const id = (event as CustomEvent).detail?.meeting_id;
  if (typeof id === "string") watchMeetingSummary(id);
});

const root = document.getElementById("app");

if (root) {
  render(<App />, root);
} else {
  bindFileUpload();
}

const historyRoot = document.getElementById("meeting-history-app");
if (historyRoot) {
  historyRoot.replaceChildren();
  render(<MeetingHistory />, historyRoot);
  historyRoot.setAttribute("data-history-boot", "ready");
}

const voiceprintRoot = document.getElementById("voiceprint-bank-app");
const voiceprintSection = voiceprintRoot?.closest('[data-workspace-section="voiceprints"]');
const historyBody = historyRoot?.querySelector(".history-panel .panel-body");
if (voiceprintRoot) {
  if (voiceprintSection && historyBody) historyBody.append(voiceprintSection);
  render(<VoiceprintBank />, voiceprintRoot);
}

if (!root && !historyRoot && !voiceprintRoot) {
  throw new Error("Missing MOSS application root");
}
