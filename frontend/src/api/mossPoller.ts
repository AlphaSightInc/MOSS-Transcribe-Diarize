import type {
  SessionLifecycle,
  SessionMode,
  TranscriptItem,
  TranscriptRelabeledMetadata,
  TranscriptRefinementCompleteMetadata,
  WsEvent
} from "./types";
import { dispatchWsEvent } from "./ws";

const CAPTURING_POLL_DELAY_MS = 250;
const IDLE_POLL_DELAY_MS = 2_000;
const RETRY_DELAYS_MS = [500, 1_000, 2_000, 5_000] as const;
const POLL_REQUEST_TIMEOUT_MS = 10_000;
const TERMINAL_STATUSES = new Set<SessionLifecycle>(["closed", "failed", "aborted"]);

type JsonObject = Record<string, unknown>;

interface MossCanonicalCommit {
  spanId: number;
  startSample: number;
  transcript: string;
  revisedTranscript: string | null;
}

interface MossProvisionalSuffix {
  generation: number;
  startSample: number;
  transcript: string;
}

interface MossSnapshot {
  sessionId: string;
  status: SessionLifecycle;
  version: number;
  sampleRate: number;
  failureReason: string | null;
  statusLine: string | null;
  labelRevisionVersion: number;
  canonicalSpeakers: string[];
  committed: MossCanonicalCommit[];
  provisional: MossProvisionalSuffix | null;
}

interface MossRuntimeEvent {
  seq: number;
  sessionId: string;
  kind: string;
  payload: JsonObject;
}

interface SnapshotRender {
  event: Extract<WsEvent, { type: "transcript_update" }>;
  relabelEvent: Extract<WsEvent, { type: "transcript_relabeled" }> | null;
  provisional: MossProvisionalSuffix | null;
  revisedSpanIds: number[];
}

export interface MossPollerOptions {
  sessionId: string;
  accessToken: string;
  mode?: SessionMode;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
  dispatch?: (event: WsEvent) => void;
  onError?: (message: string) => void;
  onTerminal?: (message: string) => void;
}

export interface MossSessionPoller {
  start(): void;
  stop(): void;
  poll(): Promise<void>;
  cursors(): Readonly<{ snapshotVersion: number; eventSequence: number }>;
  running(): boolean;
}

/**
 * Polls MOSS's two independent cursors and translates only the five reachable Phase-1
 * reference events. Snapshot rendering is authoritative replacement; event rendering is
 * replay-deduped by sequence and supplies lifecycle/refinement notifications.
 */
export function createMossSessionPoller(options: MossPollerOptions): MossSessionPoller {
  const fetcher = options.fetch ?? globalThis.fetch;
  const dispatch = options.dispatch ?? dispatchWsEvent;
  const mode = options.mode ?? "live";
  const baseUrl = (options.baseUrl ?? "").replace(/\/$/, "");
  let snapshotVersion = 0;
  let eventSequence = 0;
  let running = false;
  let inFlight = false;
  let restartPending = false;
  let generation = 0;
  let retryIndex = 0;
  let retryTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
  let pollController: AbortController | null = null;
  let finalizationSeen = false;
  let lastLabelRevisionVersion = 0;
  const revisedSpanIds = new Set<number>();
  let priorProvisional: { generation: number; items: TranscriptItem[] } | null = null;

  function endpoint(path: "snapshot" | "events", cursor: number): string {
    const encodedSessionId = encodeURIComponent(options.sessionId);
    const query = path === "snapshot" ? `since_version=${cursor}` : `since_seq=${cursor}`;
    return `${baseUrl}/api/live/sessions/${encodedSessionId}/${path}?${query}`;
  }

  function scheduleNext(delay: number): void {
    if (!running || retryTimer !== null) {
      return;
    }
    retryTimer = globalThis.setTimeout(() => {
      retryTimer = null;
      void poll();
    }, delay);
  }

  function stop(): void {
    generation += 1;
    running = false;
    restartPending = false;
    pollController?.abort();
    pollController = null;
    if (retryTimer !== null) {
      globalThis.clearTimeout(retryTimer);
      retryTimer = null;
    }
  }

  async function poll(): Promise<void> {
    if (inFlight) {
      return;
    }

    const currentGeneration = generation;
    const controller = new AbortController();
    pollController = controller;
    let timedOut = false;
    const pollTimeout = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, POLL_REQUEST_TIMEOUT_MS);
    inFlight = true;
    try {
      const [snapshotPayload, eventsPayload] = await Promise.all([
        fetchJson(fetcher, endpoint("snapshot", snapshotVersion), options.accessToken, controller.signal),
        fetchJson(fetcher, endpoint("events", eventSequence), options.accessToken, controller.signal)
      ]);

      if (currentGeneration !== generation) {
        return;
      }

      const runtimeEvents = parseRuntimeEvents(eventsPayload);
      const newEvents = dedupeNewRuntimeEvents(runtimeEvents, eventSequence);
      const highestEventSequence = newEvents.reduce(
        (highest, event) => Math.max(highest, event.seq),
        eventSequence
      );
      const finalizationArrived = newEvents.some((event) => event.kind === "identity_finalized");
      const snapshot = parseSnapshot(snapshotPayload);

      if (snapshot) {
        const isFinalized = finalizationSeen || finalizationArrived;
        const renderedSnapshot = renderSnapshot(
          snapshot,
          highestEventSequence,
          isFinalized,
          lastLabelRevisionVersion,
          revisedSpanIds,
          priorProvisional
        );
        dispatch({
          type: "session_state",
          session_id: snapshot.sessionId,
          mode,
          state: snapshot.status,
          status: snapshot.status,
          error: snapshot.failureReason,
          status_line: snapshot.statusLine
        });
        dispatch(renderedSnapshot.event);
        if (renderedSnapshot.relabelEvent) {
          dispatch(renderedSnapshot.relabelEvent);
        }
        priorProvisional = renderedSnapshot.provisional
          ? {
              generation: renderedSnapshot.provisional.generation,
              items: renderedSnapshot.event.items.filter((item) => item.state === "provisional")
            }
          : null;
        lastLabelRevisionVersion = snapshot.labelRevisionVersion;
        for (const spanId of renderedSnapshot.revisedSpanIds) {
          revisedSpanIds.add(spanId);
        }
        snapshotVersion = snapshot.version;
      }

      for (const event of newEvents) {
        const referenceEvent = mapRuntimeEvent(event, snapshot, isFinalizationKnown(finalizationSeen, finalizationArrived));
        if (referenceEvent) {
          dispatch(referenceEvent);
        }
      }
      finalizationSeen ||= finalizationArrived;
      eventSequence = highestEventSequence;

      if (snapshot && TERMINAL_STATUSES.has(snapshot.status)) {
        const message = snapshot.failureReason ?? `Session ${snapshot.status}.`;
        stop();
        options.onTerminal?.(message);
        return;
      }

      retryIndex = 0;
      if (running) {
        scheduleNext(pollDelayForStatus(snapshot?.status ?? "idle"));
      }
    } catch (error) {
      if (currentGeneration !== generation) {
        return;
      }
      const message = errorMessage(error);
      if (error instanceof PollHttpError && (error.status === 404 || error.status === 409)) {
        dispatch({
          type: "session_state",
          session_id: options.sessionId,
          mode,
          state: "failed",
          status: "failed",
          error: message
        });
        stop();
        options.onTerminal?.(message);
        return;
      }

      options.onError?.(timedOut ? "request timed out" : message);
      if (running) {
        const delay = RETRY_DELAYS_MS[Math.min(retryIndex, RETRY_DELAYS_MS.length - 1)];
        retryIndex += 1;
        scheduleNext(delay);
      }
    } finally {
      globalThis.clearTimeout(pollTimeout);
      if (pollController === controller) {
        pollController = null;
      }
      inFlight = false;
      if (restartPending && running) {
        restartPending = false;
        void poll();
      }
    }
  }

  return {
    start() {
      if (running) {
        return;
      }
      running = true;
      if (inFlight) {
        restartPending = true;
        return;
      }
      void poll();
    },
    stop,
    poll,
    cursors: () => ({ snapshotVersion, eventSequence }),
    running: () => running
  };
}

export function pollDelayForStatus(status: SessionLifecycle): number {
  return status === "active" ? CAPTURING_POLL_DELAY_MS : IDLE_POLL_DELAY_MS;
}

function renderSnapshot(
  snapshot: MossSnapshot,
  sequence: number,
  finalized: boolean,
  previousLabelRevisionVersion: number,
  previouslyRevisedSpanIds: ReadonlySet<number>,
  previousProvisional: { generation: number; items: TranscriptItem[] } | null
): SnapshotRender {
  const committed = snapshot.committed.flatMap((commit) =>
    transcriptItemsFromMossText(
      commit.revisedTranscript ?? commit.transcript,
      commit.startSample,
      snapshot.sampleRate,
      snapshot.canonicalSpeakers,
      {
        state: finalized ? "final" : "confirmed",
        segmentIdPrefix: `${commit.spanId}:`,
        provisionalStale: false
      }
    )
  );
  const provisional = snapshot.provisional;
  const currentProvisional = provisional
    ? transcriptItemsFromMossText(
        provisional.transcript,
        provisional.startSample,
        snapshot.sampleRate,
        snapshot.canonicalSpeakers,
        {
          state: "provisional",
          segmentIdPrefix: `prov:${provisional.generation}:`,
          provisionalStale: false
        }
      )
    : [];
  const staleProvisional =
    previousProvisional &&
    (!provisional || previousProvisional.generation !== provisional.generation)
      ? previousProvisional.items.map((item) => ({ ...item, provisional_stale: true }))
      : [];
  const items = [...committed, ...staleProvisional, ...currentProvisional];
  const relabeled =
    snapshot.labelRevisionVersion > previousLabelRevisionVersion ||
    snapshot.committed.some(
      (commit) => commit.revisedTranscript !== null && !previouslyRevisedSpanIds.has(commit.spanId)
    );

  return {
    event: {
      type: "transcript_update",
      session_id: snapshot.sessionId,
      seq: sequence,
      timestamp: new Date().toISOString(),
      items,
      metadata: { operation: "snapshot" }
    },
    relabelEvent: relabeled
      ? {
          type: "transcript_relabeled",
          session_id: snapshot.sessionId,
          seq: sequence,
          timestamp: new Date().toISOString(),
          items,
          metadata: {
            operation: "post_cluster_relabel",
            changed_segment_count: committed.length
          } satisfies TranscriptRelabeledMetadata
        }
      : null,
    provisional,
    revisedSpanIds: snapshot.committed
      .filter((commit) => commit.revisedTranscript !== null)
      .map((commit) => commit.spanId)
  };
}

function mapRuntimeEvent(
  event: MossRuntimeEvent,
  snapshot: MossSnapshot | null,
  finalized: boolean
): WsEvent | null {
  switch (event.kind) {
    case "identity_finalized": {
      if (!snapshot) {
        return null;
      }
      const metadata: TranscriptRefinementCompleteMetadata = {
        operation: "refinement_complete",
        identity_revision_version: optionalNumber(event.payload.identity_revision_version),
        identity_revision_spans: optionalNumber(event.payload.identity_revision_spans),
        identity_revision_units: optionalNumber(event.payload.identity_revision_units)
      };
      return {
        type: "refinement_complete",
        session_id: event.sessionId,
        seq: event.seq,
        timestamp: new Date().toISOString(),
        items: snapshot.committed.flatMap((commit) =>
          transcriptItemsFromMossText(
            commit.revisedTranscript ?? commit.transcript,
            commit.startSample,
            snapshot.sampleRate,
            snapshot.canonicalSpeakers,
            {
              state: finalized ? "final" : "confirmed",
              segmentIdPrefix: `${commit.spanId}:`,
              provisionalStale: false
            }
          )
        ),
        metadata
      };
    }
    case "session_closed":
    case "stop":
      return {
        type: "stop_progress",
        session_id: event.sessionId,
        state: snapshot?.status ?? "closing",
        stop_phase: event.kind,
        llm_state: null
      };
    default:
      return null;
  }
}

function transcriptItemsFromMossText(
  text: string,
  startSample: number,
  sampleRate: number,
  canonicalSpeakers: readonly string[],
  options: {
    state: TranscriptItem["state"];
    segmentIdPrefix: string;
    provisionalStale: boolean;
  }
): TranscriptItem[] {
  const offsetSeconds = startSample / sampleRate;
  return parseMossTranscript(text).map((segment, index) => {
    const speakerEntityId = speakerEntityIdFor(segment.speaker, canonicalSpeakers);
    return {
      start: offsetSeconds + segment.start,
      end: offsetSeconds + segment.end,
      text: segment.text,
      speaker: segment.speaker,
      speaker_entity_id: speakerEntityId,
      display_name: segment.speaker,
      confidence: null,
      state: options.state,
      segment_id: `${options.segmentIdPrefix}${index}`,
      provisional_stale: options.provisionalStale,
      refinement_status: options.state === "provisional" ? "online_preview" : "confirmed",
      preview_speaker: null,
      deep_refinement_speaker: null,
      deep_refinement_changed: null
    };
  });
}

function parseMossTranscript(text: string): Array<{ start: number; end: number; speaker: string; text: string }> {
  const segments: Array<{ start: number; end: number; speaker: string; text: string }> = [];
  const pattern = /\[(\d+(?:\.\d+)?)\]\[(S\d+)\]([\s\S]*?)\[(\d+(?:\.\d+)?)\](?=\s*\[|\s*$)/g;
  for (const match of text.matchAll(pattern)) {
    const start = Number(match[1]);
    const end = Number(match[4]);
    const segmentText = match[3]?.trim() ?? "";
    if (Number.isFinite(start) && Number.isFinite(end) && end >= start && segmentText.length > 0) {
      segments.push({ start, end, speaker: match[2] ?? "S00", text: segmentText });
    }
  }
  return segments;
}

function speakerEntityIdFor(speaker: string, canonicalSpeakers: readonly string[]): string {
  const match = /^S(\d+)$/.exec(speaker);
  if (!match) {
    return speaker;
  }
  const speakerIndex = Number(match[1]);
  return canonicalSpeakers[speakerIndex - 1] ?? speaker;
}

async function fetchJson(
  fetcher: typeof globalThis.fetch,
  url: string,
  accessToken: string,
  signal: AbortSignal
): Promise<unknown> {
  const response = await fetcher(url, {
    method: "GET",
    cache: "no-store",
    credentials: "same-origin",
    signal,
    headers: {
      Authorization: `Bearer ${accessToken}`
    }
  });
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new Error("invalid JSON response");
  }
  if (!response.ok) {
    throw new PollHttpError(response.status, detailFromPayload(payload));
  }
  return payload;
}

function parseSnapshot(payload: unknown): MossSnapshot | null {
  const response = record(payload, "snapshot response");
  if (response.snapshot === null || response.unchanged === true) {
    return null;
  }
  const snapshot = record(response.snapshot, "snapshot");
  const session = record(snapshot.session, "snapshot session");
  const descriptor = record(snapshot.descriptor, "snapshot descriptor");
  const identity = record(session.identity_snapshot, "identity snapshot");
  return {
    sessionId: requiredString(snapshot.session_id, "snapshot session_id"),
    status: lifecycle(session.status),
    version: requiredNonNegativeNumber(session.version, "snapshot version"),
    sampleRate: requiredPositiveNumber(descriptor.sample_rate, "snapshot sample_rate"),
    failureReason: optionalString(session.failure_reason),
    statusLine: optionalString(response.status_line),
    labelRevisionVersion: requiredNonNegativeNumber(
      session.label_revision_version ?? 0,
      "label revision version"
    ),
    canonicalSpeakers: stringList(identity.canonical_speakers),
    committed: Array.isArray(session.committed)
      ? session.committed.map(parseCanonicalCommit)
      : fail("snapshot committed"),
    provisional: session.provisional === null || session.provisional === undefined
      ? null
      : parseProvisionalSuffix(session.provisional)
  };
}

function parseRuntimeEvents(payload: unknown): MossRuntimeEvent[] {
  const response = record(payload, "events response");
  if (!Array.isArray(response.events)) {
    fail("events response events");
  }
  return response.events.map((value) => {
    const event = record(value, "runtime event");
    return {
      seq: requiredNonNegativeNumber(event.seq, "runtime event seq"),
      sessionId: requiredString(event.session_id, "runtime event session_id"),
      kind: requiredString(event.kind, "runtime event kind"),
      payload: record(event.payload, "runtime event payload")
    };
  });
}

function dedupeNewRuntimeEvents(
  events: readonly MossRuntimeEvent[],
  lastRenderedSequence: number
): MossRuntimeEvent[] {
  const seen = new Set<number>();
  return [...events]
    .sort((left, right) => left.seq - right.seq)
    .filter((event) => {
      if (event.seq <= lastRenderedSequence || seen.has(event.seq)) {
        return false;
      }
      seen.add(event.seq);
      return true;
    });
}

function parseCanonicalCommit(value: unknown): MossCanonicalCommit {
  const commit = record(value, "canonical commit");
  return {
    spanId: requiredNonNegativeNumber(commit.span_id, "canonical commit span_id"),
    startSample: requiredNonNegativeNumber(commit.start_sample, "canonical commit start_sample"),
    transcript: requiredString(commit.transcript, "canonical commit transcript"),
    revisedTranscript: optionalString(commit.revised_transcript)
  };
}

function parseProvisionalSuffix(value: unknown): MossProvisionalSuffix {
  const provisional = record(value, "provisional suffix");
  return {
    generation: requiredNonNegativeNumber(provisional.generation, "provisional generation"),
    startSample: requiredNonNegativeNumber(provisional.start_sample, "provisional start_sample"),
    transcript: requiredString(provisional.transcript, "provisional transcript")
  };
}

function lifecycle(value: unknown): SessionLifecycle {
  switch (value) {
    case "active":
    case "closing":
    case "closed":
    case "failed":
    case "aborted":
      return value;
    default:
      fail("snapshot status");
  }
}

function record(value: unknown, label: string): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail(label);
  }
  return value as JsonObject;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    fail(label);
  }
  return value;
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function requiredPositiveNumber(value: unknown, label: string): number {
  const number = requiredNonNegativeNumber(value, label);
  if (number <= 0) {
    fail(label);
  }
  return number;
}

function requiredNonNegativeNumber(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    fail(label);
  }
  return value;
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function detailFromPayload(payload: unknown): string {
  if (payload && typeof payload === "object" && typeof (payload as JsonObject).detail === "string") {
    return (payload as JsonObject).detail as string;
  }
  return "request failed";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "request failed";
}

function isFinalizationKnown(previouslySeen: boolean, arrivedNow: boolean): boolean {
  return previouslySeen || arrivedNow;
}

function fail(label: string): never {
  throw new Error(`Malformed MOSS ${label}.`);
}

class PollHttpError extends Error {
  constructor(readonly status: number, detail: string) {
    super(detail);
  }
}
