import { transcriptLaneLabel } from "../lib/transcriptOrder";
import { Fragment, type JSX } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { requestMeetingHistoryRefresh, SPEAKER_NAMED_EVENT } from "../lib/meetingEvents";
import { nameMeetingSpeaker, reassignMeetingPassages } from "../api/speakers";
import {
  buildTranscriptExportText,
  formatTranscriptClockTime,
  serializeTranscriptExport,
  triggerTranscriptExportDownload,
  type TranscriptExportFormat
} from "../lib/transcriptExport";
import { groupSegmentsIntoTurns, type TranscriptTurn } from "../lib/mergeTranscript";
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
import {
  sessionId,
  sessionNeedsReview,
  sessionStatus,
  sessionTitle,
  sessionTranscriptItems,
  transcript,
  transcriptSearchQuery
} from "../state/session";
import { autoscroll } from "../state/ui";

interface TranscriptLegendEntry {
  colorToken: string;
  legendKey: string;
  visibleLabel: string;
  speakerId: string;
  committed: boolean;
  isUnidentified: boolean;
}

interface PassageCorrectionTarget {
  meetingId: string;
  passageIds: string[];
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

async function copyTextToClipboard(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  if (typeof document === "undefined") {
    throw new Error("Clipboard unavailable");
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

export function TranscriptPane() {
  const [findOpen, setFindOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [activeSearchMatchIndex, setActiveSearchMatchIndex] = useState(0);
  const transcriptFindRef = useRef<HTMLInputElement | null>(null);
  const transcriptScrollRef = useRef<HTMLDivElement | null>(null);
  const [namingTarget, setNamingTarget] = useState<TranscriptLegendEntry | null>(null);
  const [saveVoiceprint, setSaveVoiceprint] = useState(true);
  const [speakerName, setSpeakerName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [namingMessage, setNamingMessage] = useState<string | null>(null);
  const [namingError, setNamingError] = useState<string | null>(null);
  const namingDialogRef = useRef<HTMLDialogElement | null>(null);
  const namingInputRef = useRef<HTMLInputElement | null>(null);
  const [correctionTarget, setCorrectionTarget] = useState<PassageCorrectionTarget | null>(null);
  const [correctionMode, setCorrectionMode] = useState<"existing" | "new">("existing");
  const [correctionSpeakerId, setCorrectionSpeakerId] = useState("");
  const [correctionName, setCorrectionName] = useState("");
  const [savingCorrection, setSavingCorrection] = useState(false);
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const correctionDialogRef = useRef<HTMLDialogElement | null>(null);

  const fullTranscriptItems = transcript.value;
  const searchQuery = transcriptSearchQuery.value.trim();
  const genericSpeakerNames = fullTranscriptItems.filter(item => item.display_name === item.speaker).map((item) => ({
    display_name: item.display_name
  }));
  const consecutiveSpeakerMap = buildConsecutiveSpeakerMap(genericSpeakerNames);
  const speakerColorMap = buildSpeakerColorMap(fullTranscriptItems);
  const allTurns = groupSegmentsIntoTurns(fullTranscriptItems);
  const searchResults = buildTranscriptSearchResults(
    allTurns,
    searchQuery,
    (turn) => visibleSpeakerName(turn, consecutiveSpeakerMap)
  );
  const activeSearchMatchId =
    searchResults.matchCount > 0
      ? Math.min(activeSearchMatchIndex, searchResults.matchCount - 1)
      : -1;
  const transcriptAvailable = allTurns.length > 0;
  const activeSessionId = sessionId.value;
  const canNameSpeakers = activeSessionId !== null;
  const transcriptExportAvailable = transcriptAvailable && activeSessionId !== null;
  const legendEntries = buildLegendEntries(
    fullTranscriptItems,
    consecutiveSpeakerMap,
    speakerColorMap
  );
  const correctionSpeakers = legendEntries.filter(
    entry => !isBackendUnknownSpeakerId(entry.speakerId)
  );
  const automaticProcessingRunning =
    sessionStatus.value === "active" ||
    sessionStatus.value === "closing" ||
    (sessionStatus.value === "closed" && allTurns.some(turn => turn.state !== "final"));
  const canCorrectPassages =
    activeSessionId !== null &&
    ["closed", "failed", "aborted"].includes(sessionStatus.value) &&
    !automaticProcessingRunning;

  useEffect(() => {
    setNamingTarget(null);
    setNamingMessage(null);
    setNamingError(null);
  }, [activeSessionId, canNameSpeakers]);

  useEffect(() => {
    setCorrectionTarget(null);
    setCorrectionError(null);
  }, [activeSessionId]);

  useEffect(() => {
    if (!namingTarget) return;
    const dialog = namingDialogRef.current;
    if (!dialog) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    namingInputRef.current?.focus();
    namingInputRef.current?.select();
    return () => {
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      previousFocus?.focus();
    };
  }, [namingTarget]);

  useEffect(() => {
    if (!correctionTarget) return;
    const dialog = correctionDialogRef.current;
    if (!dialog) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    return () => {
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      previousFocus?.focus();
    };
  }, [correctionTarget]);

  function openSpeakerName(entry: TranscriptLegendEntry | undefined): void {
    const reason = !canNameSpeakers
      ? "Open a meeting to name its speakers."
      : !entry || !entry.committed
        ? "Wait until this speaker has committed speech before naming."
        : entry.speakerId === "S00"
          ? "This speech has no identified speaker yet."
          : null;
    setNamingError(null);
    setNamingMessage(reason);
    if (reason || !entry) return;
    setNamingTarget(entry);
    setSpeakerName(entry.visibleLabel);
    setSaveVoiceprint(true);
  }

  async function saveSpeakerName(event: Event): Promise<void> {
    event.preventDefault();
    if (!namingTarget || !activeSessionId || !canNameSpeakers || savingName) return;
    const meetingId = activeSessionId;
    setSavingName(true);
    setNamingError(null);
    try {
      const result = await nameMeetingSpeaker(meetingId, namingTarget.speakerId, speakerName.trim(), undefined, saveVoiceprint);
      if (sessionId.value !== meetingId) return;
      // The response acknowledges a durable display label, not a new identity.
      sessionTranscriptItems.value = sessionTranscriptItems.value.map(item =>
        item.speaker_entity_id === result.speaker_id ? { ...item, display_name: result.label } : item);
      document.dispatchEvent(new CustomEvent(SPEAKER_NAMED_EVENT, { detail: { meetingId } }));
      requestMeetingHistoryRefresh();
      setNamingMessage(result.enrollment === "not_requested"
        ? `Saved ${result.label}. Voiceprint not saved.`
        : result.enrollment === "unavailable"
        ? `Saved ${result.label}. No retained voice evidence is available for a new voiceprint.`
        : result.enrollment === "enrolled"
        ? `Saved ${result.label}. Voiceprint saved privately in this browser workspace.`
        : `Saved ${result.label}. Voiceprint will save when enough clear speech arrives before Stop.`);
      setNamingTarget(null);
    } catch (error) {
      if (sessionId.value === meetingId) {
        setNamingError(error instanceof Error ? error.message : "Speaker naming failed.");
      }
    } finally {
      setSavingName(false);
    }
  }

  function openPassageCorrection(turn: TranscriptTurn): void {
    if (!canCorrectPassages || turn.segment_ids.length === 0) return;
    const existing = correctionSpeakers.find(entry => entry.speakerId !== turn.speaker_entity_id);
    setCorrectionTarget({ meetingId: activeSessionId!, passageIds: [...turn.segment_ids] });
    setCorrectionMode(existing ? "existing" : "new");
    setCorrectionSpeakerId(existing?.speakerId ?? "");
    setCorrectionName("");
    setCorrectionError(null);
  }

  async function savePassageCorrection(event: Event): Promise<void> {
    event.preventDefault();
    if (!correctionTarget || !activeSessionId || savingCorrection) return;
    const meetingId = correctionTarget.meetingId;
    if (activeSessionId !== meetingId) {
      setCorrectionTarget(null);
      return;
    }
    setSavingCorrection(true);
    setCorrectionError(null);
    try {
      const result = await reassignMeetingPassages(
        meetingId,
        correctionTarget.passageIds,
        correctionMode === "existing"
          ? { speaker_id: correctionSpeakerId }
          : { label: correctionName.trim() }
      );
      if (sessionId.value !== meetingId) return;
      const changed = new Set(result.segment_ids);
      sessionTranscriptItems.value = sessionTranscriptItems.value.map(item =>
        item.segment_id && changed.has(item.segment_id)
          ? { ...item, speaker: result.speaker_id, speaker_entity_id: result.speaker_id, display_name: result.label }
          : item
      );
      sessionNeedsReview.value = result.needs_review;
      requestMeetingHistoryRefresh();
      setNamingMessage(`Reassigned selected passage to ${result.label}.`);
      setCorrectionTarget(null);
    } catch (error) {
      if (sessionId.value === meetingId) {
        setCorrectionError(error instanceof Error ? error.message : "Passage correction failed.");
      }
    } finally {
      setSavingCorrection(false);
    }
  }

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

      if (event.key === "Escape" && (findOpen || exportMenuOpen)) {
        event.preventDefault();
        setFindOpen(false);
        setExportMenuOpen(false);
        transcriptSearchQuery.value = "";
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [exportMenuOpen, findOpen]);

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

  async function handleCopy(): Promise<void> {
    const text = buildTranscriptExportText(allTurns, (turn) =>
      visibleSpeakerName(turn, consecutiveSpeakerMap)
    );
    try {
      await copyTextToClipboard(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  function handleDownload(format: TranscriptExportFormat): void {
    if (activeSessionId === null) {
      return;
    }
    triggerTranscriptExportDownload(serializeTranscriptExport(
      format,
      allTurns,
      (turn) => visibleSpeakerName(turn, consecutiveSpeakerMap),
      { sessionId: activeSessionId, exportedAt: new Date() },
      { needsReview: sessionNeedsReview.value }
    ));
  }

  return (
    <section className="transcript-pane">
      <header className="tr-head">
        <div className="tr-head-spacer" aria-hidden="true" />
        <div className="tr-title-wrap">
          {/* Reference markup: a <button class="tr-title"> carrying the edit hint, not an <h1>.
              Session titles are Phase 2, so the button is inert and disabled -- but the element,
              its classes and the hint glyph are the reference's, because this pane is not an
              exempt region and its geometry is measured against the reference directly. */}
          <button type="button" className="tr-title" disabled>
            {sessionTitle.value.trim() || "MOSS"}
            <span className="edit-hint" aria-hidden="true">
              ✎
            </span>
          </button>
        </div>
      </header>

      <div className="tr-legend" id="legend">
        <span className="tr-speakers-label">
          <span>Speakers</span>
          <span className="tr-speakers-count" id="tr-speakers-count">{legendEntries.length}</span>
        </span>

        {legendEntries.map((entry) => (
          <button
            key={entry.legendKey}
            type="button"
            className={`legend-chip${entry.isUnidentified ? " is-unidentified" : ""}`}
            data-speaker-id={entry.speakerId}
            disabled={!canNameSpeakers || !entry.committed || entry.speakerId === "S00"}
            aria-label={`Name speaker ${entry.visibleLabel}`}
            title={entry.speakerId === "S00" ? "This speech has no identified speaker yet" : canNameSpeakers ? "Name this speaker" : "Open a meeting to name its speakers"}
            onClick={() => openSpeakerName(entry)}
          >
            <span
              className="legend-chip-dot"
              style={{ "--sp": entry.colorToken } as JSX.CSSProperties}
            />
            <span className="legend-chip-name">{entry.visibleLabel}</span>
          </button>
        ))}

        {/* Holds the reference's Transcript|Summary toggle, which is a ruled Phase 2 deletion
            (charter §5 exemption). The container stays: `margin-left: auto` is what right-aligns
            this row, so removing it would move everything it anchors. */}
        <div className="tr-legend-right" aria-hidden="true">
          <div className="transcript-view-placeholder" />
        </div>
      </div>

      {namingMessage ? <p className="hint" role="status">{namingMessage}</p> : null}
      {sessionNeedsReview.value ? <p className="hint" role="status"><strong>Needs review.</strong> Check passages marked Speaker uncertain or a partial processing notice.</p> : null}
      {namingTarget ? (
        <dialog ref={namingDialogRef} className="history-dialog" aria-labelledby="speaker-name-title"
          onCancel={() => setNamingTarget(null)}>
          <form onSubmit={(event) => void saveSpeakerName(event)}>
            <h3 id="speaker-name-title">Name speaker</h3>
            <label htmlFor="speaker-name-input">Display name</label>
            <input ref={namingInputRef} id="speaker-name-input" value={speakerName} required
              disabled={savingName} onInput={(event) => setSpeakerName(event.currentTarget.value)} />
            <label className="sp-voiceprint"><input type="checkbox" checked={saveVoiceprint} onChange={event => setSaveVoiceprint(event.currentTarget.checked)} disabled={savingName} /><span>Save voiceprint</span></label>
            <p className="hint">Applies to this speaker throughout this meeting. When checked, enough clear speech also saves a private voiceprint. People may share the same name.</p>
            {namingError ? <p role="alert">{namingError}</p> : null}
            <div className="history-dialog-actions">
              <button className="history-toolbar-btn" type="button" disabled={savingName} onClick={() => setNamingTarget(null)}>Cancel</button>
              <button className="history-toolbar-btn" type="submit" disabled={savingName || !speakerName.trim()}>{savingName ? "Saving…" : "Save name"}</button>
            </div>
          </form>
        </dialog>
      ) : null}
      {correctionTarget ? (
        <dialog ref={correctionDialogRef} className="history-dialog" aria-labelledby="passage-speaker-title"
          onCancel={() => setCorrectionTarget(null)}>
          <form onSubmit={(event) => void savePassageCorrection(event)}>
            <h3 id="passage-speaker-title">Reassign passage</h3>
            <p className="hint">Changes only this selected passage in this recording. It does not save a voiceprint.</p>
            <label><input type="radio" name="passage-target" checked={correctionMode === "existing"}
              disabled={savingCorrection || correctionSpeakers.length === 0}
              onChange={() => setCorrectionMode("existing")} /> Existing person</label>
            <select aria-label="Existing person" value={correctionSpeakerId}
              disabled={savingCorrection || correctionMode !== "existing"}
              onChange={event => setCorrectionSpeakerId(event.currentTarget.value)}>
              {correctionSpeakers.map(entry => <option key={entry.speakerId} value={entry.speakerId}>{entry.visibleLabel}</option>)}
            </select>
            <label><input type="radio" name="passage-target" checked={correctionMode === "new"}
              disabled={savingCorrection} onChange={() => setCorrectionMode("new")} /> New person</label>
            <input aria-label="New person name" value={correctionName}
              disabled={savingCorrection || correctionMode !== "new"}
              onInput={event => setCorrectionName(event.currentTarget.value)} />
            {correctionError ? <p role="alert">{correctionError}</p> : null}
            <div className="history-dialog-actions">
              <button className="history-toolbar-btn" type="button" disabled={savingCorrection}
                onClick={() => setCorrectionTarget(null)}>Cancel</button>
              <button className="history-toolbar-btn" type="submit" disabled={savingCorrection ||
                (correctionMode === "existing" ? !correctionSpeakerId : !correctionName.trim())}>
                {savingCorrection ? "Saving…" : "Save correction"}
              </button>
            </div>
          </form>
        </dialog>
      ) : null}

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
          <div className="divider" aria-hidden="true" />
          <button
            type="button"
            className="mini-btn"
            title="Copy"
            disabled={!transcriptAvailable}
            onClick={() => void handleCopy()}
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <div className="divider" aria-hidden="true" />
          <button
            type="button"
            className={`mini-btn${autoscroll.value ? " is-on" : ""}`}
            aria-pressed={autoscroll.value}
            title="Auto-scroll as new text arrives"
            onClick={() => {
              autoscroll.value = !autoscroll.value;
            }}
          >
            Auto-scroll
          </button>
          <div className="divider" aria-hidden="true" />
          <button
            type="button"
            className="mini-switch transcript-export-trigger"
            aria-haspopup="menu"
            aria-expanded={exportMenuOpen}
            title="Export transcript"
            disabled={!transcriptExportAvailable}
            onClick={() => setExportMenuOpen((open) => !open)}
          >
            <span className="mini-switch-track" aria-hidden="true">
              <span className="mini-switch-thumb" />
            </span>
            <span className="mini-switch-label">Export transcript</span>
          </button>
        </div>

        {exportMenuOpen ? (
          <div className="transcript-export-menu" role="menu" aria-label="Export transcript format">
            {([
              ["md", "Markdown (.md)"],
              ["txt", "Plain text (.txt)"],
              ["json", "JSON (.json)"],
              ["srt", "SubRip (.srt)"],
              ["vtt", "WebVTT (.vtt)"]
            ] as const).map(([format, label]) => (
              <button
                key={format}
                type="button"
                role="menuitem"
                onClick={() => {
                  setExportMenuOpen(false);
                  handleDownload(format);
                }}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}

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
                  data-continuation={String(previousTurn?.speaker_entity_id === turn.speaker_entity_id && previousTurn?.source_lane === turn.source_lane)}
                  data-new-speaker={String(index === 0 || previousTurn?.speaker_entity_id !== turn.speaker_entity_id || previousTurn?.source_lane !== turn.source_lane)}
                  data-preview-stale={String(turn.state === "provisional" && turn.provisional_stale)}
                  data-state={turn.state}
                  data-source-lane={turn.source_lane}
                  data-turn-start={turn.start}
                  data-turn-end={turn.end}
                  data-target-keys={turn.target_segment_keys.join("|")}
                  data-segments={JSON.stringify(turn.segments)}
                  style={{ "--sp": colorToken } as JSX.CSSProperties}
                >
                  <div className="utt-meta">
                    <button type="button" className="utt-speaker" data-speaker-id={turn.speaker_entity_id}
                      aria-label={`Name speaker ${speakerLabel}`}
                      onClick={() => openSpeakerName(legendEntries.find(entry => entry.speakerId === turn.speaker_entity_id))}>
                      <span className="utt-speaker-label">
                        {renderSearchParts(speakerParts, activeSearchMatchId)}
                      </span>
                    </button>
                    {automaticProcessingRunning ? <span className="hint">Identity provisional</span> : null}
                    {turn.source_lane && <span className="utt-lane">{transcriptLaneLabel(turn.source_lane)}</span>}
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
                  {canCorrectPassages && turn.segment_ids.length > 0 ? (
                    <button type="button" className="history-action-btn"
                      data-reassign-passage={turn.segment_ids.join(",")}
                      onClick={() => openPassageCorrection(turn)}>Reassign passage</button>
                  ) : null}
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

function visibleSpeakerName(
  item: { speaker: string; speaker_entity_id: string; display_name: string },
  consecutiveSpeakerMap: ReadonlyMap<string, string>
): string {
  if (isBackendUnknownSpeakerId(item.speaker_entity_id)) {
    return resolveVisibleSpeakerLabel(item.speaker_entity_id, consecutiveSpeakerMap);
  }
  // A user may choose a label that looks like a generic speaker tag. Names are
  // literal display text, not input to automatic numbering.
  return item.display_name !== item.speaker
    ? item.display_name
    : resolveVisibleSpeakerLabel(item.speaker, consecutiveSpeakerMap);
}

function buildLegendEntries(
  items: typeof transcript.value,
  consecutiveSpeakerMap: ReadonlyMap<string, string>,
  speakerColorMap: ReadonlyMap<string, string>
): TranscriptLegendEntry[] {
  const entries = new Map<string, TranscriptLegendEntry>();

  for (const item of items) {
    // UNKNOWN is the transient legacy preview and has no legend entry. Saved S00
    // remains visible as a disabled unidentified legend, but never a correction target.
    if (item.speaker === "UNKNOWN") {
      continue;
    }

    const visibleLabel = visibleSpeakerName(item, consecutiveSpeakerMap);
    const legendKey = buildSpeakerLegendKey(item.speaker_entity_id, visibleLabel);
    if (!entries.has(legendKey)) {
      entries.set(legendKey, {
        legendKey,
        visibleLabel,
        speakerId: item.speaker_entity_id,
        committed: item.state !== "provisional",
        isUnidentified: isBackendUnknownSpeakerId(item.speaker_entity_id),
        colorToken: resolveSpeakerColorToken(item.speaker, speakerColorMap)
      });
    } else if (item.state !== "provisional") {
      entries.get(legendKey)!.committed = true;
    }
  }

  return [...entries.values()];
}
