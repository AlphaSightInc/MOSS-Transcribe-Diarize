import { describe, expect, it } from "vitest";
import type { TranscriptItem } from "../api/types";
import {
  compareSegments,
  groupSegmentsIntoTurns,
  upsertTranscriptItems
} from "./mergeTranscript";

function makeItem(overrides: Partial<TranscriptItem> = {}): TranscriptItem {
  return {
    start: 0,
    end: 1,
    text: "hello world",
    speaker: "SPEAKER_01",
    speaker_entity_id: "speaker-1",
    display_name: "SPEAKER_01",
    confidence: 0.98,
    state: "final",
    segment_id: "seg-1",
    ...overrides
  };
}

describe("mergeTranscript", () => {
  it("replaces today's single live-provisional tail in-place", () => {
    const merged = upsertTranscriptItems([], [
      makeItem({
        state: "provisional",
        text: "first preview",
        segment_id: "live-provisional"
      })
    ]);

    const next = upsertTranscriptItems(merged, [
      makeItem({
        start: 1,
        end: 2,
        state: "provisional",
        text: "second preview",
        segment_id: "live-provisional"
      })
    ]);

    expect(next).toHaveLength(1);
    expect(next[0]?.state).toBe("provisional");
    expect(next[0]?.text).toBe("second preview");
  });

  it("keeps non-overlapping provisional rows when one provisional row updates", () => {
    const merged = upsertTranscriptItems([], [
      makeItem({
        start: 0,
        end: 1,
        state: "provisional",
        text: "speaker one preview",
        segment_id: "preview-a"
      }),
      makeItem({
        start: 3,
        end: 4,
        state: "provisional",
        text: "speaker two preview",
        segment_id: "preview-b"
      })
    ]);

    const next = upsertTranscriptItems(merged, [
      makeItem({
        start: 0.25,
        end: 1.25,
        state: "provisional",
        text: "speaker one revised preview",
        segment_id: "preview-a-next"
      })
    ]);

    expect(next).toHaveLength(2);
    expect(next.map((item) => item.segment_id)).toEqual(["preview-a-next", "preview-b"]);
    expect(next.map((item) => item.text)).toEqual([
      "speaker one revised preview",
      "speaker two preview"
    ]);
  });

  it.each(["final", "confirmed"] as const)(
    "collapses a provisional row when a %s segment arrives for the same segment_id",
    (state) => {
      const merged = upsertTranscriptItems([], [
        makeItem({
          state: "provisional",
          text: "preview text",
          segment_id: "seg-2"
        })
      ]);

      const next = upsertTranscriptItems(merged, [
        makeItem({
          state,
          text: "committed text",
          segment_id: "seg-2"
        })
      ]);

      expect(next).toHaveLength(1);
      expect(next[0]?.state).toBe(state);
      expect(next[0]?.text).toBe("committed text");
    }
  );

  it("honors clear metadata for the live provisional row before merging canonical items", () => {
    const merged = upsertTranscriptItems([], [
      makeItem({
        state: "provisional",
        text: "preview text",
        segment_id: "live-provisional"
      })
    ]);

    const next = upsertTranscriptItems(
      merged,
      [
        makeItem({
          state: "final",
          text: "committed text",
          segment_id: "canonical-000001"
        })
      ],
      {
        operation: "clear",
        replacement_key: "live-provisional",
        lane: "provisional"
      }
    );

    expect(next).toHaveLength(1);
    expect(next[0]?.segment_id).toBe("canonical-000001");
    expect(next[0]?.state).toBe("final");
  });

  it("marks stale provisional updates and replaces the existing live preview row", () => {
    const merged = upsertTranscriptItems([], [
      makeItem({
        state: "provisional",
        text: "fresh preview",
        segment_id: "live-provisional"
      })
    ]);

    const next = upsertTranscriptItems(
      merged,
      [
        makeItem({
          start: 5,
          end: 6,
          state: "provisional",
          text: "stale preview",
          segment_id: "live-provisional"
        })
      ],
      {
        operation: "stale",
        replacement_key: "live-provisional",
        lane: "provisional"
      }
    );

    expect(next).toHaveLength(1);
    expect(next[0]?.text).toBe("stale preview");
    expect(next[0]?.provisional_stale).toBe(true);
  });

  it("removes the live provisional row on an empty clear update", () => {
    const merged = upsertTranscriptItems([], [
      makeItem({
        state: "provisional",
        text: "preview text",
        segment_id: "live-provisional"
      })
    ]);

    const next = upsertTranscriptItems(merged, [], {
      operation: "clear",
      replacement_key: "live-provisional",
      lane: "provisional"
    });

    expect(next).toHaveLength(0);
  });

  it("clears a stale live provisional row on canonical-only updates without metadata", () => {
    const merged = upsertTranscriptItems([], [
      makeItem({
        state: "provisional",
        text: "preview text",
        segment_id: "live-provisional"
      })
    ]);

    const next = upsertTranscriptItems(merged, [
      makeItem({
        state: "confirmed",
        text: "committed text",
        segment_id: "canonical-000001"
      })
    ]);

    expect(next).toHaveLength(1);
    expect(next[0]?.segment_id).toBe("canonical-000001");
    expect(next[0]?.state).toBe("confirmed");
  });

  it("deduplicates by segment_id, preserves sort order, and recomputes speaker boundaries", () => {
    const merged = upsertTranscriptItems([], [
      makeItem({
        start: 2,
        end: 3,
        text: "later text",
        speaker: "SPEAKER_02",
        speaker_entity_id: "speaker-2",
        display_name: "SPEAKER_02",
        segment_id: "seg-later"
      }),
      makeItem({
        start: 0,
        end: 1,
        text: "original",
        segment_id: "seg-dup"
      })
    ]);

    const next = upsertTranscriptItems(merged, [
      makeItem({
        start: 0,
        end: 1,
        text: "updated",
        segment_id: "seg-dup"
      }),
      makeItem({
        start: 1,
        end: 2,
        text: "middle text",
        speaker: "SPEAKER_01",
        speaker_entity_id: "speaker-1",
        display_name: "SPEAKER_01",
        segment_id: "seg-middle"
      })
    ]);

    expect(next.map((item) => item.text)).toEqual(["updated", "middle text", "later text"]);
    expect(next.map((item) => item.isNewSpeaker)).toEqual([true, false, true]);
    expect(next.map((item) => item.isContinuation)).toEqual([false, true, false]);
  });

  it("handles the empty-to-first-item case", () => {
    const merged = upsertTranscriptItems([], [makeItem()]);

    expect(merged).toHaveLength(1);
    expect(merged[0]?.id).toBe("seg-1");
    expect(merged[0]?.isNewSpeaker).toBe(true);
  });

  it("does not merge turns when an alias remap leaves the same entity with different display names", () => {
    const turns = groupSegmentsIntoTurns([
      makeItem({
        start: 0,
        end: 1,
        text: "first speaker text",
        speaker: "SPEAKER_02",
        speaker_entity_id: "SPEAKER_02",
        display_name: "Lex Friedman",
        segment_id: "seg-1"
      }),
      makeItem({
        start: 1,
        end: 2,
        text: "second speaker text",
        speaker: "SPEAKER_02",
        speaker_entity_id: "SPEAKER_02",
        display_name: "SPEAKER_02",
        segment_id: "seg-2"
      })
    ]);

    expect(turns).toHaveLength(2);
    expect(turns.map((turn) => turn.display_name)).toEqual(["Lex Friedman", "SPEAKER_02"]);
    expect(turns.map((turn) => turn.text)).toEqual(["first speaker text", "second speaker text"]);
  });

  it("keeps provisional items sorted after committed rows", () => {
    const items = [
      makeItem({ state: "provisional", segment_id: "seg-preview", text: "preview", start: 0.5 }),
      makeItem({ segment_id: "seg-final", text: "final", start: 0.75 })
    ].sort(compareSegments);

    expect(items.map((item) => item.state)).toEqual(["final", "provisional"]);
  });

  it("groups consecutive committed segments into turns without duplicating overlap text", () => {
    const turns = groupSegmentsIntoTurns([
      makeItem({
        start: 0,
        end: 1,
        text: "we should align on the roadmap today",
        segment_id: "seg-a"
      }),
      makeItem({
        start: 1,
        end: 2,
        text: "align on the roadmap today before launch",
        segment_id: "seg-b"
      })
    ]);

    expect(turns).toHaveLength(1);
    expect(turns[0]?.text).toBe("we should align on the roadmap today before launch");
    expect(turns[0]?.segment_ids).toEqual(["seg-a", "seg-b"]);
  });

  it("preserves formatted paragraph and list breaks when joining same-speaker segments", () => {
    const turns = groupSegmentsIntoTurns(
      [
        makeItem({
          start: 0,
          end: 1,
          text: "first point\n\n1. Alpha\n2. Beta",
          segment_id: "seg-a"
        }),
        makeItem({
          start: 1,
          end: 2,
          text: "second point\n\nNew paragraph",
          segment_id: "seg-b"
        })
      ],
      { preserveResolvedWhitespace: true }
    );

    expect(turns).toHaveLength(1);
    expect(turns[0]?.text).toBe(
      "first point\n\n1. Alpha\n2. Beta\n\nsecond point\n\nNew paragraph"
    );
  });
});
