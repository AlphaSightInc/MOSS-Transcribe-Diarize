import { Fragment, type JSX } from "preact";
import type { TranscriptTurn } from "../lib/mergeTranscript";
import { isSettledTurn, projectTranscriptCards } from "../lib/transcriptCards";
import type { TranscriptSearchPart, TranscriptSearchTurn } from "../lib/transcriptSearch";
import { transcriptLaneLabel } from "../lib/transcriptOrder";
import { formatTranscriptClockTime } from "../lib/transcriptExport";
import { resolveSpeakerColorToken } from "../lib/speakerMap";

interface Props {
  searchTurns: readonly TranscriptSearchTurn[];
  activeMatchId: number;
  finalized: boolean;
  canCorrectPassages: boolean;
  correctionWaiting?: boolean;
  speakerColorMap: ReadonlyMap<string, string>;
  onSpeakerClick: (id: string) => void;
  onPassageCorrection: (turn: TranscriptTurn) => void;
}

function searchParts(parts: readonly TranscriptSearchPart[], activeMatchId: number): JSX.Element[] {
  return parts.map((part, index) => part.matchId === null
    ? <Fragment key={`text-${index}`}>{part.text}</Fragment>
    : <mark key={`match-${part.matchId}-${index}`}
        className={`tr-search-match${part.matchId === activeMatchId ? " is-active" : ""}`}
        data-search-match-id={part.matchId}>{part.text}</mark>);
}

export function TranscriptCards({ searchTurns, activeMatchId, finalized, canCorrectPassages, correctionWaiting = false,
  speakerColorMap, onSpeakerClick, onPassageCorrection }: Props) {
  const cards = projectTranscriptCards(searchTurns.map(item => item.turn));
  const byTurn = new Map(searchTurns.map(item => [item.turn, item]));

  return <div className="transcript-cards" data-transcript-cards="true">
    {cards.map((card, index) => {
      const first = card.rows[0]!;
      const foundFirst = byTurn.get(first);
      const label = foundFirst?.speakerLabel ?? first.display_name;
      const unknown = card.speakerId === "S00" || card.speakerId === "UNKNOWN";
      const state = card.rows.some(row => row.state === "provisional") ? "provisional" :
        card.rows.every(row => row.state === "final") ? "final" : "confirmed";
      const segments = card.rows.flatMap(row => row.segments);
      const targetKeys = card.rows.flatMap(row => row.target_segment_keys);
      const colorToken = resolveSpeakerColorToken(first.speaker, speakerColorMap);
      return <article key={card.key} className="utt transcript-card" data-card-key={card.key}
          data-s00={String(unknown)} data-continuation="false"
          data-new-speaker="true" data-state={state}
          data-preview-stale={String(card.rows.some(row => row.provisional_stale))}
          data-source-lane={first.source_lane} data-turn-start={card.start} data-turn-end={card.end}
          data-target-keys={targetKeys.join("|")} data-segments={JSON.stringify(segments)}
          style={{ "--sp": colorToken } as JSX.CSSProperties}>
        <div className="utt-meta">
          <button type="button" className="utt-speaker" data-speaker-id={card.speakerId}
            aria-label={`Name speaker ${label}`} onClick={() => onSpeakerClick(card.speakerId)}>
            <span className="utt-speaker-label">
              {foundFirst ? searchParts(foundFirst.speakerParts, activeMatchId) : label}
            </span>
          </button>
          {first.source_lane && <span className="utt-lane">{transcriptLaneLabel(first.source_lane)}</span>}
          <div className="utt-time">{formatTranscriptClockTime(card.start)}</div>
        </div>
        <div className="transcript-card-fragments">
          {card.rows.map((row, rowIndex) => {
            const found = byTurn.get(row);
            const textStatus = isSettledTurn(row, finalized) ? "settled" :
              row.state === "confirmed" ? "confirmed" : "unsettled";
            return <div key={`${card.key}:${row.target_segment_keys[0] || rowIndex}`}
                className="utt-content" data-text-status={textStatus}>
              <p className="utt-text" title={`Text ${textStatus}`}>
                {row.state === "provisional"
                  ? <><span className={`prov${row.provisional_stale ? " is-stale" : ""}`}>
                      {found ? searchParts(found.textParts, activeMatchId) : row.text}
                    </span>{index === cards.length - 1 && rowIndex === card.rows.length - 1
                      ? <span className="live-caret" aria-hidden="true" /> : null}</>
                  : found ? searchParts(found.textParts, activeMatchId) : row.text}
              </p>
              {(canCorrectPassages || correctionWaiting) && row.segment_ids.length > 0 ? (
                <button type="button" className="utt-reassign" aria-label="Reassign passage"
                  title={correctionWaiting ? "Wait for transcript improvement" : "Reassign passage"}
                  disabled={correctionWaiting}
                  data-reassign-passage={row.segment_ids.join(",")}
                  onClick={() => onPassageCorrection(row)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l11-11-4-4L4 16v4Zm9-13 4 4" /></svg>
                </button>
              ) : null}
            </div>;
          })}
        </div>
      </article>;
    })}
  </div>;
}
