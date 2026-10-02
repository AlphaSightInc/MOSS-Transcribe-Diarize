import { type JSX } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import "../styles/transcript.css";
import { requestMeetingHistoryRefresh, SPEAKER_NAMED_EVENT } from "../lib/meetingEvents";
import { editMeetingPassageText, nameMeetingSpeaker, reassignMeetingPassages, VoiceprintEvidenceNotAdmittedError } from "../api/speakers";
import {
  buildTranscriptExportText
} from "../lib/transcriptExport";
import { groupSegmentsIntoTurns, type TranscriptTurn } from "../lib/mergeTranscript";
import {
  buildSpeakerLegendKey,
  isBackendUnknownSpeakerId,
  speakerColorToken
} from "../lib/speakerMap";
import { buildTranscriptSearchResults } from "../lib/transcriptSearch";
import {
  defaultSpeakerLabel,
  projectTranscriptRows,
  transcriptCardSpeakerLabel
} from "../lib/transcriptCards";
import { recallCaptureSurface, transcriptSourceLabel } from "../lib/captureSurface";
import {
  recordingInterruptions,
  sessionId,
  sessionNeedsReview,
  provisionalSegments,
  sessionMode,
  sessionStatus,
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
  speakerId: string;
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
  const correctionControlRef = useRef<HTMLButtonElement | null>(null);
  const correctionListRef = useRef<HTMLDivElement | null>(null);
  const correctionNameRef = useRef<HTMLInputElement | null>(null);
  const [correctionListOpen, setCorrectionListOpen] = useState(false);
  const [correctionActiveIndex, setCorrectionActiveIndex] = useState(0);

  const [textEditor, setTextEditor] = useState<{ meetingId: string; passageId: string; original: string; text: string; trigger: HTMLElement | null } | null>(null);
  const textEditorRef = useRef(textEditor);
  textEditorRef.current = textEditor;
  const textSaveRef = useRef<Promise<boolean> | null>(null);
  const [savingText, setSavingText] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const textAreaRef = useRef<HTMLTextAreaElement | null>(null);
  const textContainerRef = useRef<HTMLDivElement | null>(null);

  const fullTranscriptItems = transcript.value;
  const searchQuery = transcriptSearchQuery.value.trim();
  const allTurns = groupSegmentsIntoTurns(fullTranscriptItems, {
    interruptions: recordingInterruptions.value,
    preservePassages: ["closed", "failed", "aborted"].includes(sessionStatus.value) && fullTranscriptItems.every(item => item.state === "final")
  });
  const guessedSpeakerIds = [...new Set(provisionalSegments.value.flatMap(segment =>
    segment.tentative_speaker ? [segment.tentative_speaker] : []))];
  const automaticProcessingRunning =
    sessionStatus.value === "active" ||
    sessionStatus.value === "closing" ||
    (sessionStatus.value === "closed" && allTurns.some(turn => turn.state !== "final"));
  const finalized = !automaticProcessingRunning;
  const speakerLabel = transcriptCardSpeakerLabel;
  const speakerLabels: Record<string, string> = {};
  for (const item of fullTranscriptItems) speakerLabels[item.speaker_entity_id] = speakerLabel(item);
  for (const id of guessedSpeakerIds) speakerLabels[id] ??= defaultSpeakerLabel(id);
  const tentativeBlocks = projectTentativeSegments(provisionalSegments.value, speakerLabels);
  // Guesses replace the transcript's own preview rows; both describe the same preview words.
  const displayedTurns = tentativeBlocks.length
    ? allTurns.filter(turn => turn.state !== "provisional") : allTurns;
  const guessTurns = tentativeTurns(tentativeBlocks);
  const guesses = new Set(guessTurns);
  const rowSpeakerLabel = (turn: TranscriptTurn) => guesses.has(turn) ? turn.display_name : speakerLabel(turn);
  const rows = projectTranscriptRows(displayedTurns, guessTurns, recordingInterruptions.value);
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
  const transcriptAvailable = rows.length > 0 || recordingInterruptions.value.some(gap => gap.end !== null);
  const activeSessionId = sessionId.value;
  const captureSurface = activeSessionId ? recallCaptureSurface(activeSessionId) : null;
  const sourceLabel = (lane: string | undefined) => transcriptSourceLabel(lane, captureSurface, sessionMode.value);
  const selectedMeeting = selectedSummaryMeeting.value?.id === activeSessionId
    ? selectedSummaryMeeting.value : null;
  const refinementRunning = selectedMeeting?.refinement_state === "running";
  const canNameSpeakers = activeSessionId !== null;
  const legendEntries = buildLegendEntries(fullTranscriptItems, speakerLabel);
  const correctionSpeakers = legendEntries.filter(
    entry => !isBackendUnknownSpeakerId(entry.speakerId) && entry.speakerId !== correctionTarget?.speakerId
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

  useLayoutEffect(() => {
    setCorrectionTarget(null);
    setCorrectionError(null);
    setTextEditor(null);
    setTextError(null);
  }, [activeSessionId]);

  useLayoutEffect(() => {
    if (!namingTarget) return;
    const dialog = namingDialogRef.current;
    if (!dialog) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    if (correctionTarget && canCorrectPassages) {
      if (correctionListOpen) correctionNameRef.current?.focus();
      else correctionControlRef.current?.focus();
    } else {
      namingInputRef.current?.focus();
      namingInputRef.current?.select();
    }
    return () => {
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      previousFocus?.focus();
    };
  }, [namingTarget]);

  useLayoutEffect(() => {
    if (!correctionTarget || !correctionListOpen) return;
    const options = correctionListRef.current?.querySelectorAll<HTMLElement>('[role="option"]');
    if (correctionActiveIndex === correctionSpeakers.length) correctionNameRef.current?.focus();
    else options?.[correctionActiveIndex]?.focus();
  }, [correctionTarget, correctionListOpen, correctionActiveIndex]);

  function closeCorrectionList(): void {
    setCorrectionListOpen(false);
    correctionControlRef.current?.focus();
  }

  function correctionKeyDown(event: JSX.TargetedKeyboardEvent<HTMLElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (correctionListOpen) closeCorrectionList();
      else closeSpeakerPopup();
    } else if ((event.key === "ArrowDown" || event.key === "ArrowUp") &&
      (event.target as HTMLElement).closest(".passage-choice")) {
      event.preventDefault();
      const count = correctionSpeakers.length + 1;
      setCorrectionActiveIndex(correctionListOpen
        ? (correctionActiveIndex + (event.key === "ArrowDown" ? 1 : -1) + count) % count
        : event.key === "ArrowDown" ? 0 : count - 1);
      setCorrectionListOpen(true);
    }
  }

  function closeSpeakerPopup(): void {
    if (savingName || savingCorrection) return;
    setNamingTarget(null);
    setCorrectionTarget(null);
    setCorrectionListOpen(false);
  }

  function openSpeakerName(entry: TranscriptLegendEntry | undefined, passageIds: string[] = []): void {
    if (!entry || (namingBlocked(entry) !== null && !(canCorrectPassages && passageIds.length))) return;
    setNamingError(null);
    setVoiceprintNotice(null);
    setNamingTarget(entry);
    setSpeakerName(entry.visibleLabel);
    setSaveVoiceprint(true);
    setCorrectionTarget({ meetingId: activeSessionId!, passageIds, speakerId: entry.speakerId });
    setCorrectionMode("new");
    setCorrectionSpeakerId("");
    setCorrectionListOpen(canCorrectPassages && !legendEntries.some(other => other.speakerId !== entry.speakerId && !other.isUnidentified));
    setCorrectionActiveIndex(0);
    setCorrectionName("");
    setCorrectionError(null);
  }

  async function saveSpeakerName(event: Event): Promise<void> {
    event.preventDefault();
    if (!namingTarget || !activeSessionId || !canNameSpeakers || savingName || savingCorrection || namingTarget.isUnidentified || !speakerName.trim()) return;
    const meetingId = activeSessionId;
    const requestedName = speakerName.trim();
    setSavingName(true);
    setNamingError(null);
    try {
      let refused = false;
      let unavailable = false;
      const targets = [namingTarget, ...legendEntries.filter(entry =>
        entry.visibleLabel === namingTarget.visibleLabel && entry.speakerId !== namingTarget.speakerId && !entry.isUnidentified)];
      for (const target of targets) {
        if (sessionId.value !== meetingId) return;
        const enroll = saveVoiceprint && target.speakerId === namingTarget.speakerId;
        let result;
        try {
          result = await nameMeetingSpeaker(meetingId, target.speakerId, requestedName, undefined, enroll);
        } catch (error) {
          if (!enroll || !(error instanceof VoiceprintEvidenceNotAdmittedError) || sessionId.value !== meetingId) throw error;
          refused = true;
          result = await nameMeetingSpeaker(meetingId, target.speakerId, requestedName, undefined, false);
        }
        if (sessionId.value !== meetingId) return;
        unavailable ||= enroll && result.enrollment === "unavailable";
        sessionTranscriptItems.value = sessionTranscriptItems.value.map(item =>
          item.speaker_entity_id === result.speaker_id ? { ...item, display_name: result.label } : item);
        // Each acknowledged change must be visible even if a later matching id fails.
        document.dispatchEvent(new CustomEvent(SPEAKER_NAMED_EVENT, { detail: { meetingId } }));
        requestMeetingHistoryRefresh();
      }
      setVoiceprintNotice(refused || unavailable ? VOICEPRINT_NOT_SAVED : null);
      setNamingTarget(null);
      setCorrectionTarget(null);
    } catch (error) {
      if (sessionId.value === meetingId) {
        setNamingError(error instanceof Error ? error.message : "Speaker naming failed.");
      }
    } finally {
      setSavingName(false);
    }
  }

  async function savePassageCorrection(event: Event): Promise<void> {
    event.preventDefault();
    if (!correctionTarget || !activeSessionId || savingCorrection || savingName || !canCorrectPassages || !correctionTarget.passageIds.length) return;
    if (correctionMode === "existing" ? !correctionSpeakerId : !correctionName.trim()) return;
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
      setNamingTarget(null);
    } catch (error) {
      if (sessionId.value === meetingId) {
        setCorrectionError(error instanceof Error ? error.message : "Passage correction failed.");
      }
    } finally {
      setSavingCorrection(false);
    }
  }

  function closeTextEditor(): void {
    const editor = textEditorRef.current;
    if (textSaveRef.current) return;
    textEditorRef.current = null;
    setTextEditor(null);
    setTextError(null);
    editor?.trigger?.focus();
  }

  function saveTextEditor(): Promise<boolean> {
    if (textSaveRef.current) return textSaveRef.current;
    const editor = textEditorRef.current;
    if (!editor) return Promise.resolve(true);
    const text = editor.text.trim();
    if (!text || text.length > 5000) return Promise.resolve(false);
    if (text === editor.original) { closeTextEditor(); return Promise.resolve(true); }
    setSavingText(true);
    setTextError(null);
    const pending = (async () => {
      try {
        const result = await editMeetingPassageText(editor.meetingId, editor.passageId, text);
        if (sessionId.value !== editor.meetingId) return false;
        sessionTranscriptItems.value = sessionTranscriptItems.value.map(item => item.segment_id === editor.passageId
          ? { ...item, text, edited: true, original_text: item.original_text ?? item.text } : item);
        sessionNeedsReview.value = result.needs_review;
        requestMeetingHistoryRefresh();
        textEditorRef.current = null;
        setTextEditor(null);
        editor.trigger?.focus();
        return true;
      } catch (error) {
        if (sessionId.value === editor.meetingId) setTextError(error instanceof Error ? error.message : "Text edit failed.");
        return false;
      } finally {
        textSaveRef.current = null;
        setSavingText(false);
      }
    })();
    textSaveRef.current = pending;
    return pending;
  }

  async function openTextEditor(turn: TranscriptTurn, trigger: HTMLElement): Promise<void> {
    if (!canCorrectPassages || turn.segment_ids.length !== 1) return;
    const meetingId = activeSessionId!;
    if (textEditorRef.current?.passageId === turn.segment_ids[0]) return;
    if (textEditorRef.current && !(await saveTextEditor())) return;
    if (sessionId.value !== meetingId) return;
    const editor = { meetingId, passageId: turn.segment_ids[0], original: turn.text, text: turn.text, trigger };
    textEditorRef.current = editor;
    setTextEditor(editor);
    setTextError(null);
  }

  useLayoutEffect(() => {
    if (!textEditor) return;
    const input = textAreaRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${input.scrollHeight}px`;
  }, [textEditor?.text]);

  useLayoutEffect(() => {
    const input = textAreaRef.current;
    if (!textEditor || !input) return;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }, [textEditor?.passageId]);

  useEffect(() => {
    if (!textEditor) return;
    const outside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!textContainerRef.current?.contains(target) && !target.closest?.("[data-edit-passage]")) void saveTextEditor();
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [textEditor]);

  function renderTextEditor(turn: TranscriptTurn): JSX.Element | null {
    if (!textEditor || turn.segment_ids[0] !== textEditor.passageId) return null;
    const empty = !textEditor.text.trim();
    return <div className="text-editor" ref={textContainerRef} onBlurCapture={event => {
      const next = event.relatedTarget as HTMLElement | null;
      if (next && !event.currentTarget.contains(next) && !next.closest("[data-edit-passage]")) void saveTextEditor();
    }}>
      <textarea ref={textAreaRef} aria-label="Section text" value={textEditor.text} disabled={savingText} maxLength={5000}
        onInput={event => {
          const editor = { ...textEditor, text: event.currentTarget.value };
          textEditorRef.current = editor;
          setTextEditor(editor);
        }} onKeyDown={event => {
          if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeTextEditor(); }
          else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); void saveTextEditor(); }
        }} />
      {empty ? <p className="hint">Text cannot be empty.</p> : null}
      {textError ? <p role="alert">{textError}</p> : null}
      <div className="text-editor-actions">
        <button type="button" className="history-toolbar-btn is-primary" disabled={savingText || empty}
          onClick={() => void saveTextEditor()}>{savingText ? "Saving…" : "Save"}</button>
        <button type="button" className="history-toolbar-btn" disabled={savingText} onClick={closeTextEditor}>Cancel</button>
      </div>
    </div>;
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
    const text = buildTranscriptExportText(allTurns, speakerLabel, recordingInterruptions.value);
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
      {/* #9: no title row -- the card starts at the speaker legend, leaving the height to the transcript.
          The meeting title stays on its History card and in the top-bar title pill below desktop width. */}
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
        <dialog ref={namingDialogRef} className="history-dialog passage-dialog speaker-dialog" aria-labelledby="speaker-name-title"
          onKeyDown={correctionKeyDown} onCancel={event => { event.preventDefault(); closeSpeakerPopup(); }}
          onClick={event => { if (event.target === event.currentTarget) {
            const rect = event.currentTarget.getBoundingClientRect();
            if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeSpeakerPopup();
          } }}>
          <div className="speaker-dialog-title"><h3 id="speaker-name-title">Speaker</h3>
            <button type="button" className="history-toolbar-btn" aria-label="Close Speaker" disabled={savingName || savingCorrection} onClick={closeSpeakerPopup}>×</button></div>
          <form className="speaker-assignment-form" onSubmit={(event) => void savePassageCorrection(event)}>
            <h4>This Section Only</h4>
            {!canCorrectPassages ? <p className="hint">Available after the recording stops.</p> : null}
            {canCorrectPassages && !correctionTarget?.passageIds.length ? <p className="hint">Choose a section’s speaker name to assign it.</p> : null}
            <fieldset disabled={!canCorrectPassages || !correctionTarget?.passageIds.length || savingCorrection || savingName}>
            <div className="passage-choice" onBlur={event => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setCorrectionListOpen(false);
            }}>
              <button ref={correctionControlRef} type="button" className="passage-choice-control"
                role="combobox" aria-label="Speaker" aria-haspopup="listbox"
                aria-expanded={correctionListOpen} aria-controls="passage-speaker-list" disabled={savingCorrection}
                onClick={() => {
                  setCorrectionActiveIndex(correctionMode === "existing"
                    ? correctionSpeakers.findIndex(entry => entry.speakerId === correctionSpeakerId) : correctionSpeakers.length);
                  setCorrectionListOpen(!correctionListOpen);
                }}>
                <span>{correctionMode === "existing"
                  ? correctionSpeakers.find(entry => entry.speakerId === correctionSpeakerId)?.visibleLabel
                  : correctionName.trim() || "New Speaker"}</span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
              </button>
              {correctionListOpen ? (
                <div ref={correctionListRef} id="passage-speaker-list" className="passage-choice-list"
                  role="listbox" aria-label="Speaker">
                  {correctionSpeakers.map((entry, index) => (
                    <div key={entry.speakerId} role="option" tabIndex={-1} className="passage-choice-option"
                      data-speaker-id={entry.speakerId}
                      aria-selected={correctionMode === "existing" && correctionSpeakerId === entry.speakerId}
                      onFocus={() => setCorrectionActiveIndex(index)}
                      onClick={() => {
                        setCorrectionMode("existing"); setCorrectionSpeakerId(entry.speakerId); closeCorrectionList();
                      }} onKeyDown={event => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault(); event.currentTarget.click();
                        }
                      }}>
                      <span className="legend-chip-dot" style={{ "--sp": entry.colorToken } as JSX.CSSProperties} />
                      <span>{entry.visibleLabel}</span>
                    </div>
                  ))}
                  <div role="option" className="passage-choice-option passage-choice-new" aria-label="New Speaker"
                    aria-selected={correctionMode === "new"} onClick={() => correctionNameRef.current?.focus()}>
                    <input ref={correctionNameRef} aria-label="New Speaker" placeholder="New Speaker" value={correctionName}
                      disabled={savingCorrection} onFocus={() => {
                        setCorrectionMode("new"); setCorrectionActiveIndex(correctionSpeakers.length);
                      }} onInput={event => setCorrectionName(event.currentTarget.value)}
                      onKeyDown={event => {
                        if (event.key === "Enter") { event.preventDefault(); closeCorrectionList(); }
                      }} />
                  </div>
                </div>
              ) : null}
            </div>
            {correctionError ? <p role="alert">{correctionError}</p> : null}
            <div className="history-dialog-actions">
              <button className="history-toolbar-btn" type="submit" disabled={savingCorrection ||
                (correctionMode === "existing" ? !correctionSpeakerId : !correctionName.trim())}>
                {savingCorrection ? "Saving…" : "Assign This Section"}
              </button>
            </div>
            </fieldset>
          </form>
          <form className="speaker-rename-form" onSubmit={(event) => void saveSpeakerName(event)}>
            <h4>All Sections Named “{namingTarget.visibleLabel}”</h4>
            <fieldset disabled={namingTarget.isUnidentified || savingName || savingCorrection}>
            <label htmlFor="speaker-name-input">Display name</label>
            <input ref={namingInputRef} id="speaker-name-input" value={speakerName} required
              disabled={savingName} onInput={(event) => setSpeakerName(event.currentTarget.value)} />
            <label className="sp-voiceprint"><input type="checkbox" checked={saveVoiceprint} onChange={event => setSaveVoiceprint(event.currentTarget.checked)} disabled={savingName} /><span>Save voiceprint</span></label>
            {namingError ? <p role="alert">{namingError}</p> : null}
            <div className="history-dialog-actions">
              <button className="history-toolbar-btn" type="button" disabled={savingName} onClick={closeSpeakerPopup}>Cancel</button>
              <button className="history-toolbar-btn" type="submit" disabled={savingName || !speakerName.trim()}>{savingName ? "Saving…" : "Rename All"}</button>
            </div>
            </fieldset>
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
            <TranscriptCards rows={rows} interruptions={recordingInterruptions.value} search={searchByTurn} activeMatchId={activeSearchMatchId}
              finalized={finalized} canCorrectPassages={canCorrectPassages} correctionWaiting={refinementRunning}
              speakerLabel={rowSpeakerLabel} sourceLabel={sourceLabel}
              namingBlocked={(id) => canCorrectPassages ? null : namingBlocked(legendEntries.find(entry => entry.speakerId === id))}
              onSpeakerClick={(id, ids) => openSpeakerName(legendEntries.find(entry => entry.speakerId === id), ids)}
              onTextEdit={(turn, trigger) => void openTextEditor(turn, trigger)} renderTextEditor={renderTextEditor} />
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
  speakerLabel: (item: typeof transcript.value[number]) => string
): TranscriptLegendEntry[] {
  const entries = new Map<string, TranscriptLegendEntry>();

  for (const item of items) {
    // Transient UNKNOWN previews have no legend entry. Persisted unknowns can be
    // assigned from their section, but never named or offered as an existing speaker.
    if (item.speaker === "UNKNOWN" && item.state === "provisional") {
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
        colorToken: speakerColorToken(item.speaker_entity_id)
      });
    } else if (item.state !== "provisional") {
      entries.get(legendKey)!.committed = true;
    }
  }

  return [...entries.values()];
}
