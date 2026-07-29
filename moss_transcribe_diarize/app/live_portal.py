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
      <span id="connectionState" class="status" role="status" aria-live="polite">disconnected</span>
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
          <span id="serverState" class="status" role="status" aria-live="polite">disconnected</span>
        </div>
        <div id="statusDetail" class="panel empty" role="status" aria-live="polite"></div>
        <div id="transcript" class="panel empty"></div>
        <div id="events" class="panel empty"></div>
      </section>
    </main>
  </div>
  <script>
    (() => {
      const allowedServerStates = new Set(["active", "closing", "closed", "failed", "aborted"]);
      const localStates = new Set(["disconnected", "reconnecting"]);
      const terminalStates = new Set(["closed", "failed", "aborted"]);
      const retryDelaysMs = [500, 1000, 2000, 5000];
      // The reader's own cadence, and the only thing that decides how long committed
      // text waits before a browser asks for it. The app's latency gate reports an
      // analytic render bound built from the SAME cadence
      // (CaptureLatencyContract.portalCycleSeconds), so the two must move together or
      // the reported bound stops describing this page; a test asserts they agree.
      const pollDelayMs = 500;
      const pollRequestTimeoutMs = 10000;
      const controlRequestTimeoutMs = 10000;
      const stopDrainDeadlineSeconds = 5.0;
      const maxRenderedEvents = 200;
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
        generation: 0,
        inFlight: false,
        retryIndex: 0,
        retryTimer: 0,
        pollController: null,
        controlController: null,
        renderedEvents: new Set(),
        renderedEventOrder: [],
      };

      function setText(node, value) {
        node.textContent = value == null ? "" : String(value);
        node.classList.toggle("empty", !node.textContent);
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
        return {
          "Authorization": `Bearer ${state.viewToken}`,
          "Content-Type": "application/json",
        };
      }

      function assertCurrent(generation) {
        if (!state.connected || generation !== state.generation) {
          throw new DOMException("stale live portal generation", "AbortError");
        }
      }

      function cancelPending() {
        if (state.retryTimer) {
          clearTimeout(state.retryTimer);
          state.retryTimer = 0;
        }
        for (const key of ["pollController", "controlController"]) {
          if (state[key]) {
            state[key].abort();
            state[key] = null;
          }
        }
      }

      function setControls(connected) {
        nodes.connect.disabled = connected;
        nodes.disconnect.disabled = !connected;
        nodes.stop.disabled = !connected;
        nodes.abort.disabled = !connected;
      }

      function clearAuthority() {
        state.sessionId = "";
        state.viewToken = "";
        state.snapshotVersion = 0;
        state.eventSequence = 0;
        state.renderedEvents.clear();
        state.renderedEventOrder = [];
        nodes.sessionId.value = "";
        nodes.viewToken.value = "";
      }

      function disconnect() {
        state.generation += 1;
        state.connected = false;
        state.inFlight = false;
        cancelPending();
        clearAuthority();
        setLocalState("disconnected");
        setText(nodes.serverState, "disconnected");
        setControls(false);
      }

      function terminalDisconnect() {
        state.generation += 1;
        state.connected = false;
        state.inFlight = false;
        cancelPending();
        clearAuthority();
        setLocalState("disconnected");
        setControls(false);
      }

      async function readJson(response) {
        let payload;
        try {
          payload = await response.json();
        } catch (error) {
          throw new Error("invalid JSON response");
        }
        if (!response.ok) {
          const failure = payload && payload.failure;
          if (failure && (failure.code || failure.kind || failure.reason)) {
            throw new Error([failure.code, failure.kind, failure.reason].filter(Boolean).join(": "));
          }
          throw new Error(`HTTP ${response.status}`);
        }
        return payload;
      }

      async function fetchJson(url, options, generation, signal) {
        assertCurrent(generation);
        const response = await fetch(url, {
          cache: "no-store",
          credentials: "same-origin",
          signal,
          ...options,
          headers: {
            ...authHeaders(),
            ...(options && options.headers ? options.headers : {}),
          },
        });
        assertCurrent(generation);
        return readJson(response);
      }

      async function fetchTimedJson(url, options, generation, controller, timeoutMs) {
        let timedOut = false;
        const timeout = window.setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs);
        try {
          return await fetchJson(url, options, generation, controller.signal);
        } catch (error) {
          if (timedOut) {
            throw new Error("request timed out");
          }
          throw error;
        } finally {
          clearTimeout(timeout);
        }
      }

      async function fetchPollJson(url, options, generation, controller) {
        return fetchTimedJson(url, options, generation, controller, pollRequestTimeoutMs);
      }

      async function fetchControlJson(url, options, generation, controller) {
        return fetchTimedJson(url, options, generation, controller, controlRequestTimeoutMs);
      }

      function line(label, value) {
        if (value === undefined || value === null || value === "") {
          return "";
        }
        return `${label}: ${value}`;
      }

      function laneLine(prefix, lane, payload) {
        if (!payload || typeof payload !== "object") {
          return "";
        }
        return [
          `${prefix} ${lane}: ${payload.health || payload.state || "unknown"}`,
          line("next", payload.next_sequence),
          line("accepted", payload.accepted_samples),
          line("accounted", payload.accounted_samples),
          line("failed", payload.failed_samples),
          line("retained", payload.retained_samples),
          line("epoch", payload.current_device_epoch ?? payload.device_epoch),
          line("dropped", payload.dropped_frames),
          line("discontinuities", payload.discontinuities),
          line("code", payload.failure_code),
        ].filter(Boolean).join(" | ");
      }

      function helperLines(helper) {
        if (!helper || typeof helper !== "object") {
          return ["helper: missing"];
        }
        const lines = [
          line("helper", helper.state),
          line("helper sequence", helper.sequence),
        ].filter(Boolean);
        const lanes = helper.lanes || {};
        for (const lane of Object.keys(lanes).sort()) {
          lines.push(laneLine("helper", lane, lanes[lane]));
        }
        return lines;
      }

      function v2Lines(v2Session) {
        if (!v2Session || typeof v2Session !== "object") {
          return ["v2 status: missing"];
        }
        const lines = [
          line("v2 status", v2Session.status),
          line("v2 terminal reason", v2Session.terminal_reason),
        ].filter(Boolean);
        const lanes = v2Session.lanes || {};
        for (const lane of Object.keys(lanes).sort()) {
          lines.push(laneLine("v2", lane, lanes[lane]));
        }
        return lines;
      }

      function renderTranscript(snapshot) {
        const session = snapshot.session;
        const rows = [];
        for (const item of session.committed || []) {
          // A span whose speaker was corrected after it was published carries the
          // corrected labelling beside the words it was committed with; the words are
          // identical either way, and the reader is shown who is believed to have said
          // them now rather than who was believed at the time.
          const text = item.revised_transcript || item.transcript;
          // A span with no speech commits an empty transcript so its audio stays
          // accounted for; it must not open a blank gap in the meeting.
          if (text) {
            rows.push(text);
          }
        }
        if (session.provisional && session.provisional.transcript) {
          rows.push(session.provisional.transcript);
        }
        setText(nodes.transcript, rows.join("\\n\\n"));
      }

      function renderSnapshot(payload) {
        if (!payload || typeof payload !== "object") {
          throw new Error("malformed snapshot response");
        }
        const snapshot = payload.snapshot;
        if (!snapshot) {
          return null;
        }
        const session = snapshot.session;
        if (!session || !allowedServerStates.has(session.status)) {
          throw new Error("malformed snapshot session");
        }
        setServerState(session.status);
        const failure = snapshot.terminal_failure || {};
        const details = [
          line("state", session.status),
          line("version", session.version),
          line("accepted samples", session.accepted_samples),
          line("accounted samples", session.accounted_samples),
          line("retained samples", session.retained_samples),
          line("pending work", snapshot.pending_work_items),
          // Shown only once a label has actually been corrected: a meeting whose live
          // labels stood is not a meeting with "0 revisions", it is one with nothing to
          // say about revisions at all.
          session.label_revision_version ? line("label revisions", session.label_revision_version) : "",
          line("failure", session.failure_reason),
          line("failure kind", failure.kind),
          line("failure code", failure.code),
          line("failure detail", failure.detail),
          ...helperLines(payload.helper_presence),
          ...v2Lines(payload.v2_session),
        ].filter(Boolean);
        setText(nodes.statusDetail, details.join("\\n"));
        renderTranscript(snapshot);
        return session;
      }

      function renderedEventBounds() {
        return {
          cap: maxRenderedEvents,
          identity: state.renderedEvents.size,
          order: state.renderedEventOrder.length,
          dom: nodes.events.children.length,
        };
      }

      function retainRenderedEvent(row, sequence) {
        nodes.events.appendChild(row);
        state.renderedEvents.add(sequence);
        state.renderedEventOrder.push(sequence);
        while (state.renderedEventOrder.length > maxRenderedEvents) {
          const removed = state.renderedEventOrder.shift();
          state.renderedEvents.delete(removed);
        }
        while (nodes.events.children.length > maxRenderedEvents) {
          nodes.events.removeChild(nodes.events.children[0]);
        }
      }

      function renderEvents(payload) {
        if (!payload || !Array.isArray(payload.events)) {
          throw new Error("malformed events response");
        }
        let highest = null;
        const rows = [];
        const batchEvents = new Set();
        for (const event of payload.events) {
          if (
            !Number.isInteger(event.seq)
            || event.seq <= state.eventSequence
            || batchEvents.has(event.seq)
            || state.renderedEvents.has(event.seq)
          ) {
            continue;
          }
          batchEvents.add(event.seq);
          const row = document.createElement("div");
          row.textContent = [
            line("seq", event.seq),
            line("kind", event.kind),
            line("snapshot", event.snapshot_version),
          ].filter(Boolean).join(" | ");
          rows.push({ row, sequence: event.seq });
          highest = highest === null ? event.seq : Math.max(highest, event.seq);
        }
        if (rows.length) {
          for (const item of rows) {
            retainRenderedEvent(item.row, item.sequence);
          }
          nodes.events.classList.remove("empty");
        }
        return highest;
      }

      function schedulePoll(delayMs) {
        if (!state.connected || state.retryTimer) {
          return;
        }
        const generation = state.generation;
        state.retryTimer = window.setTimeout(() => {
          state.retryTimer = 0;
          void poll(generation);
        }, delayMs);
      }

      function scheduleRetry(message) {
        setLocalState("reconnecting");
        setText(nodes.statusDetail, `Reconnecting: ${message}`);
        const delay = retryDelaysMs[Math.min(state.retryIndex, retryDelaysMs.length - 1)];
        state.retryIndex += 1;
        schedulePoll(delay);
      }

      async function poll(generation) {
        if (!state.connected || state.inFlight || generation !== state.generation) {
          return;
        }
        state.inFlight = true;
        const controller = new AbortController();
        state.pollController = controller;
        try {
          const snapshotPayload = await fetchPollJson(
            endpoints.snapshot(state.sessionId, state.snapshotVersion),
            { method: "GET" },
            generation,
            controller,
          );
          const session = renderSnapshot(snapshotPayload);
          assertCurrent(generation);
          if (session) {
            state.snapshotVersion = session.version;
          }
          const eventsPayload = await fetchPollJson(
            endpoints.events(state.sessionId, state.eventSequence),
            { method: "GET" },
            generation,
            controller,
          );
          const highestEvent = renderEvents(eventsPayload);
          assertCurrent(generation);
          if (highestEvent !== null) {
            state.eventSequence = highestEvent;
          }
          state.retryIndex = 0;
          if (session && terminalStates.has(session.status)) {
            terminalDisconnect();
          } else {
            schedulePoll(pollDelayMs);
          }
        } catch (error) {
          if (error.name !== "AbortError" && state.connected && generation === state.generation) {
            scheduleRetry(error.message || "request failed");
          }
        } finally {
          if (generation === state.generation) {
            state.inFlight = false;
          }
          if (state.pollController === controller) {
            state.pollController = null;
          }
        }
      }

      async function control(action) {
        if (!state.connected || !["stop", "abort"].includes(action)) {
          return;
        }
        const generation = state.generation;
        const url = endpoints[action](state.sessionId);
        if (state.controlController) {
          state.controlController.abort();
        }
        const controller = new AbortController();
        state.controlController = controller;
        try {
          const payload = await fetchControlJson(
            url,
            {
              method: "POST",
              body: JSON.stringify(
                action === "stop" ? { deadline: stopDrainDeadlineSeconds } : { reason: "operator abort" },
              ),
            },
            generation,
            controller,
          );
          const session = renderSnapshot(payload);
          if (session) {
            state.snapshotVersion = session.version;
          }
          if (session && terminalStates.has(session.status)) {
            terminalDisconnect();
          }
        } catch (error) {
          if (error.name !== "AbortError") {
            setText(nodes.statusDetail, `${action} failed: ${error.message || "request failed"}`);
          }
        } finally {
          if (state.controlController === controller) {
            state.controlController = null;
          }
        }
      }

      nodes.connect.addEventListener("click", () => {
        const nextSessionId = nodes.sessionId.value.trim();
        const nextViewToken = nodes.viewToken.value;
        disconnect();
        state.sessionId = nextSessionId;
        state.viewToken = nextViewToken;
        nodes.sessionId.value = "";
        nodes.viewToken.value = "";
        state.connected = Boolean(state.sessionId && state.viewToken);
        state.generation += 1;
        state.retryIndex = 0;
        state.snapshotVersion = 0;
        state.eventSequence = 0;
        state.renderedEvents.clear();
        state.renderedEventOrder = [];
        setText(nodes.events, "");
        setText(nodes.transcript, "");
        setControls(state.connected);
        if (state.connected) {
          setLocalState("reconnecting");
          setText(nodes.statusDetail, "Waiting for first server snapshot.");
          schedulePoll(0);
        }
      });
      nodes.disconnect.addEventListener("click", disconnect);
      nodes.stop.addEventListener("click", () => {
        setText(nodes.statusDetail, "Stop requested.");
        void control("stop");
      });
      nodes.abort.addEventListener("click", () => void control("abort"));
      window.addEventListener("pagehide", clearAuthority);

      window.mossLivePortal = { endpoints, renderedEventBounds };
    })();
  </script>
</body>
</html>
"""
