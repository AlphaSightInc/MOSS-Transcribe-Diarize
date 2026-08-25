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
        <label for="sharedToken">Shared bearer token</label>
        <input id="sharedToken" type="password" autocomplete="off" />
        <button id="startButton" class="primary" type="button">Start session</button>
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
      // The token the server publishes for speech nobody has been attributed. Declared here
      // because the surface a reader is shown carries canonical identities, not tokens, and
      // this page has to write one; a test binds it to the server's own constant.
      const unattributedSpeaker = "S00";
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
        start: "/api/live/sessions",
        snapshot: (sessionId, snapshotVersion) => `/api/live/sessions/${encodeURIComponent(sessionId)}/snapshot?since_version=${snapshotVersion}`,
        events: (sessionId, eventSequence) => `/api/live/sessions/${encodeURIComponent(sessionId)}/events?since_seq=${eventSequence}`,
        stop: (sessionId) => `/api/live/sessions/${encodeURIComponent(sessionId)}/stop`,
        abort: (sessionId) => `/api/live/sessions/${encodeURIComponent(sessionId)}/abort`,
      };
      const nodes = {
        sharedToken: document.getElementById("sharedToken"),
        start: document.getElementById("startButton"),
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
        // `/events?since_seq` is inclusive, and sequence 0 is session_created.  -1
        // therefore means no event has rendered yet; it lets the first poll render 0 once.
        eventSequence: -1,
        connected: false,
        generation: 0,
        inFlight: false,
        retryIndex: 0,
        retryTimer: 0,
        startController: null,
        pollController: null,
        controlController: null,
        renderedEvents: new Set(),
        renderedEventOrder: [],
        pendingLatencyEvents: new Map(),
      };
      const latencySamples = {
        queueWaitMS: [],
        processingMS: [],
        decodeMS: [],
        commitToFetchMS: [],
        eventsFetchMS: [],
        fetchToDOMRenderMS: [],
        spanStartToDOMRenderUpperBoundMS: [],
        spanEndToDOMRenderUpperBoundMS: [],
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

      function resetLatency() {
        state.pendingLatencyEvents.clear();
        for (const values of Object.values(latencySamples)) {
          values.length = 0;
        }
      }

      function latencyDistribution(values) {
        const sorted = [...values].sort((left, right) => left - right);
        const percentile = (fraction) => {
          if (!sorted.length) return null;
          const rank = Math.ceil(fraction * sorted.length);
          return sorted[Math.max(1, rank) - 1];
        };
        return {
          count: sorted.length,
          p50MS: percentile(0.50),
          p95MS: percentile(0.95),
          maxMS: sorted.length ? sorted[sorted.length - 1] : null,
        };
      }

      function latencyReport() {
        return {
          schema: "moss-live-portal-latency.v1",
          sampleCount: latencySamples.spanEndToDOMRenderUpperBoundMS.length,
          clockContract: "durations are measured within one clock domain, then added; absolute clocks are never subtracted",
          queueWaitMS: latencyDistribution(latencySamples.queueWaitMS),
          processingMS: latencyDistribution(latencySamples.processingMS),
          decodeMS: latencyDistribution(latencySamples.decodeMS),
          commitToFetchMS: latencyDistribution(latencySamples.commitToFetchMS),
          eventsFetchMS: latencyDistribution(latencySamples.eventsFetchMS),
          fetchToDOMRenderMS: latencyDistribution(latencySamples.fetchToDOMRenderMS),
          spanStartToDOMRenderUpperBoundMS: latencyDistribution(
            latencySamples.spanStartToDOMRenderUpperBoundMS
          ),
          spanEndToDOMRenderUpperBoundMS: latencyDistribution(
            latencySamples.spanEndToDOMRenderUpperBoundMS
          ),
        };
      }

      function authHeaders(token = state.viewToken) {
        return {
          "Authorization": `Bearer ${token}`,
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
        for (const key of ["startController", "pollController", "controlController"]) {
          if (state[key]) {
            state[key].abort();
            state[key] = null;
          }
        }
      }

      function setControls(connected) {
        nodes.start.disabled = connected;
        nodes.connect.disabled = connected;
        nodes.disconnect.disabled = !connected;
        nodes.stop.disabled = !connected;
        nodes.abort.disabled = !connected;
      }

      function clearAuthority() {
        state.sessionId = "";
        state.viewToken = "";
        state.snapshotVersion = 0;
        state.eventSequence = -1;
        state.renderedEvents.clear();
        state.renderedEventOrder = [];
        resetLatency();
        nodes.sharedToken.value = "";
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

      // A refusal of authority, as opposed to a refused request. 401 is "this token is not
      // (or is no longer) a view of this session"; 403 is "this peer may not view it".
      // Neither becomes true again by asking a second time.
      function viewRefused(error) {
        return error && (error.status === 401 || error.status === 403);
      }

      function viewEnded(error) {
        terminalDisconnect();
        setText(
          nodes.statusDetail,
          `View ended (${(error && error.message) || "not authorised"}). The server no longer `
            + `authorises this token. Terminal sessions remain readable, so this means the token `
            + `expired or was revoked. Connect again with a fresh token to watch a live session.`,
        );
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
          const error = failure && (failure.code || failure.kind || failure.reason)
            ? new Error([failure.code, failure.kind, failure.reason].filter(Boolean).join(": "))
            : new Error(`HTTP ${response.status}`);
          // The status code travels with the error. A refused *request* may be worth
          // retrying; a refused *authority* never is, and the poll loop is the only
          // place that can tell those apart.
          error.status = response.status;
          throw error;
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

      function activateAuthority(sessionId, token) {
        state.sessionId = sessionId;
        state.viewToken = token;
        state.connected = Boolean(state.sessionId && state.viewToken);
        state.generation += 1;
        state.retryIndex = 0;
        state.snapshotVersion = 0;
        state.eventSequence = -1;
        state.renderedEvents.clear();
        state.renderedEventOrder = [];
        resetLatency();
        setText(nodes.events, "");
        setText(nodes.transcript, "");
        setControls(state.connected);
        if (state.connected) {
          setLocalState("reconnecting");
          setText(nodes.statusDetail, "Waiting for first server snapshot.");
          schedulePoll(0);
        }
      }

      async function startSession() {
        const token = nodes.sharedToken.value;
        disconnect();
        if (!token) {
          return;
        }
        const generation = state.generation;
        const controller = new AbortController();
        state.startController = controller;
        nodes.start.disabled = true;
        nodes.connect.disabled = true;
        setText(nodes.statusDetail, "Starting session.");
        try {
          const response = await fetch(endpoints.start, {
            method: "POST",
            cache: "no-store",
            credentials: "same-origin",
            signal: controller.signal,
            headers: authHeaders(token),
          });
          const payload = await readJson(response);
          if (generation !== state.generation) {
            throw new DOMException("stale live portal generation", "AbortError");
          }
          if (!payload || typeof payload.id !== "string" || !payload.id) {
            throw new Error("malformed session response");
          }
          activateAuthority(payload.id, token);
        } catch (error) {
          if (error.name !== "AbortError" && generation === state.generation) {
            setText(nodes.statusDetail, `Start failed: ${error.message || "request failed"}`);
          }
        } finally {
          if (state.startController === controller) {
            state.startController = null;
          }
          setControls(state.connected);
        }
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

      // The `Sxx` token a canonical speaker is published as. Positional, and the canonical
      // list only ever grows by appending, which is what makes a label written in minute one
      // still name the same speaker in minute seventeen. This is the server's own
      // `display_speaker_label` rule, applied on the one surface that carries canonical
      // identities instead of tokens: `effective_transcript` reports who is believed to have
      // spoken, and the reader is shown the token the rest of the meeting is written in.
      // Nobody-attributed, and an identity this snapshot has not established, both read as the
      // honest unattributed token rather than as a guess.
      function speakerLabel(canonicalSpeaker, canonicalSpeakers) {
        if (canonicalSpeaker === undefined || canonicalSpeaker === null) {
          return unattributedSpeaker;
        }
        const index = (canonicalSpeakers || []).indexOf(canonicalSpeaker);
        if (index < 0) {
          return unattributedSpeaker;
        }
        return `S${String(index + 1).padStart(2, "0")}`;
      }

      // Sample integers are what the wire carries and what the server treats as
      // authoritative; seconds are a presentation value, computed here from the rate the
      // descriptor declares rather than from a number this page happens to believe. Six
      // significant digits is what the server's own span renderer prints, so a surface
      // rendered here reads in the same grammar as the spans the short base path publishes.
      function displaySeconds(sampleIndex, sampleRate) {
        return String(Number((Number(sampleIndex) / sampleRate).toPrecision(6)));
      }

      function renderTranscript(snapshot, sampleRate) {
        const session = snapshot.session;
        const speakers = (session.identity_snapshot || {}).canonical_speakers || [];
        const rows = [];
        // ONE replacement surface. The server publishes the whole of what a reader should be
        // shown on every snapshot -- the rolling authority's words over the interval it owns,
        // then the short base path's words after that frontier -- so this render REPLACES the
        // transcript instead of appending to it. That is what makes a correction that arrives
        // ten seconds late read as a corrected meeting rather than as the meeting said twice,
        // and it is why the reader never sees the same words under two authorities: the server
        // resolved that before it serialized, and this page does not re-decide it.
        for (const segment of session.effective_transcript || []) {
          // A span with no speech contributes no segment so its audio stays accounted for
          // without opening a blank gap in the meeting.
          if (!segment || !segment.text) {
            continue;
          }
          rows.push(
            `[${displaySeconds(segment.start_sample, sampleRate)}]`
            + `[${speakerLabel(segment.canonical_speaker, speakers)}]`
            + `${segment.text}`
            + `[${displaySeconds(segment.end_sample, sampleRate)}]`,
          );
        }
        // The span still being spoken is not part of the surface: nothing has committed it, so
        // no authority owns it yet. It is shown after the surface, exactly as the base path
        // published it, so the reader sees the live tail without it reading as settled text.
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
        // The surface carries sample indices; turning them into a time a reader can use needs
        // the rate the service declares. Refusing a snapshot that does not declare one is the
        // point: a page that silently assumed a rate would print a plausible wrong time, and a
        // page that skipped the timestamps would drop information the reader has today.
        const sampleRate = (snapshot.descriptor || {}).sample_rate;
        if (!Number.isInteger(sampleRate) || sampleRate <= 0) {
          throw new Error("malformed snapshot descriptor");
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
          // The other dimension of the same living document, and shown on the same terms: a
          // meeting whose words were never revised has nothing to say about word revisions,
          // and a meeting no terminal pass has touched is not a meeting that "failed" to
          // finalize. Say each only once there is something to say.
          session.text_revision_version ? line("text revisions", session.text_revision_version) : "",
          session.text_revision_version ? line("converged through sample", session.canonical_through_sample) : "",
          session.finalization_status && session.finalization_status !== "not_started"
            ? line("finalization", session.finalization_status)
            : "",
          line("failure", session.failure_reason),
          line("failure kind", failure.kind),
          line("failure code", failure.code),
          line("failure detail", failure.detail),
          ...helperLines(payload.helper_presence),
          ...v2Lines(payload.v2_session),
        ].filter(Boolean);
        setText(nodes.statusDetail, details.join("\\n"));
        renderTranscript(snapshot, sampleRate);
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

      function retainLatencyEvents(payload) {
        if (
          !payload
          || !Array.isArray(payload.events)
          || !Number.isFinite(payload.runtime_observed_monotonic_ns)
        ) {
          return;
        }
        for (const event of payload.events) {
          const detail = event && event.payload;
          if (
            !event
            || !Number.isInteger(event.seq)
            || event.seq <= state.eventSequence
            || event.kind !== "canonical_processed"
            || !detail
            || !Number.isInteger(detail.span_id)
            || !Number.isFinite(detail.runtime_monotonic_ns)
          ) {
            continue;
          }
          state.pendingLatencyEvents.set(event.seq, {
            event,
            observedMonotonicNS: payload.runtime_observed_monotonic_ns,
          });
          while (state.pendingLatencyEvents.size > maxRenderedEvents) {
            state.pendingLatencyEvents.delete(state.pendingLatencyEvents.keys().next().value);
          }
        }
      }

      function measureRenderedLatency(
        session,
        eventsFetchMS,
        eventsFetchedAtMS,
        generation,
      ) {
        if (!session || !Array.isArray(session.committed)) {
          return;
        }
        const committedSpanIds = new Set(
          session.committed
            .map((item) => item && item.span_id)
            .filter((spanId) => Number.isInteger(spanId))
        );
        const ready = [];
        for (const [sequence, retained] of state.pendingLatencyEvents) {
          if (committedSpanIds.has(retained.event.payload.span_id)) {
            ready.push(retained);
            state.pendingLatencyEvents.delete(sequence);
          }
        }
        if (!ready.length) {
          return;
        }
        window.requestAnimationFrame((renderedAtMS) => {
          if (!state.connected || generation !== state.generation) {
            return;
          }
          const fetchToDOMRenderMS = Math.max(0, renderedAtMS - eventsFetchedAtMS);
          for (const retained of ready) {
            const detail = retained.event.payload;
            const commitToFetchMS = Math.max(
              0,
              (retained.observedMonotonicNS - detail.runtime_monotonic_ns) / 1_000_000,
            );
            const queueWaitMS = Number(detail.queue_wait_ms);
            const processingMS = Number(detail.canonical_processing_elapsed_ms);
            const queuedToProcessedMS = Number(detail.queued_to_processed_ms);
            const decodeMS = Number(detail.canonical_decode_elapsed_sec) * 1_000;
            const spanDurationMS = Number(detail.frozen_span_duration_sec) * 1_000;
            if (
              ![queueWaitMS, processingMS, queuedToProcessedMS, decodeMS, spanDurationMS]
                .every(Number.isFinite)
            ) {
              continue;
            }
            // `commitToFetchMS` ends at the server's read of the events response. Adding the
            // complete browser fetch duration double-counts at most the request prefix, so the
            // result is an explicit upper bound ending at an actual post-DOM animation frame.
            const spanEndUpperMS = queuedToProcessedMS
              + commitToFetchMS
              + eventsFetchMS
              + fetchToDOMRenderMS;
            latencySamples.queueWaitMS.push(queueWaitMS);
            latencySamples.processingMS.push(processingMS);
            latencySamples.decodeMS.push(decodeMS);
            latencySamples.commitToFetchMS.push(commitToFetchMS);
            latencySamples.eventsFetchMS.push(eventsFetchMS);
            latencySamples.fetchToDOMRenderMS.push(fetchToDOMRenderMS);
            latencySamples.spanEndToDOMRenderUpperBoundMS.push(spanEndUpperMS);
            latencySamples.spanStartToDOMRenderUpperBoundMS.push(
              spanDurationMS + spanEndUpperMS
            );
            for (const values of Object.values(latencySamples)) {
              if (values.length > maxRenderedEvents) values.shift();
            }
          }
        });
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
          // Both responses describe the same cursor generation and neither depends on the
          // other's body. Starting them together makes the viewer pay the slower fetch once.
          const eventsFetchStartedAtMS = performance.now();
          const [snapshotPayload, eventsPayload] = await Promise.all([
            fetchPollJson(
              endpoints.snapshot(state.sessionId, state.snapshotVersion),
              { method: "GET" },
              generation,
              controller,
            ),
            fetchPollJson(
              endpoints.events(state.sessionId, state.eventSequence),
              { method: "GET" },
              generation,
              controller,
            ),
          ]);
          const eventsFetchedAtMS = performance.now();
          const session = renderSnapshot(snapshotPayload);
          assertCurrent(generation);
          if (session) {
            state.snapshotVersion = session.version;
          }
          retainLatencyEvents(eventsPayload);
          const highestEvent = renderEvents(eventsPayload);
          assertCurrent(generation);
          if (highestEvent !== null) {
            state.eventSequence = highestEvent;
          }
          measureRenderedLatency(
            session,
            Math.max(0, eventsFetchedAtMS - eventsFetchStartedAtMS),
            eventsFetchedAtMS,
            generation,
          );
          state.retryIndex = 0;
          if (session && terminalStates.has(session.status)) {
            terminalDisconnect();
          } else {
            schedulePoll(pollDelayMs);
          }
        } catch (error) {
          // A failed member makes this cursor generation unusable. Abort its sibling before
          // retrying so the next pair cannot overlap a stale in-flight request.
          controller.abort();
          if (error.name !== "AbortError" && state.connected && generation === state.generation) {
            if (viewRefused(error)) {
              // View authority is derived from the session lifecycle: the grant is released
              // the moment the session stops being viewable, so a poll that is refused is a
              // poll against a session that has ended. Retrying it is retrying nothing, and
              // retrying forever is how a dead meeting became a browser that sat on
              // "Reconnecting" and never told anyone the meeting was over.
              viewEnded(error);
            } else {
              scheduleRetry(error.message || "request failed");
            }
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

      nodes.start.addEventListener("click", () => void startSession());
      nodes.connect.addEventListener("click", () => {
        const nextSessionId = nodes.sessionId.value.trim();
        const nextViewToken = nodes.viewToken.value;
        disconnect();
        activateAuthority(nextSessionId, nextViewToken);
      });
      nodes.disconnect.addEventListener("click", disconnect);
      nodes.stop.addEventListener("click", () => {
        setText(nodes.statusDetail, "Stop requested.");
        void control("stop");
      });
      nodes.abort.addEventListener("click", () => void control("abort"));
      window.addEventListener("pagehide", disconnect);

      window.mossLivePortal = { endpoints, renderedEventBounds, latencyReport };
    })();
  </script>
</body>
</html>
"""
