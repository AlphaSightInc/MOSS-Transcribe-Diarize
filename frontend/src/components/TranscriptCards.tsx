import { recordingInterruptionLine, type RecordingInterruption } from "../lib/recordingInterruption";
import { Fragment, type JSX } from "preact";
import type { TranscriptTurn } from "../lib/mergeTranscript";
import { isSettledTurn, type TranscriptRow } from "../lib/transcriptCards";
import type { TranscriptSearchPart, TranscriptSearchTurn } from "../lib/transcriptSearch";
import { formatTranscriptClockTime } from "../lib/transcriptExport";
import { isBackendUnknownSpeakerId, speakerColorToken } from "../lib/speakerMap";

interface Props {
  rows: readonly TranscriptRow[];
  interruptions?: readonly RecordingInterruption[];
  search: ReadonlyMap<TranscriptTurn, TranscriptSearchTurn>;
  activeMatchId: number;
  finalized: boolean;
  canCorrectPassages: boolean;
  correctionWaiting?: boolean;
  speakerLabel: (turn: TranscriptTurn) => string;
  sourceLabel: (lane: string | undefined) => string | null;
  /** Why this speaker cannot be named now, or null when it can. */
  namingBlocked: (speakerId: string) => string | null;
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

/** Reference rows: meta column (speaker, source, time) on the left, the speaker's text on the right. */
export function TranscriptCards({ rows, interruptions = [], search, activeMatchId, finalized, canCorrectPassages,
  correctionWaiting = false, speakerLabel, sourceLabel, namingBlocked, onSpeakerClick,
  onPassageCorrection }: Props) {
  const timeline = [...rows.map((row, index) => ({ start: row.start, priority: 1, row, index, gap: null as RecordingInterruption | null })),
    ...interruptions.filter(gap => gap.end !== null).map(gap => ({ start: gap.start, priority: 0, row: null, index: -1, gap }))]
    .sort((a, b) => a.start - b.start || a.priority - b.priority);
  return <div className="transcript-cards" data-transcript-cards="true">
    {timeline.map(({ row, index, gap }) => {
      if (gap) return <p key={`interruption:${gap.start}`} className="recording-interruption" data-recording-interruption="true">{recordingInterruptionLine(gap)}</p>;
      if (!row) return null;
      const head = row.fragments[0]!;
      const unknown = isBackendUnknownSpeakerId(row.speakerId);
      const activeTail = index === rows.length - 1 && row.fragments.at(-1)!.state === "provisional";
      const state = row.fragments.some(turn => turn.state === "provisional") ? "provisional" :
        row.fragments.every(turn => turn.state === "final") ? "final" : "confirmed";
      const labelText = speakerLabel(head);
      // A continuation hides its label, so only a visible label takes part in Find.
      const headSearch = row.continuation ? undefined : search.get(head);
      const label = headSearch ? searchParts(headSearch.speakerParts, activeMatchId) : labelText;
      const blocked = row.guess ? null : namingBlocked(row.speakerId);
      // A preview row under a named voice guess; unattributed preview text names nobody.
      const guessedName = row.guess && !unknown;
      const source = sourceLabel(row.lane);
      return <article key={row.key} className={`utt transcript-card${row.guess ? " tentative-card" : ""}`}
          data-card-key={row.key} data-s00={String(unknown)}
          data-continuation={String(row.continuation)} data-new-speaker={String(!row.continuation)}
          data-active-tail={String(activeTail)} data-state={state}
          data-preview-stale={String(row.fragments.some(turn => turn.provisional_stale))}
          data-source-lane={row.lane} data-turn-start={row.start} data-turn-end={row.end}
          data-target-keys={row.fragments.flatMap(turn => turn.target_segment_keys).join("|")}
          data-segments={JSON.stringify(row.fragments.flatMap(turn => turn.segments))}
          {...(row.guess ? { "data-tentative-block": "true" } : {})}
          {...(guessedName ? { "data-speaker-guess": "true" } : {})}
          style={{ "--sp": speakerColorToken(row.speakerId) } as JSX.CSSProperties}>
        <div className="utt-meta">
          {row.guess
            ? <span className={`utt-speaker is-guess${unknown ? " is-unidentified" : ""}`} data-speaker-id={row.speakerId}>
                <span className="utt-speaker-label">{label}</span>
                {guessedName ? <span className="sr-only"> (guess)</span> : null}
              </span>
            : <button type="button" className={`utt-speaker${unknown ? " is-unidentified" : ""}`}
                data-speaker-id={row.speakerId} aria-label={`Name speaker ${labelText}`}
                disabled={blocked !== null} title={blocked ?? undefined}
                onClick={() => onSpeakerClick(row.speakerId)}>
                <span className="utt-speaker-label">{label}</span>
              </button>}
          {source ? <div className="utt-source">{source}</div> : null}
          <div className="utt-time">{formatTranscriptClockTime(row.start)}</div>
        </div>
        <div className="transcript-card-fragments">
          {row.fragments.map((turn, fragmentIndex) => {
            const found = search.get(turn);
            const text = found ? searchParts(found.textParts, activeMatchId) : turn.text;
            const textStatus = isSettledTurn(turn, finalized) ? "settled" :
              turn.state === "confirmed" ? "confirmed" : "unsettled";
            return <div key={`${row.key}:${turn.target_segment_keys[0] || fragmentIndex}`}
                className="utt-content" data-text-status={textStatus}>
              <p className="utt-text">
                {turn.state === "provisional"
                  ? <><span className={`prov${turn.provisional_stale ? " is-stale" : ""}`}>{text}</span>
                      {activeTail && fragmentIndex === row.fragments.length - 1
                        ? <span className="live-caret" aria-hidden="true" /> : null}</>
                  : text}
              </p>
              {!row.guess && (canCorrectPassages || correctionWaiting) && turn.segment_ids.length > 0 ? (
                <button type="button" className="utt-reassign" aria-label="Reassign passage"
                  title={correctionWaiting ? "Wait until the transcript finishes improving" : "Reassign passage"}
                  disabled={correctionWaiting}
                  data-reassign-passage={turn.segment_ids.join(",")}
                  onClick={() => onPassageCorrection(turn)}>
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
