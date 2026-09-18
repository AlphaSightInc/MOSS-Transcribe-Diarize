import { openMeeting } from "../api/meetings";
import { OPEN_MEETING_EVENT, requestMeetingHistoryRefresh } from "./meetingEvents";
import { MEETING_CREATED } from "./finalSummary";

/** The existing account upload form, with per-item server outcomes. */
export function bindFileUpload(): () => void {
  const form = document.querySelector<HTMLFormElement>('[data-file-upload="form"]');
  const status = document.querySelector<HTMLElement>('[data-file-upload="status"]');
  const results = document.querySelector<HTMLElement>('[data-file-upload="results"]');
  if (!form || !status || !results) return () => {};
  const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  let disposed = false;
  let generation = 0;
  const timers = new Set<ReturnType<typeof setTimeout>>();
  const clearTimers = () => { for (const timer of timers) clearTimeout(timer); timers.clear(); };

  function follow(id: string, message: HTMLElement, current: number) {
    const refresh = async () => {
      try {
        const meeting = await openMeeting(id);
        if (disposed || current !== generation) return;
        message.textContent = meeting.status === "active" ? "Processing on the server…"
          : meeting.status === "completed" ? "Completed — ready to open."
          : meeting.status === "failed" ? meeting.failure_reason || "Processing failed. Open the meeting to inspect its saved result."
          : "Processing interrupted. Open the meeting to inspect its saved result.";
        if (meeting.status !== "active") { requestMeetingHistoryRefresh(); return; }
        const timer = setTimeout(() => { timers.delete(timer); void refresh(); }, 1500);
        timers.add(timer);
      } catch {
        if (!disposed && current === generation) message.textContent = "Accepted; current status unavailable. Open the meeting or refresh history to check.";
      }
    };
    void refresh();
  }

  const send = async (label: string, path: string, options: RequestInit, current: number): Promise<boolean> => {
    const row = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = label;
    const message = document.createElement("span");
    message.textContent = "Submitting…";
    row.append(name, document.createTextNode(" — "), message);
    results.append(row);
    try {
      const response = await fetch(path, options);
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = typeof payload?.detail === "string" ? payload.detail : `Request failed (${response.status}).`;
        message.textContent = `Not accepted: ${detail} Check this item before submitting it again.`;
        return false;
      }
      if (typeof payload?.id !== "string" || !payload.id) throw new Error("Missing meeting ID");
      message.textContent = "Accepted — checking processing status…";
      const open = document.createElement("button");
      open.type = "button";
      open.className = "history-action-btn";
      open.textContent = "Open meeting";
      open.setAttribute("aria-label", `Open meeting for ${label}`);
      open.addEventListener("click", () => document.dispatchEvent(new CustomEvent(OPEN_MEETING_EVENT, { detail: { meetingId: payload.id } })));
      row.append(document.createTextNode(" "), open);
      document.dispatchEvent(new CustomEvent(MEETING_CREATED, { detail: { meeting_id: payload.id } }));
      requestMeetingHistoryRefresh();
      follow(payload.id, message, current);
      return true;
    } catch {
      message.textContent = "Submission could not be confirmed. Check your connection and meeting history before retrying.";
      return false;
    }
  };

  const onSubmit = async (event: Event) => {
    event.preventDefault();
    if (submit.disabled) return;
    const files = Array.from(form.querySelector<HTMLInputElement>('input[name="file"]')!.files ?? []);
    const urls = form.querySelector<HTMLTextAreaElement>('textarea[name="urls"]')!.value
      .split(/\r?\n/).map(value => value.trim()).filter(Boolean);
    if (!files.length && !urls.length) { status.textContent = "Choose a file or enter a media URL first."; return; }
    const current = ++generation;
    clearTimers(); results.replaceChildren(); submit.disabled = true;
    let accepted = 0, failed = 0;
    try {
      for (const file of files) {
        status.textContent = `Submitting ${accepted + failed + 1} of ${files.length + urls.length}…`;
        const body = new FormData(); body.append("file", file, file.name);
        (await send(file.name, "/api/meetings/file", { method: "POST", body }, current)) ? accepted++ : failed++;
      }
      for (const url of urls) {
        status.textContent = `Submitting ${accepted + failed + 1} of ${files.length + urls.length}…`;
        (await send(url, "/api/meetings/url", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }, current)) ? accepted++ : failed++;
      }
      status.textContent = `${accepted} accepted; ${failed} need attention. Accepted work continues on the server.`;
    } finally { submit.disabled = false; }
  };
  form.addEventListener("submit", onSubmit);
  const dispose = () => { disposed = true; clearTimers(); form.removeEventListener("submit", onSubmit); window.removeEventListener("pagehide", dispose); };
  window.addEventListener("pagehide", dispose);
  return dispose;
}
