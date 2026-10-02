import { parseRecordingInterruptions, type RecordingInterruption } from "../lib/recordingInterruption";
import type {
  SessionLifecycle,
  SessionMode,
  TranscriptItem,
  TranscriptRelabeledMetadata,
  TranscriptRefinementCompleteMetadata,
  WsEvent
} from "./types";
import { SPEAKER_NAMED_EVENT } from "../lib/meetingEvents";
import type { ProvisionalDisplaySegment, TentativeSpan } from "../lib/tentative";
import { dispatchWsEvent } from "./ws";

const CAPTURING_POLL_DELAY_MS = 100;
const IDLE_POLL_DELAY_MS = 2_000;
const RETRY_DELAYS_MS = [500, 1_000, 2_000, 5_000] as const;
const POLL_REQUEST_TIMEOUT_MS = 10_000;
const MAX_UNCHANGED_SNAPSHOT_NO_PROGRESS_ROUNDS = 2;
const TERMINAL_STATUSES = new Set<SessionLifecycle>(["failed", "aborted"]);
const FINALIZATION_STATUSES = new Set([
  "not_started",
  "running",
  "final",
  "failed",
  "unavailable"
] as const);

type FinalizationStatus = "not_started" | "running" | "final" | "failed" | "unavailable";

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
  tentativeSpans: TentativeSpan[];
  segments: ProvisionalDisplaySegment[];
}

interface MossSnapshot {
  interruptions: RecordingInterruption[];
  sessionId: string;
  status: SessionLifecycle;
  version: number;
  sampleRate: number;
  committedSamples: number;
  failureReason: string | null;
  terminalFailureReason: string | null;
  persistenceFailure: string | null;
  finalizationStatus: FinalizationStatus;
  statusLine: string | null;
  needsReview?: boolean;
  labelRevisionVersion: number;
  liveLabelPolicy: "current" | "La";
  canonicalSpeakers: string[];
  committed: MossCanonicalCommit[];
  publishedSegments: TranscriptItem[] | null;
  provisional: MossProvisionalSuffix | null;
  draft: (MossProvisionalSuffix & { endSample: number }) | null;
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
  /**
   * Only the rows derived from the snapshot's *current* provisional generation. The
   * superseded rows this render also emits (marked stale) are deliberately excluded: carrying
   * them forward is what made every generation's ghost accumulate without bound.
   */
  provisionalItems: TranscriptItem[];
  revisedSpanIds: number[];
}

export interface MossPollerOptions {
  sessionId: string;
  mode?: SessionMode;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
  dispatch?: (event: WsEvent) => void;
  onError?: (message: string) => void;
  onRecovered?: () => void;
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
 * Polls the Account Live Meeting's two independent cursors. Snapshot rendering is
 * authoritative replacement; event rendering is
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
  let identityFinalizationSeen = false;
  let lastLabelRevisionVersion = 0;
  let lastSessionState: Pick<MossSnapshot, "sessionId" | "status" | "failureReason"> | null = null;
  let lastIngressAcceptedSamples: number | null = null;
  let unchangedSnapshotNoProgressRounds = 0;
  const revisedSpanIds = new Set<number>();
  let priorProvisional: { generation: number; items: TranscriptItem[] } | null = null;
  let lastRenderedItems: TranscriptItem[] = [];
  let speakerLabelRevision = 0;

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

  function onSpeakerNamed(event: Event): void {
    if ((event as CustomEvent).detail?.meetingId !== options.sessionId || !running) return;
    // A response begun before the acknowledged rename must not restore old labels.
    stop();
    snapshotVersion = 0;
    start();
  }

  function start(): void {
    if (running) return;
    running = true;
    if (typeof document !== "undefined") document.addEventListener(SPEAKER_NAMED_EVENT, onSpeakerNamed);
    if (inFlight) { restartPending = true; return; }
    void poll();
  }

  function stop(): void {
    if (typeof document !== "undefined") document.removeEventListener(SPEAKER_NAMED_EVENT, onSpeakerNamed);
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
        fetchJson(fetcher, endpoint("snapshot", snapshotVersion), controller.signal),
        fetchJson(fetcher, endpoint("events", eventSequence), controller.signal)
      ]);

      if (currentGeneration !== generation) {
        return;
      }

      const runtimeEvents = parseRuntimeEvents(eventsPayload);
      const newEvents = dedupeNewRuntimeEvents(runtimeEvents, eventSequence);
      const captureHealth = parseCaptureHealth(snapshotPayload);
      const ingressAcceptedSamples = parseIngressAcceptedSamples(snapshotPayload);
      const snapshot = parseSnapshot(snapshotPayload);
      const labelState = parseSpeakerLabels(snapshotPayload);
      const ingressAdvanced =
        ingressAcceptedSamples !== null &&
        lastIngressAcceptedSamples !== null &&
        ingressAcceptedSamples > lastIngressAcceptedSamples;

      // `/snapshot` and `/events` are fetched in parallel, so an event can arrive in a round
      // where the snapshot came back `unchanged`. An event that cannot be rendered without a
      // snapshot is deferred, never dropped: the cursor must not advance past it, and no later
      // event may be consumed ahead of it. Re-requesting the snapshot from version 0 guarantees
      // the next round carries one, so a deferral always resolves instead of latching.
      const deferralIndex = snapshot
        ? -1
        : newEvents.findIndex((event) => eventNeedsSnapshot(event.kind));
      const consumedEvents = deferralIndex === -1 ? newEvents : newEvents.slice(0, deferralIndex);
      const consumedSequence = consumedEvents.reduce(
        (highest, event) => Math.max(highest, event.seq),
        eventSequence
      );
      const identityFinalizationArrived = consumedEvents.some(
        (event) => event.kind === "identity_finalized"
      );
      const eventCursorAdvanced = consumedSequence > eventSequence;

      if (snapshot) {
        const renderedSnapshot = renderSnapshot(
          snapshot,
          consumedSequence,
          identityFinalizationSeen || identityFinalizationArrived,
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
          error:
            snapshot.failureReason ??
            snapshot.terminalFailureReason ??
            snapshot.persistenceFailure,
          status_line: snapshot.statusLine,
          interruptions: snapshot.interruptions,
          needs_review: snapshot.needsReview,
          live_label_policy: snapshot.liveLabelPolicy
        });
        lastRenderedItems = renderedSnapshot.event.items;
        dispatch({ ...renderedSnapshot.event, items: applySpeakerLabels(lastRenderedItems, labelState.labels) });
        if (renderedSnapshot.relabelEvent) {
          dispatch({ ...renderedSnapshot.relabelEvent, items: applySpeakerLabels(lastRenderedItems, labelState.labels) });
        }
        priorProvisional = renderedSnapshot.provisional
          ? {
              generation: renderedSnapshot.provisional.generation,
              items: renderedSnapshot.provisionalItems
            }
          : null;
        lastLabelRevisionVersion = snapshot.labelRevisionVersion;
        for (const spanId of renderedSnapshot.revisedSpanIds) {
          revisedSpanIds.add(spanId);
        }
        snapshotVersion = snapshot.version;
        lastSessionState = {
          sessionId: snapshot.sessionId,
          status: snapshot.status,
          failureReason: snapshot.failureReason
        };
      } else if (lastSessionState) {
        dispatch({
          type: "session_state",
          session_id: lastSessionState.sessionId,
          mode,
          state: lastSessionState.status,
          status: lastSessionState.status,
          error: captureHealth.phase === "failed" ? captureHealth.statusLine : null,
          status_line: captureHealth.statusLine
        });
      }

      // Naming has its own revision: speech can remain unchanged while a user
      // names a speaker. Re-render cached canonical rows once, without resetting
      // the speech cursor or treating display names as speaker identity.
      if (!snapshot && labelState.revision !== speakerLabelRevision) {
        dispatch({
          type: "transcript_update",
          session_id: options.sessionId,
          seq: consumedSequence,
          timestamp: new Date().toISOString(),
          items: applySpeakerLabels(lastRenderedItems, labelState.labels),
          metadata: { operation: "snapshot" }
        });
      }
      speakerLabelRevision = labelState.revision;

      for (const event of consumedEvents) {
        const referenceEvent = mapRuntimeEvent(
          event,
          snapshot,
          identityFinalizationSeen || identityFinalizationArrived
        );
        if (referenceEvent) {
          dispatch("items" in referenceEvent
            ? { ...referenceEvent, items: applySpeakerLabels(referenceEvent.items, labelState.labels) }
            : referenceEvent);
        }
      }
      identityFinalizationSeen ||= identityFinalizationArrived;
      eventSequence = consumedSequence;
      if (ingressAcceptedSamples !== null) {
        lastIngressAcceptedSamples = ingressAcceptedSamples;
      }
      const immediateRebaseline = deferralIndex !== -1 || (!snapshot && ingressAdvanced);
      if (immediateRebaseline) {
        unchangedSnapshotNoProgressRounds = 0;
      } else if (!snapshot && snapshotVersion > 0 && !eventCursorAdvanced) {
        unchangedSnapshotNoProgressRounds += 1;
      } else {
        unchangedSnapshotNoProgressRounds = 0;
      }
      const watchdogRebaseline =
        unchangedSnapshotNoProgressRounds >= MAX_UNCHANGED_SNAPSHOT_NO_PROGRESS_ROUNDS;
      if (immediateRebaseline || watchdogRebaseline) {
        // The snapshot and v2 ingress cursors are independent. A growing cumulative ingress
        // count proves the server progressed even when this snapshot cursor was answered as
        // unchanged. If both cursors remain flat after capture stopped, a bounded uncursored
        // reread prevents a terminal transition behind a stale snapshot cursor from latching.
        snapshotVersion = 0;
        unchangedSnapshotNoProgressRounds = 0;
      }

      if (snapshot && isTerminalSnapshot(snapshot)) {
        const message = terminalMessage(snapshot);
        stop();
        options.onTerminal?.(message);
        return;
      }

      if (retryIndex > 0) options.onRecovered?.();
      retryIndex = 0;
      if (running) {
        scheduleNext(pollDelayForStatus(snapshot?.status ?? lastSessionState?.status ?? "idle"));
      }
    } catch (error) {
      if (currentGeneration !== generation) {
        return;
      }
      const message = errorMessage(error);
      if (error instanceof PollHttpError && [401, 403, 404, 409].includes(error.status)) {
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
    start,
    stop,
    poll,
    cursors: () => ({ snapshotVersion, eventSequence }),
    running: () => running
  };
}

function applySpeakerLabels(items: readonly TranscriptItem[], labels: Readonly<Record<string, string>>): TranscriptItem[] {
  return items.map((item) => ({
    ...item,
    display_name: labels[item.speaker_entity_id] ?? item.speaker
  }));
}

function parseSpeakerLabels(payload: unknown): { revision: number; labels: Record<string, string> } {
  const response = record(payload, "snapshot response");
  const labels = record(response.speaker_labels ?? {}, "speaker labels");
  return {
    revision: requiredNonNegativeNumber(response.speaker_label_revision ?? 0, "speaker label revision"),
    labels: Object.fromEntries(Object.entries(labels).map(([id, label]) => [id, requiredString(label, "speaker label")]))
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
  const committedState = publishedTranscriptState(snapshot, finalized);
  const committed = snapshot.publishedSegments?.map(item => ({ ...item, state: committedState })) ?? snapshot.committed.flatMap((commit) =>
    transcriptItemsFromMossText(
      commit.revisedTranscript ?? commit.transcript,
      commit.startSample,
      snapshot.sampleRate,
      snapshot.canonicalSpeakers,
      {
        state: committedState,
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
  // A newer generation REPLACES the preview it supersedes; it never appears beside it. The
  // reference marks a preview stale in place (`operation: "stale"`, lane `provisional`) and
  // keeps no dimmed copy of superseded text — emitting both rendered the same words twice, once
  // dim and once bright, and every superseded generation accumulated without bound.
  // Keep stale rows only ahead of the committed AUDIO boundary, while still live.
  // A commit may replace a preview with multiple text segments or no text at all.
  const staleProvisional =
    !provisional && previousProvisional && (snapshot.status === "active" || snapshot.status === "closing")
      ? previousProvisional.items
          .filter((item) => Math.round(item.end * snapshot.sampleRate) > snapshot.committedSamples)
          .map((item) => ({ ...item, provisional_stale: true }))
      : [];
  // Drafts are ephemeral, never retained as stale canonical previews. The audio frontier,
  // including an empty commit, retires them; a canonical preview supersedes them immediately.
  const draft = snapshot.draft;
  const draftItems = draft && snapshot.status === "active" && !provisional &&
    staleProvisional.length === 0 && draft.startSample === snapshot.committedSamples
    ? transcriptItemsFromMossText(draft.transcript, draft.startSample, snapshot.sampleRate, [], {
        state: "provisional", segmentIdPrefix: `draft:${draft.generation}:`, provisionalStale: false
      })
    : [];
  const items = [...committed, ...staleProvisional, ...currentProvisional, ...draftItems];
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
      tentative_spans: provisional?.tentativeSpans ?? [],
      provisional_segments: provisional?.segments ?? [],
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
    provisionalItems: currentProvisional,
    revisedSpanIds: snapshot.committed
      .filter((commit) => commit.revisedTranscript !== null)
      .map((commit) => commit.spanId)
  };
}

function mapRuntimeEvent(
  event: MossRuntimeEvent,
  snapshot: MossSnapshot | null,
  identityFinalized: boolean
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
      const committedState = publishedTranscriptState(snapshot, identityFinalized);
      return {
        type: "refinement_complete",
        session_id: event.sessionId,
        seq: event.seq,
        timestamp: new Date().toISOString(),
        items: snapshot.publishedSegments?.map(item => ({ ...item, state: committedState })) ?? snapshot.committed.flatMap((commit) =>
          transcriptItemsFromMossText(
            commit.revisedTranscript ?? commit.transcript,
            commit.startSample,
            snapshot.sampleRate,
            snapshot.canonicalSpeakers,
            {
              state: committedState,
              segmentIdPrefix: `${commit.spanId}:`,
              provisionalStale: false
            }
          )
        ),
        metadata
      };
    }
    case "session_closed":
    case "stop_requested":
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

function publishedTranscriptState(
  snapshot: MossSnapshot,
  identityFinalized: boolean
): "confirmed" | "final" {
  // A closed session can still be running automatic terminal refinement. Its current
  // identity is durable but not yet the settled publication the correction UI may edit.
  if (snapshot.status === "closed" && snapshot.finalizationStatus === "running") {
    return "confirmed";
  }
  if (["closed", "failed", "aborted"].includes(snapshot.status)) {
    return "final";
  }
  return identityFinalized ? "final" : "confirmed";
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
  signal: AbortSignal
): Promise<unknown> {
  const response = await fetcher(url, {
    method: "GET",
    cache: "no-store",
    credentials: "same-origin",
    signal
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
  const settledThrough = parseSettledThroughSamples(session.settled_through_samples);
  return {
    sessionId: requiredString(snapshot.session_id, "snapshot session_id"),
    status: lifecycle(session.status),
    version: requiredNonNegativeNumber(session.version, "snapshot version"),
    sampleRate: requiredPositiveNumber(descriptor.sample_rate, "snapshot sample_rate"),
    interruptions: parseRecordingInterruptions(response.interruptions, requiredPositiveNumber(descriptor.sample_rate, "snapshot sample_rate")),
    committedSamples: requiredNonNegativeNumber(session.committed_samples, "committed samples"),
    failureReason: optionalString(session.failure_reason),
    terminalFailureReason: parseTerminalFailureReason(snapshot.terminal_failure),
    persistenceFailure: optionalString(response.persistence_failure),
    finalizationStatus: parseFinalizationStatus(session.finalization_status),
    statusLine: optionalString(response.status_line),
    ...(typeof response.needs_review === "boolean" ? { needsReview: response.needs_review } : {}),
    labelRevisionVersion: requiredNonNegativeNumber(
      session.label_revision_version ?? 0,
      "label revision version"
    ),
    liveLabelPolicy: session.live_label_policy === "La" ? "La" : "current",
    canonicalSpeakers: stringList(identity.canonical_speakers),
    publishedSegments: parsePublishedSegments(session.effective_transcript, descriptor.sample_rate,
      stringList(identity.canonical_speakers), settledThrough),
    committed: Array.isArray(session.committed)
      ? session.committed.map(parseCanonicalCommit)
      : fail("snapshot committed"),
    draft: snapshot.draft === null || snapshot.draft === undefined ? null : (() => {
      const draft = record(snapshot.draft, "draft");
      if (draft.authority !== "draft") return fail("draft authority");
      return { ...parseProvisionalSuffix(draft),
        endSample: requiredNonNegativeNumber(draft.end_sample, "draft end sample") };
    })(),
    provisional: session.provisional === null || session.provisional === undefined
      ? null
      : parseProvisionalSuffix(session.provisional)
  };
}

function parseSettledThroughSamples(value: unknown): Map<string, number> {
  const frontiers = new Map<string, number>();
  if (value === undefined || value === null) return frontiers;
  if (!Array.isArray(value)) return fail("settled through samples");
  for (const entry of value) {
    if (!Array.isArray(entry) || entry.length !== 2 ||
        (entry[0] !== "system" && entry[0] !== "microphone")) return fail("settled lane frontier");
    frontiers.set(entry[0], requiredNonNegativeNumber(entry[1], "settled lane frontier"));
  }
  return frontiers;
}

/** Published segments are authoritative, including an empty surface; old snapshots omit them. */
function parsePublishedSegments(value: unknown, sampleRate: unknown, speakers: string[],
                                settledThrough: ReadonlyMap<string, number>): TranscriptItem[] | null {
  if (value === undefined) return null;
  if (!Array.isArray(value)) return fail("effective transcript");
  const rate = requiredPositiveNumber(sampleRate, "snapshot sample_rate");
  return value.map((raw, index) => {
    const segment = record(raw, "effective transcript segment");
    const lane = segment.source_lane;
    if (lane !== undefined && lane !== "system" && lane !== "microphone") return fail("source lane");
    const entity = optionalString(segment.canonical_speaker) ?? "S00";
    const speakerIndex = speakers.indexOf(entity);
    const speaker = speakerIndex < 0 ? "S00" : `S${String(speakerIndex + 1).padStart(2, "0")}`;
    const endSample = requiredNonNegativeNumber(segment.end_sample, "segment end");
    return {
      ...(lane ? { source_lane: lane } : {}),
      start: requiredNonNegativeNumber(segment.start_sample, "segment start") / rate,
      end: endSample / rate,
      text: requiredString(segment.text, "segment text"),
      speaker, speaker_entity_id: entity, display_name: speaker,
      state: "confirmed", segment_id: `effective:${index}`,
      settled: segment.authority === "settled" &&
        (!lane || !settledThrough.has(lane) || endSample <= settledThrough.get(lane)!)
    };
  });
}

function parseCaptureHealth(payload: unknown): { phase: string | null; statusLine: string | null } {
  const response = record(payload, "snapshot response");
  return {
    phase: optionalString(response.capture_phase),
    statusLine: optionalString(response.status_line)
  };
}

function parseIngressAcceptedSamples(payload: unknown): number | null {
  const response = record(payload, "snapshot response");
  if (response.v2_session === null || response.v2_session === undefined) {
    return null;
  }
  const v2Session = record(response.v2_session, "v2 session");
  const lanes = record(v2Session.lanes, "v2 session lanes");
  let acceptedSamples = 0;
  for (const lane of Object.values(lanes)) {
    const laneSnapshot = record(lane, "v2 lane snapshot");
    const laneAcceptedSamples = laneSnapshot.accepted_samples;
    if (
      typeof laneAcceptedSamples !== "number" ||
      !Number.isFinite(laneAcceptedSamples) ||
      laneAcceptedSamples < 0
    ) {
      return null;
    }
    acceptedSamples += laneAcceptedSamples;
  }
  return Number.isFinite(acceptedSamples) ? acceptedSamples : null;
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
    transcript: requiredTextField(commit.transcript, "canonical commit transcript"),
    revisedTranscript: optionalString(commit.revised_transcript)
  };
}

function parseProvisionalSuffix(value: unknown): MossProvisionalSuffix {
  const provisional = record(value, "provisional suffix");
  return {
    generation: requiredNonNegativeNumber(provisional.generation, "provisional generation"),
    startSample: requiredNonNegativeNumber(provisional.start_sample, "provisional start_sample"),
    transcript: requiredTextField(provisional.transcript, "provisional transcript"),
    tentativeSpans: Array.isArray(provisional.tentative_spans)
      ? provisional.tentative_spans.map((value) => {
          const span = record(value, "tentative span");
          return {
            start_sample: requiredNonNegativeNumber(span.start_sample, "tentative start_sample"),
            end_sample: requiredNonNegativeNumber(span.end_sample, "tentative end_sample"),
            source_lane: requiredTextField(span.source_lane, "tentative source_lane"),
            speaker: requiredTextField(span.speaker, "tentative speaker")
          };
        })
      : [],
    segments: Array.isArray(provisional.segments)
      ? provisional.segments.map((value) => {
          const segment = record(value, "provisional segment");
          return {
            start_sample: requiredNonNegativeNumber(segment.start_sample, "provisional segment start_sample"),
            end_sample: requiredNonNegativeNumber(segment.end_sample, "provisional segment end_sample"),
            text: requiredTextField(segment.text, "provisional segment text"),
            source_lane: requiredTextField(segment.source_lane, "provisional segment source_lane"),
            tentative_speaker: optionalString(segment.tentative_speaker)
          };
        })
      : []
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

function requiredTextField(value: unknown, label: string): string {
  if (typeof value !== "string") {
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

function parseFinalizationStatus(value: unknown): FinalizationStatus {
  if (value === undefined) return "not_started";
  if (typeof value === "string" && FINALIZATION_STATUSES.has(value as FinalizationStatus)) {
    return value as FinalizationStatus;
  }
  return fail("snapshot finalization status");
}

function isTerminalSnapshot(snapshot: MossSnapshot): boolean {
  if (snapshot.terminalFailureReason !== null || snapshot.persistenceFailure !== null) return true;
  if (TERMINAL_STATUSES.has(snapshot.status)) return true;
  return snapshot.status === "closed" && snapshot.finalizationStatus !== "running";
}

function parseTerminalFailureReason(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  const failure = record(value, "snapshot terminal failure");
  return optionalString(failure.message) ?? "Live Meeting interrupted.";
}

function terminalMessage(snapshot: MossSnapshot): string {
  return (
    snapshot.failureReason ??
    snapshot.terminalFailureReason ??
    snapshot.persistenceFailure ??
    snapshot.statusLine ??
    `Session ${snapshot.status}.`
  );
}

/**
 * `identity_finalized` renders the committed transcript, so it cannot be translated into a
 * reference event without a snapshot. Every other reachable kind renders from the event alone.
 */
function eventNeedsSnapshot(kind: string): boolean {
  return kind === "identity_finalized";
}

function fail(label: string): never {
  throw new Error(`Malformed MOSS ${label}.`);
}

class PollHttpError extends Error {
  constructor(readonly status: number, detail: string) {
    super(detail);
  }
}
