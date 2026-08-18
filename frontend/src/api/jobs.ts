import type { SessionLifecycle, TranscriptItem, WsEvent } from "./types";
import { dispatchWsEvent } from "./ws";

const POLL_DELAY_MS = 1_000;
const RETRY_DELAYS_MS = [500, 1_000, 2_000, 5_000] as const;
const SEGMENTS_READY_STATUSES = new Set(["waiting_review", "done"]);
const TERMINAL_STATUSES = new Set(["waiting_review", "done", "failed", "cancelled"]);

export interface FileJob {
  id: string;
  status: string;
  progress: number;
  error: string | null;
  updatedAt: number | null;
}

export interface FileJobSegment {
  id: string;
  start: number;
  end: number;
  speaker: string;
  text: string;
}

export interface JobsApiOptions {
  baseUrl?: string;
  bearerToken?: string;
  fetch?: typeof globalThis.fetch;
  createXmlHttpRequest?: () => XMLHttpRequest;
}

export interface UploadProgress {
  loaded: number;
  total: number;
}

export interface SubmitJobOptions extends JobsApiOptions {
  onUploadProgress?: (progress: UploadProgress) => void;
}

export interface FileJobPollerOptions extends JobsApiOptions {
  jobId: string;
  dispatch?: (event: WsEvent) => void;
  onProgress?: (job: FileJob) => void;
  onTerminal?: (job: FileJob) => void;
  onError?: (message: string) => void;
}

export interface FileJobPoller {
  start(): void;
  stop(): void;
  poll(): Promise<void>;
  running(): boolean;
}

export class JobsApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "JobsApiError";
  }
}

export async function submitJob(file: File, options: SubmitJobOptions = {}): Promise<FileJob> {
  const form = new FormData();
  form.append("file", file);
  return parseJob(await uploadJob(options, form));
}

export async function getJob(jobId: string, options: JobsApiOptions = {}): Promise<FileJob> {
  return parseJob(await requestJson(options, `/api/jobs/${encodeURIComponent(jobId)}`, {
    method: "GET",
    cache: "no-store"
  }));
}

export async function getJobSegments(
  jobId: string,
  options: JobsApiOptions = {}
): Promise<FileJobSegment[]> {
  const payload = await requestJson(options, `/api/jobs/${encodeURIComponent(jobId)}/segments`, {
    method: "GET",
    cache: "no-store"
  });
  const segments = (payload as { segments?: unknown }).segments;
  if (!Array.isArray(segments)) throw new Error("Invalid segments response.");
  return segments.map(parseSegment);
}

/**
 * Poll the certified batch-job API and project it through the shared transcript event seam.
 * Generation checks make an unmount/mode switch authoritative even when a request is in flight.
 */
export function createFileJobPoller(options: FileJobPollerOptions): FileJobPoller {
  const dispatch = options.dispatch ?? dispatchWsEvent;
  let running = false;
  let inFlight = false;
  let restartPending = false;
  let generation = 0;
  let retryIndex = 0;
  let timer: ReturnType<typeof globalThis.setTimeout> | null = null;

  function schedule(delay: number): void {
    if (!running || timer !== null) return;
    timer = globalThis.setTimeout(() => {
      timer = null;
      void poll();
    }, delay);
  }

  function stop(): void {
    restartPending = false;
    generation += 1;
    running = false;
    if (timer !== null) {
      globalThis.clearTimeout(timer);
      timer = null;
    }
  }

  async function poll(): Promise<void> {
    if (inFlight) return;
    const currentGeneration = generation;
    inFlight = true;
    try {
      const job = await getJob(options.jobId, options);
      if (currentGeneration !== generation) return;
      options.onProgress?.(job);

      if (SEGMENTS_READY_STATUSES.has(job.status)) {
        const segments = await getJobSegments(job.id, options);
        if (currentGeneration !== generation) return;
        dispatch(jobTranscriptEvent(job, segments));
        dispatch(jobStateEvent(job));
        stop();
        options.onTerminal?.(job);
        return;
      }

      dispatch(jobStateEvent(job));
      if (TERMINAL_STATUSES.has(job.status)) {
        stop();
        options.onTerminal?.(job);
        return;
      }

      retryIndex = 0;
      schedule(POLL_DELAY_MS);
    } catch (error) {
      if (currentGeneration !== generation) return;
      const message = errorMessage(error);
      options.onError?.(message);
      if (error instanceof JobsApiError && [400, 401, 403, 404].includes(error.status)) {
        dispatch(jobFailureEvent(options.jobId, message));
        stop();
        options.onTerminal?.({
          id: options.jobId,
          status: "failed",
          progress: 1,
          error: message,
          updatedAt: null
        });
        return;
      }
      const delay = RETRY_DELAYS_MS[Math.min(retryIndex, RETRY_DELAYS_MS.length - 1)];
      retryIndex += 1;
      schedule(delay);
    } finally {
      inFlight = false;
      if (restartPending && running) {
        restartPending = false;
        void poll();
      }
    }
  }

  return {
    start() {
      if (running) return;
      generation += 1;
      running = true;
      retryIndex = 0;
      if (inFlight) {
        restartPending = true;
        return;
      }
      void poll();
    },
    stop,
    poll,
    running: () => running
  };
}

function jobStateEvent(job: FileJob): Extract<WsEvent, { type: "session_state" }> {
  return {
    type: "session_state",
    session_id: job.id,
    mode: "file",
    state: job.status,
    status: lifecycleForJobStatus(job.status),
    error: job.error,
    status_line: job.error ?? job.status.replaceAll("_", " ")
  };
}

function jobFailureEvent(jobId: string, message: string): Extract<WsEvent, { type: "session_state" }> {
  return {
    type: "session_state",
    session_id: jobId,
    mode: "file",
    state: "failed",
    status: "failed",
    error: message,
    status_line: message
  };
}

function jobTranscriptEvent(
  job: FileJob,
  segments: readonly FileJobSegment[]
): Extract<WsEvent, { type: "transcript_update" }> {
  return {
    type: "transcript_update",
    session_id: job.id,
    seq: 0,
    timestamp: new Date((job.updatedAt ?? Date.now() / 1_000) * 1_000).toISOString(),
    items: segments.map((segment) => segmentToTranscriptItem(job.id, segment)),
    metadata: { operation: "snapshot" }
  };
}

function segmentToTranscriptItem(jobId: string, segment: FileJobSegment): TranscriptItem {
  return {
    start: segment.start,
    end: segment.end,
    text: segment.text,
    speaker: segment.speaker,
    speaker_entity_id: segment.speaker,
    display_name: segment.speaker,
    confidence: null,
    state: "final",
    segment_id: `${jobId}:${segment.id}`,
    provisional_stale: false,
    refinement_status: "confirmed",
    preview_speaker: null,
    deep_refinement_speaker: null,
    deep_refinement_changed: null
  };
}

function lifecycleForJobStatus(status: string): SessionLifecycle {
  if (status === "waiting_review" || status === "done") return "closed";
  if (status === "failed") return "failed";
  if (status === "cancelled") return "aborted";
  return "active";
}

function uploadJob(options: SubmitJobOptions, form: FormData): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const request = (options.createXmlHttpRequest ?? (() => new XMLHttpRequest()))();
    request.open("POST", `${baseUrl(options)}/api/jobs`, true);
    const bearerToken = options.bearerToken?.trim();
    if (bearerToken) request.setRequestHeader("Authorization", `Bearer ${bearerToken}`);

    request.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) return;
      options.onUploadProgress?.({ loaded: event.loaded, total: event.total });
    };
    request.onerror = () => reject(new JobsApiError("Upload failed.", request.status));
    request.onabort = () => reject(new JobsApiError("Upload cancelled.", request.status));
    request.onload = () => {
      let payload: unknown;
      try {
        payload = JSON.parse(request.responseText);
      } catch {
        reject(new Error("Invalid JSON response."));
        return;
      }
      if (request.status < 200 || request.status >= 300) {
        const detail = payload && typeof payload === "object" && !Array.isArray(payload)
          ? (payload as { detail?: unknown }).detail
          : null;
        reject(new JobsApiError(
          typeof detail === "string" && detail.length > 0 ? detail : "Request failed.",
          request.status
        ));
        return;
      }
      resolve(payload);
    };
    request.send(form);
  });
}

async function requestJson(options: JobsApiOptions, path: string, init: RequestInit): Promise<unknown> {
  const fetcher = options.fetch ?? globalThis.fetch;
  const headers = new Headers(init.headers);
  const bearerToken = options.bearerToken?.trim();
  if (bearerToken) headers.set("Authorization", `Bearer ${bearerToken}`);
  const response = await fetcher(`${baseUrl(options)}${path}`, {
    ...init,
    headers,
    credentials: "same-origin"
  });
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new Error("Invalid JSON response.");
  }
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && !Array.isArray(payload)
      ? (payload as { detail?: unknown }).detail
      : null;
    throw new JobsApiError(
      typeof detail === "string" && detail.length > 0 ? detail : "Request failed.",
      response.status
    );
  }
  return payload;
}

function baseUrl(options: JobsApiOptions): string {
  return (options.baseUrl ?? "").replace(/\/$/, "");
}

function parseJob(value: unknown): FileJob {
  const job = value as Record<string, unknown>;
  if (
    typeof job.id !== "string" || !job.id ||
    typeof job.status !== "string" || !job.status ||
    typeof job.progress !== "number" || !Number.isFinite(job.progress) || job.progress < 0
  ) {
    throw new Error("Invalid job response.");
  }
  return {
    id: job.id,
    status: job.status,
    progress: job.progress,
    error: typeof job.error === "string" && job.error ? job.error : null,
    updatedAt: typeof job.updated_at === "number" && job.updated_at >= 0 ? job.updated_at : null
  };
}

function parseSegment(value: unknown): FileJobSegment {
  const segment = value as Record<string, unknown>;
  if (
    typeof segment.id !== "string" ||
    typeof segment.start !== "number" || !Number.isFinite(segment.start) || segment.start < 0 ||
    typeof segment.end !== "number" || !Number.isFinite(segment.end) || segment.end < segment.start ||
    typeof segment.speaker !== "string" || typeof segment.text !== "string"
  ) {
    throw new Error("Invalid job segment.");
  }
  return segment as unknown as FileJobSegment;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed.";
}
