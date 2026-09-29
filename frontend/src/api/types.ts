import type { SourceLane } from "../lib/transcriptOrder";
import type { TentativeSpan } from "../lib/tentative";
export type SessionMode = "live" | "file";

export type SessionLifecycle = "idle" | "active" | "closing" | "closed" | "failed" | "aborted";

export interface TranscriptItem {
  source_lane?: SourceLane;
  start: number;
  end: number;
  text: string;
  speaker: string;
  speaker_entity_id: string;
  display_name: string;
  confidence?: number | null;
  state: "provisional" | "confirmed" | "final";
  settled?: boolean;
  segment_id?: string | null;
  provisional_stale?: boolean | null;
  refinement_status?: "online_preview" | "tentative_refined" | "confirmed" | null;
  preview_speaker?: string | null;
  deep_refinement_speaker?: string | null;
  deep_refinement_changed?: boolean | null;
}

export interface TranscriptUpdateMetadata {
  operation?: string;
  replacement_key?: string;
  lane?: string;
}

export interface TranscriptRelabeledMetadata extends TranscriptUpdateMetadata {
  operation: "post_cluster_relabel";
  changed_segment_count?: number;
}

export interface TranscriptRefinementCompleteMetadata extends TranscriptUpdateMetadata {
  operation: "refinement_complete";
  identity_revision_version?: number;
  identity_revision_spans?: number;
  identity_revision_units?: number;
}

// This is deliberately the reachable Account Live subset of the reference union. The poller
// translates MOSS runtime events before they reach this shared reference dispatch seam.
export type WsEvent =
  | {
      type: "session_state";
      session_id: string;
      mode: SessionMode;
      state: string;
      status: SessionLifecycle;
      error?: string | null;
      status_line?: string | null;
      needs_review?: boolean;
      live_label_policy?: "current" | "La";
    }
  | {
      type: "transcript_update";
      session_id: string;
      seq: number;
      timestamp: string;
      items: TranscriptItem[];
      tentative_spans?: TentativeSpan[];
      metadata?: TranscriptUpdateMetadata;
    }
  | {
      type: "transcript_relabeled";
      session_id: string;
      seq: number;
      timestamp: string;
      items: TranscriptItem[];
      metadata: TranscriptRelabeledMetadata;
    }
  | {
      type: "refinement_complete";
      session_id: string;
      seq: number;
      timestamp: string;
      items: TranscriptItem[];
      metadata: TranscriptRefinementCompleteMetadata;
    }
  | {
      type: "stop_progress";
      session_id: string;
      state?: string;
      stop_phase?: string | null;
      llm_state: null;
    };
