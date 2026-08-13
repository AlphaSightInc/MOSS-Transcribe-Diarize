import { render } from "preact";
import { App } from "./App";
import "./styles/index.css";

const root = document.getElementById("app");

if (!root) {
  throw new Error("Missing #app root");
}

render(<App />, root);
