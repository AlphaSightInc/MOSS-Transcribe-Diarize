import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WsEvent } from "./types";
import {
  createMossSessionPoller,
  pollDelayForStatus,
  type MossSessionPoller
} from "./mossPoller";
import { dispatchWsEvent } from "./ws";
import { resetSessionState, transcript } from "../state/session";

describe("MOSS session poller", () => {
  beforeEach(() => {
    resetSessionState();
  });

  afterEach(() => {
    resetSessionState();
  });

  it.each([
    [
      "a canonical silence span",
      {
        committed: [
          { span_id: 12, start_sample: 0, transcript: "", revised_transcript: null }
        ],
        provisional: null
      }
    ],
    [
      "an empty provisional tail",
      {
        committed: [],
        provisional: { generation: 9, start_sample: 32_000, transcript: "" }
      }
    ]
  ])("accepts %s without aborting the poll round", async (_scenario, transcriptState) => {
    const dispatched: WsEvent[] = [];
    const onError = vi.fn();
    const poller = createMossSessionPoller({
      sessionId: "session-empty-text",
      accessToken: "view-token",
      onError,
      dispatch: (event) => dispatched.push(event),
      fetch: vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/events")) return jsonResponse({ events: [] });
        return jsonResponse({
          snapshot: {
            session_id: "session-empty-text",
            descriptor: { sample_rate: 16_000 },
            session: {
              status: "active",
              version: 4,
              failure_reason: null,
              label_revision_version: 0,
              identity_snapshot: { canonical_speakers: [] },
              ...transcriptState
            }
          },
          unchanged: false,
          status_line: null
        });
      }) as typeof fetch
    });

    await poller.poll();

    expect(onError).not.toHaveBeenCalled();
    expect(dispatched.map((event) => event.type)).toEqual(["session_state", "transcript_update"]);
    expect(poller.cursors()).toEqual({ snapshotVersion: 4, eventSequence: 0 });
  });

  it.each([
    [
      "canonical",
      { committed: [{ span_id: 12, start_sample: 0, transcript: null }], provisional: null },
      "Malformed MOSS canonical commit transcript."
    ],
    [
      "provisional",
      { committed: [], provisional: { generation: 9, start_sample: 32_000, transcript: null } },
      "Malformed MOSS provisional transcript."
    ]
  ])("still rejects a non-string %s transcript", async (_field, transcriptState, expectedError) => {
    const onError = vi.fn();
    const poller = createMossSessionPoller({
      sessionId: "session-non-text",
      accessToken: "view-token",
      onError,
      fetch: vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/events")) return jsonResponse({ events: [] });
        return jsonResponse({
          snapshot: {
            session_id: "session-non-text",
            descriptor: { sample_rate: 16_000 },
            session: {
              status: "active",
              version: 4,
              failure_reason: null,
              label_revision_version: 0,
              identity_snapshot: { canonical_speakers: [] },
              ...transcriptState
            }
          },
          unchanged: false,
          status_line: null
        });
      }) as typeof fetch
    });

    await poller.poll();

    expect(onError).toHaveBeenCalledWith(expectedError);
  });

  it("replaces transcript state from a raw snapshot, maps revisions/finalization, and advances replay cursors only after dispatch", async () => {
    const dispatched: WsEvent[] = [];
    const cursorsDuringDispatch: Array<ReturnType<MossSessionPoller["cursors"]>> = [];
    let requests = 0;
    let snapshotRequests = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      requests += 1;
      const url = String(input);
      if (url.includes("/snapshot")) {
        snapshotRequests += 1;
        const provisionalGeneration = snapshotRequests === 1 ? 9 : 10;
        return jsonResponse({
          snapshot: {
            session_id: "session-7",
            descriptor: { sample_rate: 16_000 },
            session: {
              status: "active",
              version: 3 + snapshotRequests,
              failure_reason: null,
              label_revision_version: 1,
              identity_snapshot: { canonical_speakers: ["speaker-0001"] },
              committed: [
                {
                  span_id: 12,
                  start_sample: 32_000,
                  transcript: "[0][S01]Original words[1]",
                  revised_transcript: "[0][S01]Corrected words[1]"
                }
              ],
              provisional: {
                generation: provisionalGeneration,
                start_sample: 48_000,
                transcript: "[0][S01]Still speaking[0.5]"
              }
            }
          },
          unchanged: false,
          status_line: "Server catching up"
        });
      }
      return jsonResponse({
        events: [
          { seq: 0, session_id: "session-7", kind: "session_created", payload: {} },
          {
            seq: 3,
            session_id: "session-7",
            kind: "identity_finalized",
            payload: {
              identity_revision_version: 1,
              identity_revision_spans: 1,
              identity_revision_units: 1
            }
          }
        ]
      });
    });
    let poller!: MossSessionPoller;
    poller = createMossSessionPoller({
      sessionId: "session-7",
      accessToken: "view-token",
      fetch: fetcher as typeof fetch,
      dispatch(event) {
        dispatched.push(event);
        cursorsDuringDispatch.push(poller.cursors());
        dispatchWsEvent(event);
      }
    });

    await poller.poll();

    expect(requests).toBe(2);
    expect(fetcher.mock.calls.map(([url]) => String(url))).toEqual(
      expect.arrayContaining([
        "/api/live/sessions/session-7/snapshot?since_version=0",
        "/api/live/sessions/session-7/events?since_seq=0"
      ])
    );
    expect(transcript.value).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "12:0",
          start: 2,
          end: 3,
          text: "Corrected words",
          speaker: "S01",
          speaker_entity_id: "speaker-0001",
          state: "final"
        }),
        expect.objectContaining({
          id: "prov:9:0",
          start: 3,
          end: 3.5,
          state: "provisional"
        })
      ])
    );
    expect(dispatched.map((event) => event.type)).toEqual([
      "session_state",
      "transcript_update",
      "transcript_relabeled",
      "refinement_complete"
    ]);
    expect(cursorsDuringDispatch).toEqual([
      { snapshotVersion: 0, eventSequence: 0 },
      { snapshotVersion: 0, eventSequence: 0 },
      { snapshotVersion: 0, eventSequence: 0 },
      { snapshotVersion: 4, eventSequence: 0 }
    ]);
    expect(poller.cursors()).toEqual({ snapshotVersion: 4, eventSequence: 3 });

    await poller.poll();

    expect(fetcher.mock.calls.map(([url]) => String(url))).toEqual(
      expect.arrayContaining([
        "/api/live/sessions/session-7/snapshot?since_version=4",
        "/api/live/sessions/session-7/events?since_seq=3"
      ])
    );
    // A newer provisional generation REPLACES the one it supersedes. This assertion previously
    // required BOTH rows to survive, which encoded the defect rather than the contract: every
    // superseded generation was retained and re-emitted, so at the 250 ms capture cadence a
    // meeting accumulated one dimmed duplicate per poll of the very same words.
    const provisionalRows = transcript.value.filter((item) => item.state === "provisional");
    expect(provisionalRows).toHaveLength(1);
    expect(provisionalRows[0]).toEqual(
      expect.objectContaining({ id: "prov:10:0", provisional_stale: false })
    );
    expect(dispatched.filter((event) => event.type === "transcript_relabeled")).toHaveLength(1);
  });

  it("keeps exactly one provisional lane no matter how many generations pass", async () => {
    let snapshotRequests = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (!String(input).includes("/snapshot")) {
        return jsonResponse({ events: [] });
      }
      snapshotRequests += 1;
      return jsonResponse({
        snapshot: {
          session_id: "session-7",
          descriptor: { sample_rate: 16_000 },
          session: {
            status: "active",
            version: 3 + snapshotRequests,
            failure_reason: null,
            label_revision_version: 0,
            identity_snapshot: { canonical_speakers: ["speaker-0001"] },
            committed: [],
            provisional: {
              generation: 8 + snapshotRequests,
              start_sample: 48_000,
              transcript: `[0][S01]generation ${8 + snapshotRequests}[0.5]`
            }
          }
        },
        unchanged: false,
        status_line: null
      });
    });
    const poller = createMossSessionPoller({
      sessionId: "session-7",
      accessToken: "view-token",
      fetch: fetcher as typeof fetch
    });

    await poller.poll();
    await poller.poll();
    await poller.poll();
    await poller.poll();

    const provisionalRows = transcript.value.filter((item) => item.state === "provisional");
    expect(provisionalRows).toHaveLength(1);
    expect(provisionalRows[0]).toEqual(
      expect.objectContaining({ text: "generation 12", provisional_stale: false })
    );
  });

  it("marks the retained preview stale once the provisional lane goes away", async () => {
    let snapshotRequests = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (!String(input).includes("/snapshot")) {
        return jsonResponse({ events: [] });
      }
      snapshotRequests += 1;
      return jsonResponse({
        snapshot: {
          session_id: "session-7",
          descriptor: { sample_rate: 16_000 },
          session: {
            status: "active",
            version: 3 + snapshotRequests,
            failure_reason: null,
            label_revision_version: 0,
            identity_snapshot: { canonical_speakers: ["speaker-0001"] },
            committed: [],
            provisional:
              snapshotRequests === 1
                ? { generation: 9, start_sample: 48_000, transcript: "[0][S01]Still speaking[0.5]" }
                : null
          }
        },
        unchanged: false,
        status_line: null
      });
    });
    const poller = createMossSessionPoller({
      sessionId: "session-7",
      accessToken: "view-token",
      fetch: fetcher as typeof fetch
    });

    await poller.poll();
    expect(
      transcript.value.filter((item) => item.state === "provisional").map((item) => item.provisional_stale)
    ).toEqual([false]);

    await poller.poll();

    const provisionalRows = transcript.value.filter((item) => item.state === "provisional");
    expect(provisionalRows).toHaveLength(1);
    expect(provisionalRows[0]).toEqual(
      expect.objectContaining({ id: "prov:9:0", provisional_stale: true })
    );
  });

  it("defers an event it cannot render instead of advancing the cursor past it", async () => {
    const dispatched: WsEvent[] = [];
    let snapshotRequests = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (!String(input).includes("/snapshot")) {
        return jsonResponse({
          events: [
            {
              seq: 3,
              session_id: "session-7",
              kind: "identity_finalized",
              payload: {
                identity_revision_version: 1,
                identity_revision_spans: 1,
                identity_revision_units: 1
              }
            }
          ]
        });
      }
      snapshotRequests += 1;
      // The two cursors are fetched in parallel, so the first round returns an event alongside
      // an `unchanged` snapshot — the exact race that used to lose the event permanently.
      if (snapshotRequests === 1) {
        return jsonResponse({ snapshot: null, unchanged: true, status_line: null });
      }
      return jsonResponse({
        snapshot: {
          session_id: "session-7",
          descriptor: { sample_rate: 16_000 },
          session: {
            status: "active",
            version: 5,
            failure_reason: null,
            label_revision_version: 0,
            identity_snapshot: { canonical_speakers: ["speaker-0001"] },
            committed: [
              { span_id: 1, start_sample: 0, transcript: "[0][S01]Hello there[1]", revised_transcript: null }
            ],
            provisional: null
          }
        },
        unchanged: false,
        status_line: null
      });
    });
    const poller = createMossSessionPoller({
      sessionId: "session-7",
      accessToken: "view-token",
      fetch: fetcher as typeof fetch,
      dispatch(event) {
        dispatched.push(event);
        dispatchWsEvent(event);
      }
    });

    await poller.poll();

    expect(dispatched.map((event) => event.type)).not.toContain("refinement_complete");
    expect(poller.cursors().eventSequence).toBe(0);

    await poller.poll();

    expect(dispatched.map((event) => event.type)).toContain("refinement_complete");
    expect(poller.cursors().eventSequence).toBe(3);
  });

  it("re-baselines a stale unchanged snapshot cursor so a terminal snapshot is observed", async () => {
    const onTerminal = vi.fn();
    let freshSnapshotRequests = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (!url.includes("/snapshot")) return jsonResponse({ events: [] });
      if (url.endsWith("since_version=153")) {
        // Reproduces the attended run: the service advances, but this stale cursor is answered
        // as unchanged. The client must not poll it forever and leave Stop finalizing.
        return jsonResponse({
          snapshot: null,
          unchanged: true,
          status_line: null,
          v2_session: v2Session(294)
        });
      }
      freshSnapshotRequests += 1;
      return jsonResponse({
        snapshot: {
          session_id: "session-stale-cursor",
          descriptor: { sample_rate: 16_000 },
          session: {
            status: freshSnapshotRequests === 1 ? "active" : "closed",
            version: freshSnapshotRequests === 1 ? 153 : 332,
            failure_reason: null,
            label_revision_version: 0,
            identity_snapshot: { canonical_speakers: [] },
            committed: [],
            provisional: null
          }
        },
        unchanged: false,
        status_line: null,
        v2_session: v2Session(freshSnapshotRequests === 1 ? 153 : 294)
      });
    });
    const poller = createMossSessionPoller({
      sessionId: "session-stale-cursor",
      accessToken: "view-token",
      fetch: fetcher as typeof fetch,
      onTerminal
    });

    await poller.poll();
    await poller.poll();
    await poller.poll();

    expect(fetcher.mock.calls.map(([url]) => String(url)).filter((url) => url.includes("/snapshot"))).toEqual([
      "/api/live/sessions/session-stale-cursor/snapshot?since_version=0",
      "/api/live/sessions/session-stale-cursor/snapshot?since_version=153",
      "/api/live/sessions/session-stale-cursor/snapshot?since_version=0"
    ]);
    expect(onTerminal).toHaveBeenCalledWith("Session closed.");
    expect(freshSnapshotRequests).toBe(2);
    expect(poller.running()).toBe(false);
  });

  it("re-baselines a flat stale snapshot cursor so a post-stop terminal snapshot is observed", async () => {
    const onTerminal = vi.fn();
    let freshSnapshotRequests = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (!url.includes("/snapshot")) return jsonResponse({ events: [] });
      if (url.endsWith("since_version=153")) {
        // Capture has already stopped: neither ingress nor event delivery advances, but the
        // server has completed the terminal transition behind this stale snapshot cursor.
        return jsonResponse({
          snapshot: null,
          unchanged: true,
          status_line: null,
          v2_session: v2Session(294)
        });
      }
      freshSnapshotRequests += 1;
      return jsonResponse({
        snapshot: {
          session_id: "session-flat-stale-cursor",
          descriptor: { sample_rate: 16_000 },
          session: {
            status: freshSnapshotRequests === 1 ? "closing" : "closed",
            version: freshSnapshotRequests === 1 ? 153 : 332,
            failure_reason: null,
            label_revision_version: 0,
            identity_snapshot: { canonical_speakers: [] },
            committed: [],
            provisional: null
          }
        },
        unchanged: false,
        status_line: null,
        v2_session: v2Session(294)
      });
    });
    const poller = createMossSessionPoller({
      sessionId: "session-flat-stale-cursor",
      accessToken: "view-token",
      fetch: fetcher as typeof fetch,
      onTerminal
    });

    await poller.poll();
    await poller.poll();
    await poller.poll();
    await poller.poll();

    expect(fetcher.mock.calls.map(([url]) => String(url)).filter((url) => url.includes("/snapshot"))).toEqual([
      "/api/live/sessions/session-flat-stale-cursor/snapshot?since_version=0",
      "/api/live/sessions/session-flat-stale-cursor/snapshot?since_version=153",
      "/api/live/sessions/session-flat-stale-cursor/snapshot?since_version=153",
      "/api/live/sessions/session-flat-stale-cursor/snapshot?since_version=0"
    ]);
    expect(onTerminal).toHaveBeenCalledWith("Session closed.");
    expect(freshSnapshotRequests).toBe(2);
    expect(poller.running()).toBe(false);
  });

  it("does not re-baseline an unchanged snapshot while the event cursor advances", async () => {
    let eventSequence = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/events")) {
        eventSequence += 1;
        return jsonResponse({
          events: [{ seq: eventSequence, session_id: "session-event-progress", kind: "stop", payload: {} }]
        });
      }
      if (url.endsWith("since_version=153")) {
        return jsonResponse({
          snapshot: null,
          unchanged: true,
          status_line: null,
          v2_session: v2Session(294)
        });
      }
      return jsonResponse({
        snapshot: {
          session_id: "session-event-progress",
          descriptor: { sample_rate: 16_000 },
          session: {
            status: "closing",
            version: 153,
            failure_reason: null,
            label_revision_version: 0,
            identity_snapshot: { canonical_speakers: [] },
            committed: [],
            provisional: null
          }
        },
        unchanged: false,
        status_line: null,
        v2_session: v2Session(294)
      });
    });
    const poller = createMossSessionPoller({
      sessionId: "session-event-progress",
      accessToken: "view-token",
      fetch: fetcher as typeof fetch
    });

    await poller.poll();
    await poller.poll();
    await poller.poll();
    await poller.poll();

    expect(fetcher.mock.calls.map(([url]) => String(url)).filter((url) => url.includes("/snapshot"))).toEqual([
      "/api/live/sessions/session-event-progress/snapshot?since_version=0",
      "/api/live/sessions/session-event-progress/snapshot?since_version=153",
      "/api/live/sessions/session-event-progress/snapshot?since_version=153",
      "/api/live/sessions/session-event-progress/snapshot?since_version=153"
    ]);
    expect(poller.cursors()).toEqual({ snapshotVersion: 153, eventSequence: 4 });
  });

  it("updates capture health when the transcript snapshot cursor is unchanged", async () => {
    const dispatched: WsEvent[] = [];
    let snapshotRequests = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (!String(input).includes("/snapshot")) return jsonResponse({ events: [] });
      snapshotRequests += 1;
      if (snapshotRequests === 2) {
        return jsonResponse({
          snapshot: null,
          unchanged: true,
          capture_phase: "failed",
          status_line: "Shared audio capture failed. The session is continuing."
        });
      }
      return jsonResponse({
        snapshot: {
          session_id: "session-health",
          descriptor: { sample_rate: 16_000 },
          session: {
            status: "active",
            version: 4,
            failure_reason: null,
            label_revision_version: 0,
            identity_snapshot: { canonical_speakers: [] },
            committed: [],
            provisional: null
          }
        },
        unchanged: false,
        capture_phase: "recording",
        status_line: "Capturing microphone and shared audio."
      });
    });
    const poller = createMossSessionPoller({
      sessionId: "session-health",
      accessToken: "view-token",
      fetch: fetcher as typeof fetch,
      dispatch: (event) => dispatched.push(event)
    });

    await poller.poll();
    await poller.poll();

    expect(dispatched.filter((event) => event.type === "session_state").at(-1)).toMatchObject({
      status: "active",
      error: "Shared audio capture failed. The session is continuing.",
      status_line: "Shared audio capture failed. The session is continuing."
    });
  });

  it("uses capture-owner authority once to recover a terminal snapshot after view revocation", async () => {
    const dispatched: WsEvent[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const authorization = new Headers(init?.headers).get("Authorization");
      if (authorization === "Bearer capture-owner" && String(input).includes("/snapshot")) {
        return jsonResponse({
          snapshot: {
            session_id: "session-terminal",
            descriptor: { sample_rate: 16_000 },
            session: {
              status: "failed",
              version: 5,
              failure_reason: "shared audio lane failed",
              label_revision_version: 0,
              identity_snapshot: { canonical_speakers: [] },
              committed: [],
              provisional: null
            }
          },
          unchanged: false,
          capture_phase: "failed",
          status_line: "Shared audio capture failed."
        });
      }
      return jsonResponse({ detail: "invalid bearer authority" }, 401);
    });
    const onTerminal = vi.fn();
    const poller = createMossSessionPoller({
      sessionId: "session-terminal",
      accessToken: "view-token",
      terminalAccessToken: "capture-owner",
      fetch: fetcher as typeof fetch,
      dispatch: (event) => dispatched.push(event),
      onTerminal
    });

    await poller.poll();

    expect(onTerminal).toHaveBeenCalledWith("shared audio lane failed");
    expect(dispatched.filter((event) => event.type === "session_state").at(-1)).toMatchObject({
      status: "failed",
      error: "shared audio lane failed"
    });
    expect(fetcher.mock.calls.some(([, init]) =>
      new Headers(init?.headers).get("Authorization") === "Bearer capture-owner"
    )).toBe(true);
  });

  it.each([401, 403, 404, 409])("stops on terminal HTTP %i instead of scheduling a retry", async (status) => {
    const onTerminal = vi.fn();
    const poller = createMossSessionPoller({
      sessionId: "missing-session",
      accessToken: "view-token",
      fetch: vi.fn(async () => jsonResponse({ detail: "polling ended" }, status)) as typeof fetch,
      onTerminal
    });

    await poller.poll();

    expect(poller.running()).toBe(false);
    expect(onTerminal).toHaveBeenCalledWith("polling ended");
  });

  it("uses the ruled 250 ms capture cadence and 2 s finalization cadence", () => {
    expect(pollDelayForStatus("active")).toBe(250);
    expect(pollDelayForStatus("closing")).toBe(2_000);
    expect(pollDelayForStatus("idle")).toBe(2_000);
  });
});

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload
  } as Response;
}

function v2Session(acceptedSamples: number) {
  return {
    status: "active",
    terminal_reason: null,
    lanes: {
      microphone: { accepted_samples: acceptedSamples },
      system: { accepted_samples: acceptedSamples }
    }
  };
}
