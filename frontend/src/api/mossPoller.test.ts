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

  it("renders label-only revisions once, preserves duplicate identities and retains the speech cursor", async () => {
    let round = 0;
    const dispatched: WsEvent[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/events")) return jsonResponse({ events: [] });
      round += 1;
      return jsonResponse({
        unchanged: round > 1,
        speaker_label_revision: round === 1 ? 0 : round < 4 ? 1 : 2,
        speaker_labels: round === 1 ? {} : round < 4
          ? { "canonical-a": "Alex", "canonical-b": "Alex" } : { "canonical-a": "Alex" },
        snapshot: round > 1 ? null : {
          session_id: "meeting", descriptor: { sample_rate: 16_000 },
          session: { committed_samples: 0, status: "active", version: 7, failure_reason: null, label_revision_version: 0,
            identity_snapshot: { canonical_speakers: ["canonical-a", "canonical-b"] },
            committed: [{ span_id: 1, start_sample: 0, transcript: "[0][S01]First[1][1][S02]Second[2]", revised_transcript: null }],
            provisional: null }
        },
        // No new speech/event is required for the first label-only render.
      });
    }) as typeof fetch;
    const poller = createMossSessionPoller({ sessionId: "meeting", fetch: fetcher,
      dispatch: event => { dispatched.push(event); dispatchWsEvent(event); } });
    await poller.poll();
    await poller.poll();
    expect(transcript.value.map(item => [item.speaker_entity_id, item.display_name])).toEqual([
      ["canonical-a", "Alex"], ["canonical-b", "Alex"]
    ]);
    expect(poller.cursors().snapshotVersion).toBe(7);
    const renders = () => dispatched.filter(event => event.type === "transcript_update").length;
    expect(renders()).toBe(2);
    await poller.poll();
    expect(renders()).toBe(2);
    await poller.poll();
    expect(renders()).toBe(3);
    expect(transcript.value[1].display_name).toBe("S02");
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
      onError,
      dispatch: (event) => dispatched.push(event),
      fetch: vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/events")) return jsonResponse({ events: [] });
        return jsonResponse({
          snapshot: {
            session_id: "session-empty-text",
            descriptor: { sample_rate: 16_000 },
            session: { committed_samples: 0,
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
      onError,
      fetch: vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/events")) return jsonResponse({ events: [] });
        return jsonResponse({
          snapshot: {
            session_id: "session-non-text",
            descriptor: { sample_rate: 16_000 },
            session: { committed_samples: 0,
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
            session: { committed_samples: 0,
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
          session: { committed_samples: 0,
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

  it.each([
    ["one segment", "active", 16_000, "[0][S01]hello world[1]", ["hello world"]],
    ["multiple segments", "active", 16_000, "[0][S01]hello[0.4][0.6][S02]world[1]", ["hello", "world"]],
    ["empty committed span", "active", 16_000, "", []],
    ["not yet committed", "active", 0, "", ["hello world"]],
    ["aborted", "aborted", 0, "", []],
    ["failed", "failed", 0, "", []],
  ])("retires preview by audio frontier: %s", async (_name, status, boundary, text, expected) => {
    let round = 0;
    const onError = vi.fn();
    const poller = createMossSessionPoller({
      sessionId: "preview", onError,
      fetch: vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/events")) return jsonResponse({ events: [] });
        round += 1;
        return jsonResponse({ unchanged: false, snapshot: {
          session_id: "preview", descriptor: { sample_rate: 16_000 },
          session: {
            status: round === 1 ? "active" : status, version: round,
            committed_samples: round === 1 ? 0 : boundary,
            identity_snapshot: { canonical_speakers: ["speaker-1", "speaker-2"] },
            label_revision_version: 0, failure_reason: null,
            committed: round > 1 && boundary ? [{ span_id: 1, start_sample: 0, transcript: text, revised_transcript: null }] : [],
            provisional: round === 1 ? { generation: 1, start_sample: 0, end_sample: 16_000,
              transcript: "[0][S00]hello world[1]" } : null,
          },
        }});
      }) as typeof fetch,
    });
    await poller.poll();
    expect(transcript.value.map(item => item.text)).toEqual(["hello world"]);
    await poller.poll();
    expect(onError).not.toHaveBeenCalled();
    expect(transcript.value.map(item => item.text)).toEqual(expected);
    if (boundary) expect(transcript.value.every(item => item.state !== "provisional")).toBe(true);
    if (_name === "multiple segments") {
      expect(transcript.value.map(item => item.speaker_entity_id)).toEqual(["speaker-1", "speaker-2"]);
    }
    poller.stop();
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
          session: { committed_samples: 0,
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
          session: { committed_samples: 0,
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
          session: { committed_samples: 0,
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
          session: { committed_samples: 0,
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
          session: { committed_samples: 0,
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
          session: { committed_samples: 0,
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

  it.each([401, 403, 404, 409])("stops on terminal HTTP %i instead of scheduling a retry", async (status) => {
    const onTerminal = vi.fn();
    const poller = createMossSessionPoller({
      sessionId: "missing-session",
      fetch: vi.fn(async () => jsonResponse({ detail: "polling ended" }, status)) as typeof fetch,
      onTerminal
    });

    await poller.poll();

    expect(poller.running()).toBe(false);
    expect(onTerminal).toHaveBeenCalledWith("polling ended");
  });

  it("continues active background polling at 100 ms even when snapshots are unchanged", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("document", Object.assign(new EventTarget(), { visibilityState: "hidden" }));
    let snapshots = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/events")) return jsonResponse({ events: [] });
      snapshots += 1;
      return jsonResponse(snapshots > 1 ? { unchanged: true, snapshot: null } : {
        snapshot: { session_id: "active-background", descriptor: { sample_rate: 16_000 },
          session: { committed_samples: 0, status: "active", version: 1, failure_reason: null,
            identity_snapshot: { canonical_speakers: [] }, committed: [], provisional: null } }
      });
    }) as typeof fetch;
    const poller = createMossSessionPoller({ sessionId: "active-background", fetch: fetcher });
    try {
      poller.start();
      await vi.advanceTimersByTimeAsync(0);
      expect(snapshots).toBe(1);
      await vi.advanceTimersByTimeAsync(99);
      expect(snapshots).toBe(1);
      await vi.advanceTimersByTimeAsync(1);
      expect(snapshots).toBe(2);
      await vi.advanceTimersByTimeAsync(100);
      expect(snapshots).toBe(3);
      poller.stop();
      await vi.advanceTimersByTimeAsync(2_000);
      expect(snapshots).toBe(3);
    } finally {
      poller.stop();
      vi.unstubAllGlobals();
      vi.useRealTimers();
    }
  });

  it("uses 100 ms active polling and backs off to 2 s outside capture", () => {
    expect(pollDelayForStatus("active")).toBe(100);
    expect(pollDelayForStatus("closing")).toBe(2_000);
    expect(pollDelayForStatus("idle")).toBe(2_000);
  });

  it("keeps polling closed running finalization and renders final words before terminal", async () => {
    vi.useFakeTimers();
    const onTerminal = vi.fn();
    const order: string[] = [];
    let snapshotRequests = 0;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/events")) {
        return jsonResponse({
          events:
            snapshotRequests <= 1
              ? [
                  {
                    seq: 1,
                    session_id: "session-finalizing",
                    kind: "identity_finalized",
                    payload: { identity_revision_version: 1 }
                  }
                ]
              : [
                  {
                    seq: 2,
                    session_id: "session-finalizing",
                    kind: "terminal_finalization_completed",
                    payload: { finalization_status: "final" }
                  }
                ]
        });
      }
      snapshotRequests += 1;
      const final = snapshotRequests === 2;
      return jsonResponse({
        snapshot: {
          session_id: "session-finalizing",
          descriptor: { sample_rate: 16_000 },
          session: { committed_samples: 0,
            status: "closed",
            finalization_status: final ? "final" : "running",
            version: snapshotRequests,
            failure_reason: null,
            label_revision_version: 0,
            identity_snapshot: { canonical_speakers: ["speaker-0001"] },
            committed: [
              {
                span_id: 1,
                start_sample: 0,
                transcript: final
                  ? "[0][S01]terminal final words[1]"
                  : "[0][S01]durable stop tail[1]",
                revised_transcript: null
              }
            ],
            provisional: null
          }
        },
        unchanged: false,
        status_line: null
      });
    });
    const poller = createMossSessionPoller({
      sessionId: "session-finalizing",
      fetch: fetcher as typeof fetch,
      dispatch(event) {
        if (event.type === "transcript_update") {
          order.push(`transcript:${event.items[0]?.text}:${event.items[0]?.state}`);
        }
      },
      onTerminal(message) {
        order.push(`terminal:${message}`);
        onTerminal(message);
      }
    });

    try {
      poller.start();
      await vi.advanceTimersByTimeAsync(0);
      expect(snapshotRequests).toBe(1);
      expect(poller.running()).toBe(true);
      expect(onTerminal).not.toHaveBeenCalled();
      expect(order).toEqual(["transcript:durable stop tail:final"]);

      await vi.advanceTimersByTimeAsync(1_999);
      expect(snapshotRequests).toBe(1);
      await vi.advanceTimersByTimeAsync(1);

      expect(snapshotRequests).toBe(2);
      expect(order).toEqual([
        "transcript:durable stop tail:final",
        "transcript:terminal final words:final",
        "terminal:Session closed."
      ]);
      expect(onTerminal).toHaveBeenCalledWith("Session closed.");
      expect(poller.running()).toBe(false);
    } finally {
      poller.stop();
      vi.useRealTimers();
    }
  });

  it("ends visibly when persistence fences a closed running finalizer", async () => {
    const order: string[] = [];
    const onTerminal = vi.fn();
    const poller = createMossSessionPoller({
      sessionId: "session-persistence-fenced",
      fetch: vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/events")) return jsonResponse({ events: [] });
        return jsonResponse({
          snapshot: {
            session_id: "session-persistence-fenced",
            descriptor: { sample_rate: 16_000 },
            session: { committed_samples: 0,
              status: "closed",
              finalization_status: "running",
              version: 8,
              failure_reason: null,
              label_revision_version: 0,
              identity_snapshot: { canonical_speakers: ["speaker-0001"] },
              committed: [
                {
                  span_id: 1,
                  start_sample: 0,
                  transcript: "[0][S01]last durable prefix[1]",
                  revised_transcript: null
                }
              ],
              provisional: null
            },
            terminal_failure: { message: "transcript_persistence_failed" }
          },
          unchanged: false,
          persistence_failure: "transcript_persistence_failed",
          status_line: null
        });
      }) as typeof fetch,
      dispatch(event) {
        if (event.type === "transcript_update") {
          order.push(`transcript:${event.items[0]?.text}`);
        }
      },
      onTerminal(message) {
        order.push(`terminal:${message}`);
        onTerminal(message);
      }
    });

    await poller.poll();

    expect(order).toEqual([
      "transcript:last durable prefix",
      "terminal:transcript_persistence_failed"
    ]);
    expect(onTerminal).toHaveBeenCalledWith("transcript_persistence_failed");
    expect(poller.running()).toBe(false);
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


it("reports reader recovery once, including an unchanged snapshot, preserving cursors", async () => {
  vi.useFakeTimers();
  const recovered=vi.fn(); let offline=false;
  const fetcher=vi.fn(async (url: RequestInfo | URL) => {
    if(offline) throw new TypeError("Failed to fetch");
    if(String(url).includes("/events")) return jsonResponse({events:[]});
    return jsonResponse(String(url).includes("since_version=7") ? {unchanged:true} : {
      snapshot:{session_id:"recover",descriptor:{sample_rate:16000},session:{status:"active",version:7,
        committed_samples:0,identity_snapshot:{canonical_speakers:[]},committed:[],provisional:null}}
    });
  }) as typeof fetch;
  const poller=createMossSessionPoller({sessionId:"recover",fetch:fetcher,onRecovered:recovered});
  try {
    poller.start();await vi.advanceTimersByTimeAsync(0);
    offline=true;await vi.advanceTimersByTimeAsync(100);
    expect(recovered).not.toHaveBeenCalled();
    offline=false;await vi.advanceTimersByTimeAsync(500);
    expect(recovered).toHaveBeenCalledOnce();
    expect(poller.cursors().snapshotVersion).toBe(7);
    await vi.advanceTimersByTimeAsync(100);
    expect(recovered).toHaveBeenCalledOnce();
  } finally {poller.stop();vi.useRealTimers();}
});

it.each([false, true])("consumes published overlapping lane segments with finalization=%s without reparsing mono text", async finalized => {
  resetSessionState();
  const onError = vi.fn();
  const poller = createMossSessionPoller({sessionId:"lane-meeting",onError,dispatch:dispatchWsEvent,
    fetch: vi.fn(async input => jsonResponse(String(input).includes('/events') ? {events: finalized ? [{seq:1,session_id:'lane-meeting',kind:'identity_finalized',payload:{}}] : []} : {
      speaker_labels:{"speaker-0001":"Alex","speaker-0002":"Alex"},
      snapshot:{session_id:"lane-meeting",descriptor:{sample_rate:16000},session:{
        committed_samples:48000,status:"active",version:1,failure_reason:null,
        identity_snapshot:{canonical_speakers:["speaker-0001","speaker-0002"]},
        committed:[{span_id:1,start_sample:0,transcript:"[0][S01]Obsolete mono words[3]",revised_transcript:null}],
        effective_transcript:[
          {start_sample:0,end_sample:16000,text:"Microphone words",canonical_speaker:"speaker-0002",source_lane:"microphone",authority:"terminal"},
          {start_sample:0,end_sample:48000,text:"System words",canonical_speaker:"speaker-0001",source_lane:"system",authority:"terminal"}
        ],provisional:null
      }}
    })) as typeof fetch});
  await poller.poll();
  expect(onError).not.toHaveBeenCalled();
  expect(transcript.value.map(s=>[s.source_lane,s.speaker_entity_id,s.display_name,s.start,s.end,s.text])).toEqual([
    ["system","speaker-0001","Alex",0,3,"System words"],
    ["microphone","speaker-0002","Alex",0,1,"Microphone words"]
  ]);
  resetSessionState();
});


it("an empty published surface clears previous mono words", async () => {
  resetSessionState();
  const onError=vi.fn();
  const poller=createMossSessionPoller({sessionId:"empty",onError,dispatch:dispatchWsEvent,
    fetch:vi.fn(async input=>jsonResponse(String(input).includes('/events')?{events:[]}:{snapshot:{
      session_id:"empty",descriptor:{sample_rate:16000},session:{committed_samples:16000,status:"active",version:2,
      identity_snapshot:{canonical_speakers:["speaker-0001"]},
      committed:[{span_id:1,start_sample:0,transcript:"[0][S01]Removed words[1]",revised_transcript:null}],
      effective_transcript:[],provisional:null}
    }})) as typeof fetch});
  await poller.poll();
  expect(onError).not.toHaveBeenCalled();
  expect(transcript.value).toEqual([]);
});
