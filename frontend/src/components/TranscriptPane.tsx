import { Fragment, type JSX } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { formatTranscriptClockTime } from "../lib/transcriptExport";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import {
  buildConsecutiveSpeakerMap,
  buildSpeakerColorMap,
  buildSpeakerLegendKey,
  isBackendUnknownSpeakerId,
  resolveSpeakerColorToken,
  resolveVisibleSpeakerLabel
} from "../lib/speakerMap";
import {
  buildTranscriptSearchResults,
  type TranscriptSearchPart
} from "../lib/transcriptSearch";
import { transcript, transcriptSearchQuery } from "../state/session";

interface TranscriptLegendEntry {
  colorToken: string;
  legendKey: string;
  visibleLabel: string;
}

function matchesFindShortcut(event: KeyboardEvent): boolean {
  return (
    event.key.toLocaleLowerCase() === "f" &&
    (event.metaKey || event.ctrlKey) &&
    !event.altKey
  );
}

function renderSearchParts(
  parts: readonly TranscriptSearchPart[],
  activeMatchId: number
): JSX.Element[] {
  return parts.map((part, index) =>
    part.matchId === null ? (
      <Fragment key={`text-${index}`}>{part.text}</Fragment>
    ) : (
      <mark
        key={`match-${part.matchId}-${index}`}
        className={`tr-search-match${part.matchId === activeMatchId ? " is-active" : ""}`}
        data-search-match-id={part.matchId}
      >
        {part.text}
      </mark>
    )
  );
}

export function TranscriptPane() {
  const [findOpen, setFindOpen] = useState(false);
  const [activeSearchMatchIndex, setActiveSearchMatchIndex] = useState(0);
  const transcriptFindRef = useRef<HTMLInputElement | null>(null);
  const transcriptScrollRef = useRef<HTMLDivElement | null>(null);

  const fullTranscriptItems = transcript.value;
  const searchQuery = transcriptSearchQuery.value.trim();
  const genericSpeakerNames = fullTranscriptItems.map((item) => ({
    display_name: item.speaker
  }));
  const consecutiveSpeakerMap = buildConsecutiveSpeakerMap(genericSpeakerNames);
  const speakerColorMap = buildSpeakerColorMap(fullTranscriptItems);
  const allTurns = groupSegmentsIntoTurns(fullTranscriptItems);
  const searchResults = buildTranscriptSearchResults(
    allTurns,
    searchQuery,
    (turn) => resolveVisibleSpeakerLabel(turn.speaker, consecutiveSpeakerMap)
  );
  const activeSearchMatchId =
    searchResults.matchCount > 0
      ? Math.min(activeSearchMatchIndex, searchResults.matchCount - 1)
      : -1;
  const transcriptAvailable = allTurns.length > 0;
  const legendEntries = buildLegendEntries(
    fullTranscriptItems,
    consecutiveSpeakerMap,
    speakerColorMap
  );

  useEffect(() => {
    if (findOpen) {
      transcriptFindRef.current?.focus();
      transcriptFindRef.current?.select();
    }
  }, [findOpen]);

  useEffect(() => {
    setActiveSearchMatchIndex(0);
  }, [searchQuery]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (matchesFindShortcut(event)) {
        event.preventDefault();
        setFindOpen(true);
        return;
      }

      if (event.key === "Escape" && findOpen) {
        event.preventDefault();
        setFindOpen(false);
        transcriptSearchQuery.value = "";
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [findOpen]);

  useEffect(() => {
    if (!findOpen || activeSearchMatchId < 0) {
      return;
    }

    const scrollNode = transcriptScrollRef.current;
    if (!scrollNode) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      scrollNode
        .querySelector<HTMLElement>(`[data-search-match-id="${activeSearchMatchId}"]`)
        ?.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [activeSearchMatchId, findOpen, searchQuery]);

  function cycleSearchMatch(direction: -1 | 1) {
    if (searchResults.matchCount === 0) {
      return;
    }

    setActiveSearchMatchIndex((current) =>
      (current + direction + searchResults.matchCount) % searchResults.matchCount
    );
  }

  return (
    <section className="transcript-pane">
      <header className="tr-head">
        <div className="tr-head-spacer" aria-hidden="true" />
        <div className="tr-title-wrap">
          <h1 className="tr-title">Live transcript</h1>
        </div>
      </header>

      <div className="tr-legend" id="legend">
        {legendEntries.map((entry) => (
          <span key={entry.legendKey} className="legend-chip">
            <span
              className="legend-chip-dot"
              style={{ "--sp": entry.colorToken } as JSX.CSSProperties}
            />
            <span className="legend-chip-name">{entry.visibleLabel}</span>
          </span>
        ))}
        <div className="tr-legend-right" />
      </div>

      <div className="tr-body-wrap">
        <div className="tr-floating-tools" id="tr-floating-tools">
          <button
            type="button"
            className="mini-btn"
            title="Search transcript (⌘F)"
            aria-expanded={findOpen}
            onClick={() => {
              setFindOpen((current) => {
                if (current) {
                  transcriptSearchQuery.value = "";
                  setActiveSearchMatchIndex(0);
                }
                return !current;
              });
            }}
          >
            Find
          </button>
        </div>

        {findOpen ? (
          <div className="tr-find">
            <label className="tr-find-label" htmlFor="transcript-find-input">
              Find
            </label>
            <div className="tr-find-field">
              <input
                ref={transcriptFindRef}
                id="transcript-find-input"
                type="text"
                placeholder="Search transcript…"
                value={transcriptSearchQuery.value}
                onInput={(event) => {
                  transcriptSearchQuery.value = event.currentTarget.value;
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    cycleSearchMatch(event.shiftKey ? -1 : 1);
                  }
                }}
              />
              <div className="tr-find-actions">
                {searchQuery ? (
                  <button
                    type="button"
                    className="tr-find-clear"
                    aria-label="Clear search"
                    onClick={() => {
                      transcriptSearchQuery.value = "";
                      transcriptFindRef.current?.focus();
                    }}
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                ) : null}
                <button
                  type="button"
                  className="tr-find-nav"
                  aria-label="Previous match"
                  disabled={searchResults.matchCount === 0}
                  onClick={() => cycleSearchMatch(-1)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                </button>
                <button
                  type="button"
                  className="tr-find-nav"
                  aria-label="Next match"
                  disabled={searchResults.matchCount === 0}
                  onClick={() => cycleSearchMatch(1)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </button>
              </div>
            </div>
            {searchQuery ? (
              <span className="tr-find-meta">
                {searchResults.matchCount === 0
                  ? "0 matches"
                  : `${activeSearchMatchId + 1} of ${searchResults.matchCount} matches`}
              </span>
            ) : null}
          </div>
        ) : null}

        <div ref={transcriptScrollRef} className="tr-body" id="tr-body">
          {transcriptAvailable ? (
            searchResults.turns.map((searchTurn, index) => {
              const { speakerLabel, speakerParts, textParts, turn } = searchTurn;
              const previousTurn = index > 0 ? searchResults.turns[index - 1]?.turn : null;
              const isLastTurn = index === searchResults.turns.length - 1;
              const colorToken = resolveSpeakerColorToken(turn.speaker, speakerColorMap);
              return (
                <article
                  key={`${turn.segment_ids.join(",")}-${turn.start}-${index}`}
                  className="utt"
                  data-continuation={String(previousTurn?.speaker === turn.speaker)}
                  data-new-speaker={String(index === 0 || previousTurn?.speaker !== turn.speaker)}
                  data-preview-stale={String(turn.state === "provisional" && turn.provisional_stale)}
                  data-state={turn.state}
                  style={{ "--sp": colorToken } as JSX.CSSProperties}
                >
                  <div className="utt-meta">
                    <span className="utt-speaker">
                      <span className="utt-speaker-label">
                        {renderSearchParts(speakerParts, activeSearchMatchId)}
                      </span>
                    </span>
                    <div className="utt-time">{formatTranscriptClockTime(turn.start)}</div>
                  </div>
                  <p className="utt-text">
                    {turn.state === "provisional" ? (
                      <>
                        <span className={`prov${turn.provisional_stale ? " is-stale" : ""}`}>
                          {renderSearchParts(textParts, activeSearchMatchId)}
                        </span>
                        {isLastTurn ? <span className="live-caret" aria-hidden="true" /> : null}
                      </>
                    ) : (
                      renderSearchParts(textParts, activeSearchMatchId)
                    )}
                  </p>
                </article>
              );
            })
          ) : (
            <p className="empty-state transcript-empty-state">
              Transcript will appear here when a session starts.
            </p>
          )}
        </div>
        <div className="tr-fade" aria-hidden="true" />
      </div>
    </section>
  );
}

function buildLegendEntries(
  items: typeof transcript.value,
  consecutiveSpeakerMap: ReadonlyMap<string, string>,
  speakerColorMap: ReadonlyMap<string, string>
): TranscriptLegendEntry[] {
  const entries = new Map<string, TranscriptLegendEntry>();

  for (const item of items) {
    if (isBackendUnknownSpeakerId(item.speaker)) {
      continue;
    }

    const visibleLabel = resolveVisibleSpeakerLabel(item.speaker, consecutiveSpeakerMap);
    const legendKey = buildSpeakerLegendKey(item.speaker, visibleLabel);
    if (!entries.has(legendKey)) {
      entries.set(legendKey, {
        legendKey,
        visibleLabel,
        colorToken: resolveSpeakerColorToken(item.speaker, speakerColorMap)
      });
    }
  }

  return [...entries.values()];
}
