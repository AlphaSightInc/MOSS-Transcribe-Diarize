import { useEffect, useRef, useState } from "preact/hooks";
import { createFileJobPoller, submitJob, type FileJobPoller } from "../api/jobs";
import { resetSessionState } from "../state/session";

interface FilePanelProps {
  captureBearer: string;
}

export function FilePanel({ captureBearer }: FilePanelProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [message, setMessage] = useState("Select an audio or video file to transcribe.");
  const [progress, setProgress] = useState(0);
  const [running, setRunning] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const pollerRef = useRef<FileJobPoller | null>(null);

  useEffect(() => () => pollerRef.current?.stop(), []);

  async function startJob(): Promise<void> {
    if (!selectedFile || running) return;
    pollerRef.current?.stop();
    resetSessionState();
    setRunning(true);
    setProgress(0);
    setMessage("Uploading file...");
    try {
      const options = { bearerToken: captureBearer.trim() };
      const created = await submitJob(selectedFile, {
        ...options,
        onUploadProgress({ loaded, total }) {
          setProgress(loaded / total);
          setMessage(`Uploading file: ${loaded} / ${total} bytes.`);
        }
      });
      setMessage("Queued for transcription.");
      const poller = createFileJobPoller({
        jobId: created.id,
        ...options,
        onProgress(job) {
          setProgress(job.progress);
          setMessage(job.error ?? job.status.replaceAll("_", " "));
        },
        onError(error) {
          setMessage(`Connection interrupted while checking transcription; retrying: ${error}`);
        },
        onTerminal(job) {
          setRunning(false);
          setProgress(job.progress);
          setMessage(job.error ?? (job.status === "waiting_review" || job.status === "done"
            ? "Transcript ready."
            : job.status.replaceAll("_", " ")));
        }
      });
      pollerRef.current = poller;
      poller.start();
    } catch (error) {
      setRunning(false);
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    }
  }

  return (
    <section className="control-section file-supervisor" data-mode="file">
      <div className="label">File</div>
      <div className="field field--input-prompt">
        <input
          aria-label="Selected file"
          readOnly
          type="text"
          value={selectedFile?.name ?? ""}
          placeholder="No file selected."
        />
        <button
          type="button"
          className="field-btn"
          aria-label="Choose file"
          title="Choose file"
          disabled={running}
          onClick={() => inputRef.current?.click()}
        >
          <span aria-hidden="true">↑</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="audio/*,video/*"
          hidden
          disabled={running}
          onChange={(event) => {
            const file = event.currentTarget.files?.[0] ?? null;
            setSelectedFile(file);
            setMessage(file ? `Ready to upload ${file.name}.` : "Select an audio or video file to transcribe.");
          }}
        />
      </div>
      <button
        type="button"
        className="record-btn"
        disabled={!selectedFile || running}
        onClick={() => void startJob()}
      >
        <span>{running ? "Transcribing..." : "Start transcription"}</span>
      </button>
      <div className="progress file-progress" aria-label={`File transcription ${Math.round(progress * 100)}%`}>
        <div className="bar" style={{ width: `${Math.max(0, Math.min(100, progress * 100))}%` }} />
      </div>
      <p className="capture-status" role="status">{message}</p>
      <p className="capture-status">Failed uploads restart from the beginning; upload resume is unavailable in Phase 1.</p>
    </section>
  );
}
