from __future__ import annotations


def attach_live_portal(app) -> None:
    from fastapi.responses import HTMLResponse

    @app.get("/live", response_class=HTMLResponse)
    def live_portal():
        return HTMLResponse(LIVE_PORTAL_HTML, headers={"Cache-Control": "no-store"})


LIVE_PORTAL_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MOSS Live Portal</title>
  <style>
    :root {
      --bg: #f7f5f0;
      --panel: #fffdfa;
      --line: #d8d3c7;
      --text: #1d1f22;
      --muted: #6d6a63;
      --teal: #007d77;
      --coral: #c94b35;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { margin: 0; font-size: 18px; font-weight: 720; }
    main {
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
      min-height: calc(100vh - 56px);
    }
    aside {
      border-right: 1px solid var(--line);
      background: #ffffff;
      padding: 18px;
    }
    section { padding: 18px; }
    label {
      display: block;
      margin: 14px 0 6px;
      color: var(--muted);
      font-size: 12px;
    }
    input, button {
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
      padding: 8px 10px;
    }
    button { cursor: pointer; }
    button.primary { margin-top: 16px; background: var(--teal); border-color: var(--teal); color: #ffffff; }
    button.warn { background: var(--coral); border-color: var(--coral); color: #ffffff; }
    button + button { margin-top: 8px; }
    button:disabled { cursor: not-allowed; opacity: 0.45; }
    .toolbar {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      max-width: 420px;
    }
    .status {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #ffffff;
      color: var(--muted);
      font-size: 13px;
    }
    .panel {
      margin-top: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      min-height: 180px;
      padding: 14px;
    }
    .empty { color: var(--muted); }
    @media (max-width: 720px) {
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .toolbar { grid-template-columns: 1fr; max-width: none; }
    }
  </style>
</head>
<body>
  <div id="livePortal">
    <header>
      <h1>MOSS Live Portal</h1>
      <span id="connectionState" class="status">disconnected</span>
    </header>
    <main>
      <aside>
        <label for="sessionId">Session ID</label>
        <input id="sessionId" type="text" autocomplete="off" />
        <label for="viewToken">View token</label>
        <input id="viewToken" type="password" autocomplete="off" />
        <button id="connectButton" class="primary" type="button">Connect</button>
        <button id="disconnectButton" type="button" disabled>Disconnect</button>
      </aside>
      <section>
        <div class="toolbar">
          <button id="stopButton" type="button" disabled>Stop</button>
          <button id="abortButton" class="warn" type="button" disabled>Abort</button>
          <span id="serverState" class="status">disconnected</span>
        </div>
        <div id="statusDetail" class="panel empty"></div>
        <div id="transcript" class="panel empty"></div>
        <div id="events" class="panel empty"></div>
      </section>
    </main>
  </div>
  <script>
    (() => {
      const allowedServerStates = new Set(["active", "closing", "closed", "failed", "aborted"]);
      const localStates = new Set(["disconnected", "reconnecting"]);
      const endpoints = {
        snapshot: (sessionId, snapshotVersion) => `/api/live/sessions/${encodeURIComponent(sessionId)}/snapshot?since_version=${snapshotVersion}`,
        events: (sessionId, eventSequence) => `/api/live/sessions/${encodeURIComponent(sessionId)}/events?since_seq=${eventSequence}`,
        stop: (sessionId) => `/api/live/sessions/${encodeURIComponent(sessionId)}/stop`,
        abort: (sessionId) => `/api/live/sessions/${encodeURIComponent(sessionId)}/abort`,
      };
      const nodes = {
        sessionId: document.getElementById("sessionId"),
        viewToken: document.getElementById("viewToken"),
        connect: document.getElementById("connectButton"),
        disconnect: document.getElementById("disconnectButton"),
        stop: document.getElementById("stopButton"),
        abort: document.getElementById("abortButton"),
        connectionState: document.getElementById("connectionState"),
        serverState: document.getElementById("serverState"),
        statusDetail: document.getElementById("statusDetail"),
        transcript: document.getElementById("transcript"),
        events: document.getElementById("events"),
      };
      const state = {
        sessionId: "",
        viewToken: "",
        snapshotVersion: 0,
        eventSequence: 0,
        connected: false,
      };

      function setText(node, value) {
        node.textContent = value;
      }

      function setLocalState(value) {
        if (!localStates.has(value)) {
          return;
        }
        setText(nodes.connectionState, value);
      }

      function setServerState(value) {
        if (!allowedServerStates.has(value)) {
          return;
        }
        setText(nodes.serverState, value);
      }

      function authHeaders() {
        return { "Authorization": `Bearer ${state.viewToken}` };
      }

      function clearAuthority() {
        state.sessionId = "";
        state.viewToken = "";
        state.snapshotVersion = 0;
        state.eventSequence = 0;
        nodes.sessionId.value = "";
        nodes.viewToken.value = "";
      }

      function disconnect() {
        state.connected = false;
        clearAuthority();
        setLocalState("disconnected");
        setText(nodes.serverState, "disconnected");
        nodes.connect.disabled = false;
        nodes.disconnect.disabled = true;
        nodes.stop.disabled = true;
        nodes.abort.disabled = true;
      }

      nodes.connect.addEventListener("click", () => {
        state.sessionId = nodes.sessionId.value.trim();
        state.viewToken = nodes.viewToken.value;
        nodes.sessionId.value = "";
        nodes.viewToken.value = "";
        state.connected = Boolean(state.sessionId && state.viewToken);
        nodes.connect.disabled = state.connected;
        nodes.disconnect.disabled = !state.connected;
        nodes.stop.disabled = !state.connected;
        nodes.abort.disabled = !state.connected;
        if (state.connected) {
          setLocalState("reconnecting");
          setText(nodes.statusDetail, "Waiting for first server snapshot.");
        }
      });
      nodes.disconnect.addEventListener("click", disconnect);
      window.addEventListener("pagehide", clearAuthority);

      window.mossLivePortal = { endpoints, authHeaders, setText, setServerState, disconnect };
    })();
  </script>
</body>
</html>
"""
