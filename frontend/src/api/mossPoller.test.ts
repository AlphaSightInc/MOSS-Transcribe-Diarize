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
