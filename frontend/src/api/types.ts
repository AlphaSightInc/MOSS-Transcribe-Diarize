export type SessionMode = "live" | "file";

export interface TranscriptItem {
  start: number;
  end: number;
  text: string;
  speaker: string;
  speaker_entity_id: string;
  display_name: string;
  confidence?: number | null;
  state: "provisional" | "confirmed" | "final";
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
