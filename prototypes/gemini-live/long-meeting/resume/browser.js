// THROWAWAY extension of the actual CaptureClient/worklet. TS-private state
// access exposes exactly what an adoptSession method must initialize.
import {CaptureClient} from '../../../../frontend/src/capture/captureClient.ts';

const SETTINGS = {transcription: {vendor: 'gemini', model: 'gemini-3.5-transcribe', api_key: 'offline-prototype-stub'}, cleanup_after_stop: false};
const KEY = 'p74-resume-settings';
const log = window.measurement = {actions: [], errors: [], frames: [], resumes: []};
const actualFetch = window.fetch.bind(window);
window.fetch = async (url, options) => {
  if (String(url).endsWith('/stop') || String(url).endsWith('/abort')) {
    options = {...options, headers: {...options?.headers, 'X-Moss-Capture-Instance': client.instanceId}};
  }
  const r = await actualFetch(url, options);
  if (String(url).endsWith('/frames')) {
    const v = JSON.parse(options.body);
    log.frames.push({lane: v.lane, sequence: v.sequence, epoch: v.device_epoch, start: v.capture_timestamp_ns,
      end: v.capture_end_timestamp_ns, discontinuity: v.discontinuity, silent: v.silent, status: r.status});
  }
  return r;
};

class ResumeClient extends CaptureClient {
  requestHeaders(json = false) {
    return {...super.requestHeaders(json), 'X-Moss-Capture-Instance': this.instanceId};
  }
  async postFrame(frame, lane) {
    // Offset BOTH endpoints; the new AudioContext begins near zero.
    frame.capture_timestamp_ns += this.offsetNs || 0;
    frame.capture_end_timestamp_ns += this.offsetNs || 0;
    const result = await super.postFrame(frame, lane);
    return result;
  }
  async adopt(saved) {
    const snap = await (await fetch(`/api/live/sessions/${saved.meetingId}/snapshot`)).json();
    if (snap.snapshot.session.status !== 'active') throw Error('meeting cannot resume');
    const requestStart = performance.now();
    const response = await fetch(`/api/live/sessions/${saved.meetingId}/resume`, {
      method: 'POST', headers: this.requestHeaders(true), body: JSON.stringify({
        expected_instance_id: saved.instanceId,
        heartbeat: {schema: 'moss-live-helper-health.v1', instance_id: this.instanceId, sequence: 0,
          sent_monotonic_ns: 1, helper_version: 'p74-resume-prototype', state: 'capturing',
          lanes: Object.fromEntries([...this.lanes].map(([lane]) => [lane, this.heartbeatLane(lane, 'capturing')]))},
      })});
    const state = await response.json();
    if (!response.ok) throw Error(JSON.stringify(state));
    log.resumes.push({state, roundTripMs: performance.now() - requestStart});
    // Bound receipt-time uncertainty by round trip; do not use Date.now or
    // meeting created_at as an exact source-clock origin.
    this.offsetNs = state.capture_now_ns - Math.round(this.context.currentTime * 1e9);
    this.heartbeatSequence = state.heartbeat_next_sequence;
    this.heartbeatMonotonicNs = state.heartbeat_next_monotonic_ns - 1;
    for (const [lane, value] of this.lanes) {
      value.sequence = state.lanes[lane].next_sequence;
      value.deviceEpoch = state.lanes[lane].resume_device_epoch;
      value.pendingDiscontinuityEpochs.add(value.deviceEpoch);
      value.frameQueue = [];
    }
    this.session = Object.freeze({id: saved.meetingId});
    sessionStorage.setItem(KEY, JSON.stringify({...saved, instanceId: this.instanceId}));
    await this.scheduleHeartbeat('capturing');
    return state;
  }
}

let client;
function makeClient() {
  client = new ResumeClient({helperVersion: 'p74-resume-prototype', workletUrl: '/prototype/worklet.js',
    onTransportError: (route, e) => log.errors.push([route, String(e)])});
  window.capture = client;
  return client;
}

async function start() {
  const c = makeClient();
  // Called before any await: required transient activation for tab capture.
  const display = c.requestDisplayMedia();
  const shared = await display;
  if (!await c.attachDisplayMedia(shared)) throw Error('shared surface has no audio');
  const deviceId = await c.startMicrophone();
  c.setMicrophoneMuted(true);
  const value = await c.createSession(SETTINGS);
  sessionStorage.setItem(KEY, JSON.stringify({meetingId: value.id, instanceId: c.instanceId,
    sources: {system: true, microphone: true}, microphoneDeviceId: deviceId,
    microphoneMuted: true, echoCancellation: true, displaySurface: c.displaySurface,
    shareLabel: shared.getVideoTracks()[0]?.label || shared.getAudioTracks()[0]?.label}));
  log.actions.push({action: 'start', contextTime: c.context.currentTime,
    audioSettings: c.lanes.get('microphone').tracks[0].getSettings(), saved: JSON.parse(sessionStorage.getItem(KEY))});
  document.querySelector('#state').textContent = 'Recording';
}

async function resume() {
  const saved = JSON.parse(sessionStorage.getItem(KEY));
  const c = makeClient();
  const display = c.requestDisplayMedia();
  const shared = await display;
  if (!await c.attachDisplayMedia(shared)) throw Error('shared surface has no audio');
  const deviceId = await c.startMicrophone(saved.microphoneDeviceId);
  if (deviceId !== saved.microphoneDeviceId) throw Error('same microphone unavailable');
  c.setMicrophoneMuted(saved.microphoneMuted);
  const state = await c.adopt(saved);
  log.actions.push({action: 'resume', contextTime: c.context.currentTime,
    selectedShareLabel: shared.getVideoTracks()[0]?.label || shared.getAudioTracks()[0]?.label,
    audioSettings: c.lanes.get('microphone').tracks[0].getSettings(), saved, state});
  document.querySelector('#state').textContent = 'Recording resumed';
}

// Gesture-free microphone/context check, separately from recommended button flow.
window.noGestureProbe = async () => {
  const saved = JSON.parse(sessionStorage.getItem(KEY));
  const stream = await navigator.mediaDevices.getUserMedia({audio: {
    deviceId: {exact: saved.microphoneDeviceId}, echoCancellation: true}});
  const audio = new AudioContext({sampleRate: 16000});
  const before = audio.state;
  const after = await Promise.race([audio.resume().then(() => audio.state),
    new Promise(resolve => setTimeout(() => resolve('resume-timeout:' + audio.state), 1200))]);
  await new Promise(resolve => setTimeout(resolve, 200));
  const result = {before, after, microphone: stream.getAudioTracks()[0].getSettings(),
    currentTime: audio.currentTime, activation: navigator.userActivation.isActive};
  stream.getTracks().forEach(t => t.stop()); await audio.close();
  log.actions.push({action: 'no gesture', result}); return result;
};

for (const [id, fn] of [['start', start], ['resume', resume], ['stop', async () => {
  await client.stop(20); document.querySelector('#state').textContent = 'Completed';
}]]) document.getElementById(id).onclick = () => fn().catch(e => {
  log.errors.push(String(e)); document.querySelector('#state').textContent = String(e);
});
const saved = sessionStorage.getItem(KEY);
document.getElementById('resume').disabled = !saved;
document.getElementById('state').textContent = saved ? 'Recording interrupted — Resume recording' : 'Ready';
