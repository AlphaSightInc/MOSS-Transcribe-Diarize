import { type JSX } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import "../styles/transcript.css";
import { requestMeetingHistoryRefresh, SPEAKER_NAMED_EVENT } from "../lib/meetingEvents";
import { nameMeetingSpeaker, reassignMeetingPassages, VoiceprintEvidenceNotAdmittedError } from "../api/speakers";
import {
  buildTranscriptExportText
} from "../lib/transcriptExport";
import { groupSegmentsIntoTurns, type TranscriptTurn } from "../lib/mergeTranscript";
import {
  buildSpeakerColorMap,
  buildSpeakerLegendKey,
  isBackendUnknownSpeakerId,
  resolveSpeakerColorToken
} from "../lib/speakerMap";
import { buildTranscriptSearchResults } from "../lib/transcriptSearch";
import {
  defaultSpeakerLabel,
  projectTranscriptRows,
  settledSpeakerNumbers,
  transcriptCardSpeakerLabel
} from "../lib/transcriptCards";
import { recallCaptureSurface, transcriptSourceLabel } from "../lib/captureSurface";
import {
  sessionId,
  sessionNeedsReview,
  provisionalSegments,
  sessionMode,
  sessionStatus,
  sessionTitle,
  sessionTranscriptItems,
  transcript,
  transcriptSearchQuery
} from "../state/session";
import { autoscroll, selectedSummaryMeeting } from "../state/ui";
import { TranscriptCards } from "./TranscriptCards";
import { projectTentativeSegments, tentativeTurns } from "../lib/tentative";
import { SummaryPane } from "./SummaryPane";
import { view } from "../state/ui";

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

/** The one voiceprint line the pane keeps (Q6): enrollment was refused or had no usable audio. */
const VOICEPRINT_NOT_SAVED = "Voiceprint not saved — not enough clear speech";
/** Auto-scroll stays on while the reader is within this distance of the bottom (reference). */
const AUTOSCROLL_BOTTOM_TOLERANCE_PX = 8;

function matchesFindShortcut(event: KeyboardEvent): boolean {
  return (
    event.key.toLocaleLowerCase() === "f" &&
    (event.metaKey || event.ctrlKey) &&
    !event.altKey
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
  const [activeSearchMatchIndex, setActiveSearchMatchIndex] = useState(0);
  const transcriptFindRef = useRef<HTMLInputElement | null>(null);
  const transcriptScrollRef = useRef<HTMLDivElement | null>(null);
  const lastScroll = useRef({ top: 0, height: 0 });
  const [namingTarget, setNamingTarget] = useState<TranscriptLegendEntry | null>(null);
  const [saveVoiceprint, setSaveVoiceprint] = useState(true);
  const [speakerName, setSpeakerName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [voiceprintNotice, setVoiceprintNotice] = useState<string | null>(null);
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
  const allTurns = groupSegmentsIntoTurns(fullTranscriptItems);
  const guessedSpeakerIds = [...new Set(provisionalSegments.value.flatMap(segment =>
    segment.tentative_speaker ? [segment.tentative_speaker] : []))];
  const speakerColorMap = buildSpeakerColorMap(fullTranscriptItems, guessedSpeakerIds);
  const automaticProcessingRunning =
    sessionStatus.value === "active" ||
    sessionStatus.value === "closing" ||
    (sessionStatus.value === "closed" && allTurns.some(turn => turn.state !== "final"));
  const finalized = !automaticProcessingRunning;
  const speakerNumbers = settledSpeakerNumbers(allTurns, finalized, guessedSpeakerIds);
  const speakerLabel = (item: Parameters<typeof transcriptCardSpeakerLabel>[0]) =>
    transcriptCardSpeakerLabel(item, speakerNumbers);
  const speakerLabels: Record<string, string> = {};
  for (const item of fullTranscriptItems) speakerLabels[item.speaker_entity_id] = speakerLabel(item);
  for (const id of guessedSpeakerIds) speakerLabels[id] ??= defaultSpeakerLabel(id, speakerNumbers);
  const tentativeBlocks = projectTentativeSegments(provisionalSegments.value, speakerLabels);
  // Guesses replace the transcript's own preview rows; both describe the same preview words.
  const displayedTurns = tentativeBlocks.length
    ? allTurns.filter(turn => turn.state !== "provisional") : allTurns;
  const guessTurns = tentativeTurns(tentativeBlocks);
  const guesses = new Set(guessTurns);
  const rowSpeakerLabel = (turn: TranscriptTurn) => guesses.has(turn) ? turn.display_name : speakerLabel(turn);
  const rows = projectTranscriptRows(displayedTurns, guessTurns);
  const labelledTurns = new Set(rows.filter(row => !row.continuation).map(row => row.fragments[0]!));
  const searchResults = buildTranscriptSearchResults(
    [...displayedTurns, ...guessTurns],
    searchQuery,
    turn => labelledTurns.has(turn) ? rowSpeakerLabel(turn) : ""
  );
  const searchByTurn = new Map(searchResults.turns.map(item => [item.turn, item]));
  const activeSearchMatchId =
    searchResults.matchCount > 0
      ? Math.min(activeSearchMatchIndex, searchResults.matchCount - 1)
      : -1;
  const transcriptAvailable = rows.length > 0;
  const activeSessionId = sessionId.value;
  const captureSurface = activeSessionId ? recallCaptureSurface(activeSessionId) : null;
  const sourceLabel = (lane: string | undefined) => transcriptSourceLabel(lane, captureSurface, sessionMode.value);
  const selectedMeeting = selectedSummaryMeeting.value?.id === activeSessionId
    ? selectedSummaryMeeting.value : null;
  const refinementRunning = selectedMeeting?.refinement_state === "running";
  const canNameSpeakers = activeSessionId !== null;
  const legendEntries = buildLegendEntries(
    fullTranscriptItems,
    speakerLabel,
    speakerColorMap
  );
  const correctionSpeakers = legendEntries.filter(
    entry => !isBackendUnknownSpeakerId(entry.speakerId)
  );
  const canCorrectPassages =
    activeSessionId !== null &&
    ["closed", "failed", "aborted"].includes(sessionStatus.value) &&
    !automaticProcessingRunning && !refinementRunning;

  /** Tooltip for a speaker that cannot be named yet; null when naming is available. */
  function namingBlocked(entry: TranscriptLegendEntry | undefined): string | null {
    if (!canNameSpeakers) return "Open a meeting to name speakers";
    if (!entry || isBackendUnknownSpeakerId(entry.speakerId)) return "No identified speaker";
    return entry.committed ? null : "Wait for confirmed speech";
  }

  useEffect(() => {
    setNamingTarget(null);
    setVoiceprintNotice(null);
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
    if (namingBlocked(entry) !== null || !entry) return;
    setNamingError(null);
    setVoiceprintNotice(null);
    setNamingTarget(entry);
    setSpeakerName(entry.visibleLabel);
    setSaveVoiceprint(true);
  }

  async function saveSpeakerName(event: Event): Promise<void> {
    event.preventDefault();
    if (!namingTarget || !activeSessionId || !canNameSpeakers || savingName) return;
    const meetingId = activeSessionId;
    const requestedName = speakerName.trim();
    setSavingName(true);
    setNamingError(null);
    try {
      let result;
      let refused = false;
      try {
        result = await nameMeetingSpeaker(meetingId, namingTarget.speakerId, requestedName, undefined, saveVoiceprint);
      } catch (error) {
        if (!saveVoiceprint || !(error instanceof VoiceprintEvidenceNotAdmittedError) || sessionId.value !== meetingId) throw error;
        refused = true;
        result = await nameMeetingSpeaker(meetingId, namingTarget.speakerId, requestedName, undefined, false);
      }
      if (sessionId.value !== meetingId) return;
      // The response acknowledges a durable display label, not a new identity.
      sessionTranscriptItems.value = sessionTranscriptItems.value.map(item =>
        item.speaker_entity_id === result.speaker_id ? { ...item, display_name: result.label } : item);
      document.dispatchEvent(new CustomEvent(SPEAKER_NAMED_EVENT, { detail: { meetingId } }));
      requestMeetingHistoryRefresh();
      setVoiceprintNotice(refused || result.enrollment === "unavailable" ? VOICEPRINT_NOT_SAVED : null);
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
    if (!correctionTarget || !activeSessionId || savingCorrection || refinementRunning) return;
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
      if (matchesFindShortcut(event) && view.value === "transcript") {
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

  // Every meeting opens following its newest words.
  useEffect(() => {
    autoscroll.value = true;
  }, [activeSessionId]);

  useEffect(() => {
    if (!autoscroll.value || findOpen || view.value !== "transcript") return;
    const frameId = window.requestAnimationFrame(() => {
      const node = transcriptScrollRef.current;
      if (node) node.scrollTop = node.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [autoscroll.value, findOpen, view.value, fullTranscriptItems, provisionalSegments.value]);

  /**
   * Hand Auto-scroll to the reader and back. Only the reader moves the view up while the content
   * keeps its size: growth, bottom clamping on shrink and Chrome's scroll anchoring all change
   * scrollHeight in the same step, so content arriving never turns Auto-scroll off. A move down onto
   * the bottom turns it back on.
   */
  function handleTranscriptScroll(event: JSX.TargetedEvent<HTMLDivElement, Event>) {
    const node = event.currentTarget;
    const previous = lastScroll.current;
    const top = node.scrollTop;
    const height = node.scrollHeight;
    lastScroll.current = { top, height };
    const atBottom = height - top - node.clientHeight <= AUTOSCROLL_BOTTOM_TOLERANCE_PX;
    if (top < previous.top && height === previous.height && !atBottom) autoscroll.value = false;
    else if (top > previous.top && atBottom) autoscroll.value = true;
  }

  function cycleSearchMatch(direction: -1 | 1) {
    if (searchResults.matchCount === 0) {
      return;
    }

    setActiveSearchMatchIndex((current) =>
      (current + direction + searchResults.matchCount) % searchResults.matchCount
    );
  }

  async function handleCopy(): Promise<void> {
    const text = buildTranscriptExportText(allTurns, speakerLabel);
    try {
      await copyTextToClipboard(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
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
            {sessionTitle.value.trim() || "aiSight - LiveTranscribe"}
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
            disabled={namingBlocked(entry) !== null}
            aria-label={`Name speaker ${entry.visibleLabel}`}
            title={namingBlocked(entry) ?? undefined}
            onClick={() => openSpeakerName(entry)}
          >
            <span
              className="legend-chip-dot"
              style={{ "--sp": entry.colorToken } as JSX.CSSProperties}
            />
            <span className="legend-chip-name">{entry.visibleLabel}</span>
          </button>
        ))}

        <div className="tr-legend-right"><div className="seg transcript-tabs" role="tablist" aria-label="Meeting views">
          <button type="button" role="tab" className={`seg-btn${view.value === "transcript" ? " is-active" : ""}`}
            aria-selected={view.value === "transcript"} onClick={() => { view.value = "transcript"; }}>Transcript</button>
          <button type="button" role="tab" className={`seg-btn${view.value === "summary" ? " is-active" : ""}`}
            aria-selected={view.value === "summary"} onClick={() => { view.value = "summary"; }}>Summary</button>
        </div></div>
      </div>

      {voiceprintNotice ? <p className="tr-notice" role="status">{voiceprintNotice}</p> : null}
      {namingTarget ? (
        <dialog ref={namingDialogRef} className="history-dialog" aria-labelledby="speaker-name-title"
          onCancel={() => setNamingTarget(null)}>
          <form onSubmit={(event) => void saveSpeakerName(event)}>
            <h3 id="speaker-name-title">Name speaker</h3>
            <label htmlFor="speaker-name-input">Display name</label>
            <input ref={namingInputRef} id="speaker-name-input" value={speakerName} required
              disabled={savingName} onInput={(event) => setSpeakerName(event.currentTarget.value)} />
            <label className="sp-voiceprint"><input type="checkbox" checked={saveVoiceprint} onChange={event => setSaveVoiceprint(event.currentTarget.checked)} disabled={savingName} /><span>Save voiceprint</span></label>
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

      <div className="tr-body-wrap" hidden={view.value === "summary"}>
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

        <div ref={transcriptScrollRef} className="tr-body" id="tr-body" onScroll={handleTranscriptScroll}>
          {transcriptAvailable ? (
            <TranscriptCards rows={rows} search={searchByTurn} activeMatchId={activeSearchMatchId}
              finalized={finalized} canCorrectPassages={canCorrectPassages} correctionWaiting={refinementRunning}
              speakerColorMap={speakerColorMap} speakerLabel={rowSpeakerLabel} sourceLabel={sourceLabel}
              namingBlocked={(id) => namingBlocked(legendEntries.find(entry => entry.speakerId === id))}
              onSpeakerClick={(id) => openSpeakerName(legendEntries.find(entry => entry.speakerId === id))}
              onPassageCorrection={openPassageCorrection} />
          ) : (
            <p className="empty-state transcript-empty-state">
              Transcript will appear here when a session starts.
            </p>
          )}
        </div>
        <div className="tr-fade" aria-hidden="true" />
      </div>
      <SummaryPane hidden={view.value !== "summary"} />
    </section>
  );
}

function buildLegendEntries(
  items: typeof transcript.value,
  speakerLabel: (item: typeof transcript.value[number]) => string,
  speakerColorMap: ReadonlyMap<string, string>
): TranscriptLegendEntry[] {
  const entries = new Map<string, TranscriptLegendEntry>();

  for (const item of items) {
    // UNKNOWN is the transient legacy preview and has no legend entry. Saved S00
    // remains visible as a disabled unidentified legend, but never a correction target.
    if (item.speaker === "UNKNOWN") {
      continue;
    }

    const visibleLabel = speakerLabel(item);
    const legendKey = buildSpeakerLegendKey(item.speaker_entity_id, visibleLabel);
    if (!entries.has(legendKey)) {
      entries.set(legendKey, {
        legendKey,
        visibleLabel,
        speakerId: item.speaker_entity_id,
        committed: item.state !== "provisional",
        isUnidentified: isBackendUnknownSpeakerId(item.speaker_entity_id),
        colorToken: resolveSpeakerColorToken(item.speaker_entity_id, speakerColorMap)
      });
    } else if (item.state !== "provisional") {
      entries.get(legendKey)!.committed = true;
    }
  }

  return [...entries.values()];
}
