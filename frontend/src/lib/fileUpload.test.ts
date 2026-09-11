// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { bindFileUpload } from "./fileUpload";
import { OPEN_MEETING_EVENT } from "./meetingEvents";

let dispose = () => {};
afterEach(() => { dispose(); document.body.replaceChildren(); vi.unstubAllGlobals(); vi.useRealTimers(); });
function setup() {
  document.body.innerHTML = '<form data-file-upload="form"><input name="file" type="file" multiple><textarea name="urls"></textarea><button type="submit">Transcribe files and URLs</button></form><p data-file-upload="status"></p><ul data-file-upload="results"></ul>';
  dispose = bindFileUpload();
  return document.querySelector('form')!;
}
function meeting(status: string) {
  return { id: 'accepted', mode: 'file', title: 'Audio', title_source: 'automatic', status,
    created_at_ms: 1, transcript_version: 0, transcript: null, audio: null };
}
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe('account file/URL feedback', () => {
  it('keeps per-item outcomes, follows actual processing, and opens only on request', async () => {
    const form = setup();
    const requests: string[] = [];
    let reads = 0;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      requests.push(url);
      if (url === '/api/meetings/url') return JSON.parse(init!.body as string).url.includes('bad')
        ? response({ detail: 'Unsupported media URL' }, 422) : response(meeting('active'));
      return response(meeting(++reads > 1 ? 'completed' : 'active'));
    }));
    form.querySelector('textarea')!.value = 'https://good.test/audio\nhttps://bad.test/audio';
    const open = vi.fn();
    document.addEventListener(OPEN_MEETING_EVENT, open);
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await vi.waitFor(() => expect(document.body.textContent).toContain('Unsupported media URL'));
    expect(document.body.textContent).toContain('Processing on the server');
    expect(document.querySelectorAll('[data-file-upload="results"] li')).toHaveLength(2);
    expect(open).not.toHaveBeenCalled();
    document.querySelector<HTMLButtonElement>('[aria-label="Open meeting for https://good.test/audio"]')!.click();
    expect(open).toHaveBeenCalledOnce();
    expect((open.mock.calls[0][0] as CustomEvent).detail).toEqual({ meetingId: 'accepted' });
    await vi.waitFor(() => expect(document.body.textContent).toContain('Completed — ready to open.'), { timeout: 2500 });
    expect(requests.filter(url => url === '/api/meetings/url')).toHaveLength(2);
    document.removeEventListener(OPEN_MEETING_EVENT, open);
  });

  it('does not duplicate a pending upload or invent a rejection after a network error', async () => {
    const form = setup();
    Object.defineProperty(form.querySelector('input'), 'files', { value: [new File(['audio'], '<sample>.wav')] });
    let reject!: (reason: Error) => void;
    const fetcher = vi.fn(() => new Promise((_resolve, fail) => { reject = fail; }));
    vi.stubGlobal('fetch', fetcher);
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    expect(fetcher).toHaveBeenCalledOnce();
    expect(document.querySelector('strong')!.textContent).toBe('<sample>.wav');
    reject(new Error('offline'));
    await vi.waitFor(() => expect(document.body.textContent).toContain('Check your connection and meeting history before retrying'));
    expect(document.querySelector('button')!.disabled).toBe(false);
    expect(document.querySelector('[data-file-upload="results"] button')).toBeNull();
  });
});
