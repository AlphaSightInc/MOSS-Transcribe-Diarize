// PROTOTYPE: run the REAL capture_pipeline_page.html transport script outside a browser.
//
// Why this exists: the committed browser probes (probe_slow_post_characterization.py,
// probe_recreate_session.py, probe_g7_hidden_tab.py) need a working Chrome. When Chrome
// cannot launch, there is no way to answer the only question that matters about the P0
// frame-drop gate -- "can that assertion actually fail?" -- because a passing run proves
// nothing about a defect that is no longer in the tree.
//
// This harness reads the SAME committed HTML file the browser probes serve, extracts its
// transport <script>, optionally applies ONE named source mutation, and runs it in a Node
// vm context with stubbed browser APIs and a stubbed strict-v2 route. It is therefore a
// falsification bed: re-introduce a historical defect into the real source text and show
// the gate's assertion turning false, then remove it and show it turning true again.
//
// It is NOT a substitute for the browser probes: there is no AudioWorklet, no Chrome
// scheduler, no real HTTP stack, and no hidden-tab throttling here. Cadence is driven by
// a Node timer, so it measures transport SEMANTICS only, never browser behaviour.
//
// Usage: node page_sender_harness.mjs '<json-config>'   (prints one JSON object on stdout)

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, "capture_pipeline_page.html");

// --------------------------------------------------------------------------- source access
function transportScript() {
  const html = fs.readFileSync(PAGE, "utf8");
  const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  // The transport script is the largest block; the other one is the three-line browser warning.
  const source = blocks.sort((a, b) => b.length - a.length)[0];
  if (!source || !source.includes("async function sendQueuedFrames")) {
    throw new Error("capture_pipeline_page.html does not contain the expected transport script");
  }
  return source;
}

// Each mutation reinstates a defect that the x1 branch claims to have fixed. `applied` is
// verified, so a mutation that silently stops matching the source fails loudly instead of
// producing a bogus "the assertion still passed" result.
const MUTATIONS = {
  none: null,
  // The historical P0 (capture_pipeline_page.html:962 on afk2/f1-canary-fixes): discard the
  // worklet's PCM whenever a POST is outstanding, with no counter and no discontinuity.
  inflight_drop: {
    find: "    const emittedSequence = st.emitted++;\n",
    replace: "    const emittedSequence = st.emitted++;\n    if (st.sendInFlight) return;\n",
  },
  // The historical recreate defect: reset lane sequence state without draining in-flight POSTs.
  no_drain: {
    find: "async function drainFrameSends() {\n  while (Object.values(lanes).some((state) => state.sendInFlight)) {",
    replace: "async function drainFrameSends() {\n  while (false) {",
  },
  // The historical heartbeat lie: report zero drops regardless of what the sender did.
  heartbeat_zero: {
    find: "    dropped_frames: st ? st.droppedFrames : 0,",
    replace: "    dropped_frames: 0,",
  },
};

function mutate(source, name) {
  const mutation = MUTATIONS[name];
  if (mutation === undefined) throw new Error(`unknown mutation: ${name}`);
  if (mutation === null) return { source, applied: false };
  if (!source.includes(mutation.find)) {
    throw new Error(`mutation ${name} no longer matches the committed page source`);
  }
  return { source: source.replace(mutation.find, mutation.replace), applied: true };
}

// ------------------------------------------------------------------------------ fake routes
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function makeServer(config) {
  const state = {
    descriptor: config.descriptor,
    sessions: new Map(),
    createdSessions: 0,
    createAttempts: 0,
    telemetry: [],
    delayedFirstAccepted: false,
    heldResponseLane: null,
    heldResponseReleasedWallMs: null,
    heartbeats: [],
    phases: [],
    acceptances: [],
    frameStatuses: {},
    maxConcurrentFrameRequests: 0,
    concurrentFrameRequests: 0,
    perLaneMaxConcurrent: {},
  };

  function openSession() {
    const id = config.sessionIds[Math.min(state.createdSessions, config.sessionIds.length - 1)];
    state.createdSessions += 1;
    state.sessions.set(id, { id, next: { system: 0, microphone: 0 } });
    return id;
  }

  function reply(status, payload) {
    const body = JSON.stringify(payload ?? {});
    return {
      ok: status >= 200 && status < 300,
      status,
      async json() { return JSON.parse(body); },
      async text() { return body; },
    };
  }

  return {
    state,
    async fetch(url, init = {}) {
      const method = (init.method || "GET").toUpperCase();
      const [route] = String(url).split("?");
      const body = init.body ? JSON.parse(init.body) : null;

      if (route === "/api/live/descriptor") return reply(200, { descriptor: state.descriptor });
      if (route === "/prototype/bootstrap") return reply(200, { capture_bearer: "probe-capture-bearer" });

      if (route === "/api/live/sessions" && method === "POST") {
        state.createAttempts += 1;
        if (config.failCreateAttempts.includes(state.createAttempts)) return reply(503, { detail: "forced" });
        const id = openSession();
        return reply(200, { id, descriptor: state.descriptor, view_token: "view-token" });
      }

      const frames = route.match(/^\/api\/live\/sessions\/([^/]+)\/frames$/);
      if (frames && method === "POST") {
        const session = state.sessions.get(decodeURIComponent(frames[1]));
        const lane = body?.lane;
        state.concurrentFrameRequests += 1;
        state.maxConcurrentFrameRequests = Math.max(
          state.maxConcurrentFrameRequests, state.concurrentFrameRequests,
        );
        state.perLaneMaxConcurrent[lane] = Math.max(
          state.perLaneMaxConcurrent[lane] ?? 0, 1,
        );
        const laneInFlight = (state.perLaneMaxConcurrent[`${lane}:live`] ?? 0) + 1;
        state.perLaneMaxConcurrent[`${lane}:live`] = laneInFlight;
        state.perLaneMaxConcurrent[lane] = Math.max(state.perLaneMaxConcurrent[lane], laneInFlight);
        try {
          // Two delay shapes. Uniform: every frame POST is slow (slow-POST transport study).
          // First-accepted-lane: only the named lane's first ADMITTED response is held, which
          // is how probe_recreate_session.py forces a peer POST to still be resolving when a
          // 409 arrives on the other lane.
          if (config.delayFirstAcceptedLane === null && config.frameDelayMs > 0) {
            await sleep(config.frameDelayMs);
          }
          if (!session) return reply(404, { detail: "unknown session" });
          if (!["system", "microphone"].includes(lane)) return reply(400, { detail: "bad lane" });
          if (body.sample_count !== state.descriptor.frame_samples) return reply(400, { detail: "geometry" });
          let status;
          if (body.sequence !== session.next[lane]) {
            status = 409;
          } else {
            session.next[lane] += 1;
            status = 200;
            state.acceptances.push({
              session_id: session.id,
              lane,
              sequence: body.sequence,
              sample_count: body.sample_count,
              sample_rate: body.sample_rate,
              device_epoch: body.device_epoch,
              discontinuity: body.discontinuity,
              route_accepted_wall_ms: Date.now(),
            });
          }
          state.frameStatuses[status] = (state.frameStatuses[status] || 0) + 1;
          if (
            status === 200
            && config.delayFirstAcceptedLane === lane
            && !state.delayedFirstAccepted
          ) {
            state.delayedFirstAccepted = true;
            state.heldResponseLane = lane;
            await sleep(config.frameDelayMs);
            state.heldResponseReleasedWallMs = Date.now();
          }
          return reply(status, status === 200 ? { accepted: true } : { detail: "sequence conflict" });
        } finally {
          state.concurrentFrameRequests -= 1;
          state.perLaneMaxConcurrent[`${lane}:live`] -= 1;
        }
      }

      const heartbeat = route.match(/^\/api\/live\/sessions\/([^/]+)\/heartbeat$/);
      if (heartbeat && method === "POST") {
        state.heartbeats.push({ ...body, received_wall_ms: Date.now() });
        return reply(200, { accepted: true });
      }

      if (route.endsWith("/snapshot")) {
        return reply(200, { snapshot: { session: { version: 1, committed: [] }, pending_work_items: 0 } });
      }
      if (route.endsWith("/events")) return reply(200, { events: [] });

      if (route === "/prototype/telemetry") { state.telemetry.push(body); return reply(200, {}); }
      if (route === "/prototype/phase") { state.phases.push(body); return reply(200, {}); }
      if (route.startsWith("/prototype/")) return reply(200, {});
      return reply(404, { detail: `unstubbed route ${route}` });
    },
  };
}

// -------------------------------------------------------------------------------- DOM stubs
function makeContextGlobals(server, search) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) {
      elements.set(id, {
        id, textContent: "", value: "", className: "", disabled: false, onclick: null,
        style: {}, addEventListener() {},
        click() { if (typeof this.onclick === "function") this.onclick(); },
      });
    }
    return elements.get(id);
  };

  class AudioWorkletNodeStub {
    constructor() { this.port = { onmessage: null, postMessage() {} }; }
    connect(target) { return target; }
    disconnect() {}
  }
  class AudioContextStub {
    constructor(options) {
      this.sampleRate = options.sampleRate;
      this.state = "running";
      this.baseLatency = 0.01;
      this.destination = { connect(t) { return t; } };
      this.audioWorklet = { async addModule() {} };
    }
    createMediaStreamSource() { return { connect(t) { return t; }, disconnect() {} }; }
    createGain() { return { gain: { value: 1 }, connect(t) { return t; }, disconnect() {} }; }
    createOscillator() { return { frequency: { value: 0 }, connect(t) { return t; }, start() {}, stop() {} }; }
    createMediaStreamDestination() { return { stream: makeStream() }; }
    async close() {}
  }
  const makeStream = () => ({ getTracks: () => [{ kind: "audio", stop() {}, addEventListener() {} }] });

  const context = {
    console,
    setTimeout, clearTimeout, setInterval, clearInterval,
    queueMicrotask, performance, Date, Math, JSON, Promise, URLSearchParams,
    TextEncoder, TextDecoder, ArrayBuffer, DataView, Uint8Array, Float32Array,
    Object, Array, Number, String, Boolean, Error, Symbol, Map, Set, RegExp,
    btoa, atob, crypto: globalThis.crypto,
    location: { search },
    navigator: {
      userAgent: "Mozilla/5.0 node-page-sender-harness Chrome/0.0.0.0",
      mediaDevices: {
        getSupportedConstraints: () => ({}),
        async getUserMedia() { return makeStream(); },
        async getDisplayMedia() { const e = new Error("harness"); e.name = "NotAllowedError"; throw e; },
      },
    },
    document: {
      visibilityState: "visible",
      getElementById: element,
      addEventListener() {},
    },
    AudioContext: AudioContextStub,
    AudioWorkletNode: AudioWorkletNodeStub,
    MediaStream: function MediaStream() { return makeStream(); },
    fetch: (url, init) => server.fetch(url, init),
    __harness: { element, makeStream },
  };
  context.window = context;
  context.globalThis = context;
  return context;
}

// -------------------------------------------------------------------------------- scenarios
function frameSamplesOf(config) { return config.descriptor.frame_samples; }

function pcmFrame(n, seed) {
  const samples = new Float32Array(n);
  for (let i = 0; i < n; i++) samples[i] = 0.35 * Math.sin((i + seed) / 7.3);
  return samples;
}

async function driveWorklet(ctx, lanes, config) {
  const framePeriodMs = (frameSamplesOf(config) / config.descriptor.sample_rate) * 1000;
  const emitted = { system: 0, microphone: 0 };
  const startedWallMs = Date.now();
  for (let i = 0; i < config.frames; i++) {
    for (const lane of ["system", "microphone"]) {
      const st = lanes[lane];
      const handler = st.node.port.onmessage;
      if (!handler) continue;
      void handler({
        data: {
          type: "frame",
          samples: pcmFrame(frameSamplesOf(config), emitted[lane] * 13 + (lane === "system" ? 1 : 2)),
          startFrame: emitted[lane] * frameSamplesOf(config),
          quanta: (emitted[lane] + 1) * 8,
        },
      });
      emitted[lane] += 1;
    }
    await sleep(framePeriodMs);
  }
  return { emitted, worklet_elapsed_ms: Date.now() - startedWallMs, frame_period_ms: framePeriodMs };
}

async function scenarioTransport(context, server, config) {
  const lanes = {};
  for (const lane of ["system", "microphone"]) {
    lanes[lane] = await context.attachLane(
      lane, context.__harness.makeStream(), context.__harness.element("synthOut"), null,
    );
  }
  const drive = await driveWorklet(context, lanes, config);
  // Let the tail of the queue flush; a bounded FIFO needs more than one frame period.
  await sleep(config.settleMs);
  const laneState = {};
  for (const lane of ["system", "microphone"]) {
    const st = lanes[lane];
    laneState[lane] = {
      next_wire_sequence: st.seq,
      sent: st.sent,
      emitted: st.emitted,
      errors: st.errors,
      http: { ...st.http },
      queued_at_end: st.frames.length,
      frame_capacity: st.frameCapacity,
      dropped_frames: st.droppedFrames,
      discontinuities: st.discontinuities,
    };
  }
  return { drive, lanes: laneState };
}

async function scenarioRecreate(context, server, config) {
  const probe = context.window.__mossX1RecreateProbe;
  if (!probe) throw new Error("page did not expose the x1 recreate seam");
  // A mutant is EXPECTED to break somewhere in this sequence. Record every step and return
  // the partial trace with the failure instead of throwing, so the evidence shows how it
  // broke rather than only that it timed out.
  const steps = {};
  try {
    steps.initial = await probe.initialize();
    probe.enqueue("microphone");
    await waitFor(() => probe.state().lanes.microphone.send_in_flight, 3000, "microphone POST in flight");
    probe.enqueue("system", 1); // wrong wire sequence -> forced strict-v2 409
    steps.after_409 = await waitFor(
      () => (probe.state().session_recreate_required ? probe.state() : null), 4000, "409 to require recreate",
    );
    steps.begun = probe.beginRecreate();
    await sleep(Math.max(10, Math.floor(config.frameDelayMs / 3)));
    steps.during_drain = probe.state();
    steps.failed_recreate = await probe.finishRecreate();
    probe.beginRecreate();
    steps.recovered = await probe.finishRecreate();
    await waitFor(() => probe.state().lanes.system.sent >= 1, 4000, "system lane to resend at zero");
    probe.enqueue("microphone");
    steps.resumed = await waitFor(
      () => (probe.state().lanes.microphone.sent >= 2 ? probe.state() : null), 4000, "microphone resume",
    );
    steps.completed = true;
  } catch (error) {
    steps.completed = false;
    steps.failure = String((error && error.message) || error);
    try { steps.final_state = probe.state(); } catch { steps.final_state = null; }
  }
  return steps;
}

async function waitFor(predicate, timeoutMs, description) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = predicate();
    if (value) return value === true ? true : value;
    await sleep(5);
  }
  throw new Error(`timed out waiting for ${description}`);
}

// ------------------------------------------------------------------------------------- main
async function main() {
  const config = {
    scenario: "transport",
    mutation: "none",
    frames: 50,
    frameDelayMs: 100,
    settleMs: 1500,
    failCreateAttempts: [],
    delayFirstAcceptedLane: null,
    sessionIds: ["harness-session-a", "harness-session-b", "harness-session-c"],
    search: "",
    descriptor: {
      sample_rate: 16000,
      frame_samples: 1000,
      bounds: { max_frame_samples: 16000, max_retained_samples: 320000, max_queue_depth: 64 },
    },
    ...JSON.parse(process.argv[2] || "{}"),
  };

  const { source, applied } = mutate(transportScript(), config.mutation);
  const server = makeServer(config);
  const context = vm.createContext(makeContextGlobals(server, config.search));
  vm.runInContext(source, context, { filename: "capture_pipeline_page.html" });
  await sleep(50); // let the page's own auto-probe IIFE settle

  const scenario = config.scenario === "recreate"
    ? await scenarioRecreate(context, server, config)
    : await scenarioTransport(context, server, config);

  const result = {
    harness: "prototypes/browser-capture-feasibility/page_sender_harness.mjs",
    page: "prototypes/browser-capture-feasibility/capture_pipeline_page.html",
    config: { ...config, descriptor: config.descriptor },
    mutation_applied: applied,
    scenario,
    server: {
      created_sessions: server.state.createdSessions,
      held_response_lane: server.state.heldResponseLane,
      held_response_released_wall_ms: server.state.heldResponseReleasedWallMs,
      create_attempts: server.state.createAttempts,
      frame_status_counts: server.state.frameStatuses,
      max_concurrent_frame_requests: server.state.maxConcurrentFrameRequests,
      per_lane_max_concurrent: Object.fromEntries(
        Object.entries(server.state.perLaneMaxConcurrent).filter(([k]) => !k.endsWith(":live")),
      ),
      accepted_by_lane: ["system", "microphone"].reduce((acc, lane) => {
        acc[lane] = server.state.acceptances.filter((a) => a.lane === lane).length;
        return acc;
      }, {}),
      next_sequence_by_lane: [...server.state.sessions.values()].map((s) => ({ id: s.id, next: s.next })),
      acceptances: server.state.acceptances,
      telemetry: server.state.telemetry,
      heartbeats: server.state.heartbeats.slice(-4),
      heartbeat_count: server.state.heartbeats.length,
    },
  };
  await emit(result);
}

// process.exit() truncates a large pending stdout write; wait for the flush callback.
const emit = (payload) =>
  new Promise((resolve) => process.stdout.write(JSON.stringify(payload), resolve));

main().then(
  () => process.exit(0),
  async (error) => {
    await emit({ error: String((error && error.stack) || error) });
    process.exit(1);
  },
);
