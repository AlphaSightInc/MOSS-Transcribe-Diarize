// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { bindFileUpload } from "./fileUpload";
import { OPEN_MEETING_EVENT } from "./meetingEvents";
import { defaultAppSettings, saveAppSettings } from "./settings";

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


it('shows the saved failure reason in the upload result row', async () => {
  const form = setup();
  form.querySelector('textarea')!.value = 'https://example.test/bad.mp3';
  vi.stubGlobal('fetch', vi.fn(async (url: string) => response(
    url === '/api/meetings/url' ? meeting('active') :
      {...meeting('failed'),failure_code:'invalid_audio',failure_reason:'Invalid audio: cannot decode this file.'})));
  form.dispatchEvent(new Event('submit', {cancelable:true}));
  await vi.waitFor(() => expect(document.querySelector('[data-file-upload="results"] li span')!.textContent)
    .toBe('Invalid audio: cannot decode this file.'));
});

it('shows capacity refusal before sending file bytes or creating a meeting', async () => {
  const form = setup();
  Object.defineProperty(form.querySelector('input'), 'files', { value: [new File(['audio'], 'large.wav')] });
  const fetcher = vi.fn(async () => response({ detail: 'Insufficient storage for upload.' }, 507));
  vi.stubGlobal('fetch', fetcher);
  form.dispatchEvent(new Event('submit', { cancelable: true }));
  await vi.waitFor(() => expect(document.body.textContent).toContain('Not accepted: Insufficient storage for upload.'));
  expect(fetcher).toHaveBeenCalledOnce();
  expect(fetcher.mock.calls[0]).toEqual(['/api/meetings/file/admission', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"file_bytes":5}'
  }]);
  expect(document.querySelector('[data-file-upload="results"] button')).toBeNull();
});

it('sends a file only after preflight succeeds, preserving authoritative upload refusal', async () => {
  const form = setup();
  Object.defineProperty(form.querySelector('input'), 'files', { value: [new File(['audio'], 'media.wav')] });
  const fetcher = vi.fn(async (url: string) => url.endsWith('/admission')
    ? new Response(null, { status: 204 }) : response({ detail: 'Insufficient storage for upload.' }, 507));
  vi.stubGlobal('fetch', fetcher);
  form.dispatchEvent(new Event('submit', { cancelable: true }));
  await vi.waitFor(() => expect(document.body.textContent).toContain('Not accepted: Insufficient storage for upload.'));
  expect(fetcher.mock.calls.map(call => call[0])).toEqual(['/api/meetings/file/admission', '/api/meetings/file']);
});

it('sends the browser transcription settings (I-2) with every file and URL', async () => {
  const values = new Map<string, string>();
  vi.stubGlobal('localStorage', { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
  const settings = defaultAppSettings();
  settings.transcription.apiKey = 'k';
  saveAppSettings(settings);
  const form = setup();
  Object.defineProperty(form.querySelector('input'), 'files', { value: [new File(['audio'], 'media.wav')] });
  form.querySelector('textarea')!.value = 'https://example.test/a.mp3';
  const bodies: Record<string, BodyInit | null | undefined> = {};
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/admission')) return new Response(null, { status: 204 });
    if (url === '/api/meetings/file' || url === '/api/meetings/url') { bodies[url] = init?.body; return response(meeting('completed')); }
    return response(meeting('completed'));
  }));
  form.dispatchEvent(new Event('submit', { cancelable: true }));
  await vi.waitFor(() => expect(Object.keys(bodies)).toHaveLength(2));
  const wire = { vendor: 'gemini', url: null, model: 'gemini-3.5-transcribe', api_key: 'k' };
  const multipart = bodies['/api/meetings/file'] as FormData;
  expect(JSON.parse(multipart.get('transcription') as string)).toEqual(wire);
  expect((multipart.get('file') as File).name).toBe('media.wav');
  expect(JSON.parse(bodies['/api/meetings/url'] as string)).toEqual({ url: 'https://example.test/a.mp3', transcription: wire });
});
