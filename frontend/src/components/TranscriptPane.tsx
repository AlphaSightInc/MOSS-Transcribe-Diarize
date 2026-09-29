import { type JSX } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
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
import { isSettledTurn, settledSpeakerNumbers, transcriptCardSpeakerLabel } from "../lib/transcriptCards";
import {
  liveLabelPolicy,
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
import { projectTentativeSegments } from "../lib/tentative";
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
  const speakerColorMap = buildSpeakerColorMap(fullTranscriptItems);
  const allTurns = groupSegmentsIntoTurns(fullTranscriptItems);
  const automaticProcessingRunning =
    sessionStatus.value === "active" ||
    sessionStatus.value === "closing" ||
    (sessionStatus.value === "closed" && allTurns.some(turn => turn.state !== "final"));
  const finalized = !automaticProcessingRunning;
  const speakerNumbers = settledSpeakerNumbers(allTurns, finalized);
  const speakerLabel = (item: Pick<typeof transcript.value[number], "speaker_entity_id" | "speaker" | "display_name" | "source_lane" | "settled" | "state">) => {
    const id = item.speaker_entity_id || item.speaker;
    if (/^local-\d+$/.test(id) && (!item.display_name || item.display_name === id || /^Speaker \d+$/.test(item.display_name))) {
      return `Local ${String(Number(id.slice(6))).padStart(2, "0")}`;
    }
    return transcriptCardSpeakerLabel(item, speakerNumbers, liveLabelPolicy.value, finalized);
  };
  const searchResults = buildTranscriptSearchResults(
    allTurns,
    searchQuery,
    speakerLabel
  );
  const activeSearchMatchId =
    searchResults.matchCount > 0
      ? Math.min(activeSearchMatchIndex, searchResults.matchCount - 1)
      : -1;
  const speakerLabels: Record<string, string> = {};
  for (const item of fullTranscriptItems) speakerLabels[item.speaker_entity_id] = speakerLabel(item);
  for (const segment of provisionalSegments.value) {
    const id = segment.tentative_speaker;
    if (!id || speakerLabels[id]) continue;
    const numberedSpeaker = /^speaker-(\d+)$/.exec(id);
    speakerLabels[id] = /^local-\d+$/.test(id)
      ? `Local ${String(Number(id.slice(6))).padStart(2, "0")}`
      : numberedSpeaker ? `S${String(Number(numberedSpeaker[1])).padStart(2, "0")}`
      : "Speaker TBD";
  }
  const tentativeBlocks = projectTentativeSegments(provisionalSegments.value, speakerLabels);
  const transcriptAvailable = allTurns.length > 0 || tentativeBlocks.length > 0;
  const activeSessionId = sessionId.value;
  const selectedMeeting = selectedSummaryMeeting.value?.id === activeSessionId
    ? selectedSummaryMeeting.value : null;
  const refinementState = selectedMeeting?.refinement_state;
  const refinementRunning = refinementState === "running";
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
  const settlingVisible = transcriptAvailable && !finalized &&
    allTurns.some(turn => !isSettledTurn(turn, finalized));

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
    const requestedName = speakerName.trim();
    setSavingName(true);
    setNamingError(null);
    try {
      let result;
      let refusalMessage: string | null = null;
      try {
        result = await nameMeetingSpeaker(meetingId, namingTarget.speakerId, requestedName, undefined, saveVoiceprint);
      } catch (error) {
        if (!saveVoiceprint || !(error instanceof VoiceprintEvidenceNotAdmittedError) || sessionId.value !== meetingId) throw error;
        refusalMessage = error.message;
        result = await nameMeetingSpeaker(meetingId, namingTarget.speakerId, requestedName, undefined, false);
      }
      if (sessionId.value !== meetingId) return;
      // The response acknowledges a durable display label, not a new identity.
      sessionTranscriptItems.value = sessionTranscriptItems.value.map(item =>
        item.speaker_entity_id === result.speaker_id ? { ...item, display_name: result.label } : item);
      document.dispatchEvent(new CustomEvent(SPEAKER_NAMED_EVENT, { detail: { meetingId } }));
      requestMeetingHistoryRefresh();
      setNamingMessage(refusalMessage
        ? `Saved ${result.label}. Voiceprint not saved. ${refusalMessage}`
        : result.enrollment === "not_requested"
        ? `Saved ${result.label}. Voiceprint not saved.`
        : result.enrollment === "unavailable"
        ? `Saved ${result.label}. Voiceprint not saved: eligible audio was unavailable for this speaker.`
        : result.enrollment === "enrolled"
        ? `Saved ${result.label}. Voiceprint saved privately in this browser workspace.`
        : `Saved ${result.label}. Voiceprint will be saved after recording finishes if eligible audio is available.`);
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

  useEffect(() => {
    if (activeSessionId && sessionMode.value === "live" && sessionStatus.value === "active") {
      autoscroll.value = true;
    }
  }, [activeSessionId]);

  useEffect(() => {
    if (!autoscroll.value || findOpen) return;
    const frameId = window.requestAnimationFrame(() => {
      const node = transcriptScrollRef.current;
      if (node) node.scrollTop = node.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [autoscroll.value, findOpen, fullTranscriptItems]);

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

        <div className="tr-legend-right"><div className="seg transcript-tabs" role="tablist" aria-label="Meeting views">
          <button type="button" role="tab" className={`seg-btn${view.value === "transcript" ? " is-active" : ""}`}
            aria-selected={view.value === "transcript"} onClick={() => { view.value = "transcript"; }}>Transcript</button>
          <button type="button" role="tab" className={`seg-btn${view.value === "summary" ? " is-active" : ""}`}
            aria-selected={view.value === "summary"} onClick={() => { view.value = "summary"; }}>Summary</button>
        </div></div>
      </div>

      {refinementRunning ? <p className="transcript-refinement" role="status"><strong>Improving transcript…</strong> Passage corrections wait until improvement finishes.</p>
        : refinementState === "done" ? <p className="transcript-refinement" role="status">Transcript improved</p>
        : refinementState === "failed" ? <p className="transcript-refinement" role="status">{selectedMeeting?.notice || "Improvement unavailable — the live transcript was kept"}</p> : null}

      {namingMessage ? <p className="hint" role="status">{namingMessage}</p> : null}
      {sessionNeedsReview.value ? <p className="hint" role="status"><strong>Needs review.</strong> Check passages marked Speaker TBD or a partial processing notice.</p> : null}
      {namingTarget ? (
        <dialog ref={namingDialogRef} className="history-dialog" aria-labelledby="speaker-name-title"
          onCancel={() => setNamingTarget(null)}>
          <form onSubmit={(event) => void saveSpeakerName(event)}>
            <h3 id="speaker-name-title">Name speaker</h3>
            <label htmlFor="speaker-name-input">Display name</label>
            <input ref={namingInputRef} id="speaker-name-input" value={speakerName} required
              disabled={savingName} onInput={(event) => setSpeakerName(event.currentTarget.value)} />
            <label className="sp-voiceprint"><input type="checkbox" checked={saveVoiceprint} onChange={event => setSaveVoiceprint(event.currentTarget.checked)} disabled={savingName} /><span>Save voiceprint</span></label>
            <p className="hint">Applies to this speaker throughout this meeting. Saving a private voiceprint needs at least 2 seconds of finished, clear speech; speech still being reviewed does not count. People may share the same name.</p>
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

        {settlingVisible ? <p className="transcript-settling-hint" data-settling-hint="true">
          Identity settling. Live labels may change as speech is reviewed.
        </p> : null}
        <div ref={transcriptScrollRef} className="tr-body" id="tr-body">
          {transcriptAvailable ? (
            <TranscriptCards searchTurns={tentativeBlocks.length ? searchResults.turns.filter(item => item.turn.state !== "provisional") : searchResults.turns} activeMatchId={activeSearchMatchId}
              finalized={finalized} canCorrectPassages={canCorrectPassages} correctionWaiting={refinementRunning}
              speakerColorMap={speakerColorMap}
              onSpeakerClick={(id) => openSpeakerName(legendEntries.find(entry => entry.speakerId === id))}
              onPassageCorrection={openPassageCorrection} />
          ) : null}
          <div className="transcript-cards" data-tentative-blocks="true">{tentativeBlocks.map((block, index) => <article key={`${block.lane}:${block.start}:${index}`}
            className="utt transcript-card tentative-card" data-tentative-block="true" data-state="provisional"
            data-source-lane={block.lane} data-turn-start={block.start} data-turn-end={block.end}
            data-target-keys={`tentative:${block.lane}:${block.start}`} data-segments={JSON.stringify([{ start: block.start, end: block.end, text: block.text }])}>
            <div className="utt-meta"><span className="utt-speaker" data-speaker-id={block.speakerId ?? "S00"}>
              <span className="utt-speaker-label">{block.label}</span></span>
              <span className="utt-lane">{block.lane === "microphone" ? "Microphone" : block.lane === "system" ? "Shared audio" : block.lane}</span></div>
            <div className="transcript-card-fragments"><div className="utt-content" data-text-status="unsettled"><p className="utt-text">{block.text}</p></div></div>
          </article>)}</div>
          {!transcriptAvailable ? (
            <p className="empty-state transcript-empty-state">
              Transcript will appear here when a session starts.
            </p>
          ) : null}
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
        colorToken: resolveSpeakerColorToken(item.speaker, speakerColorMap)
      });
    } else if (item.state !== "provisional") {
      entries.get(legendKey)!.committed = true;
    }
  }

  return [...entries.values()];
}
