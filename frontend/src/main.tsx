import { render } from "preact";
import { App } from "./App";
import { MeetingHistory } from "./components/MeetingHistory";
import "./styles/index.css";

const root = document.getElementById("app");

if (root) {
  render(<App />, root);
}

const historyRoot = document.getElementById("meeting-history-app");
if (historyRoot) {
  render(<MeetingHistory />, historyRoot);
}

if (!root && !historyRoot) {
  throw new Error("Missing MOSS application root");
}
