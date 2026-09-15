"""Demo-path verification: two DIFFERENT voices, one per lane, NON-overlapping.

`verify_workspace.py` feeds identical audio to both lanes, so it never proves that two
distinct speakers survive the mixer. The presenter flow in `docs/handoffs/demo-script.md`
depends on exactly that, and on it holding at the level a built-in laptop microphone
actually produces -- roughly 3 % of shared-tab audio, which is what the 2026-09-14
attended run measured. Both conditions are checked here.

Run: .venv/bin/python tests/e2e/verify_demo_lanes.py --allow-local-self-signed
Exit 0 = the demo path is intact; exit 1 = it is not; nothing is retained.

Scope: the NON-overlapping path only. Simultaneous speech on both lanes is a known
limitation (see the handback) -- do not read a pass here as overlap support.
"""
from __future__ import annotations
import argparse
import array
import base64
import json
import ssl
import sys
import time
import urllib.request
import wave
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / 'evidence/live-policy-sweep-20260825/corpus'
SHARED_TAB_VOICE = CORPUS / 'interview_bill_ackman_60s/audio.wav'
MICROPHONE_VOICE = CORPUS / 'interview_keyu_jin_60s/audio.wav'

# The attended run measured the built-in microphone at ~3 % of shared-tab full scale.
DEFAULT_MIC_GAIN = 0.03


class Client:
    """Cookie-carrying JSON client. One bootstrap per run: each call creates a workspace."""

    def __init__(self, base: str, context: ssl.SSLContext | None):
        self._base, self._context, self._jar = base.rstrip('/'), context, {}

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {'Content-Type': 'application/json'}
        if self._jar:
            headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in self._jar.items())
        request = urllib.request.Request(self._base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, context=self._context, timeout=60) as response:
            for header in response.headers.get_all('Set-Cookie') or []:
                name, _, value = header.partition('=')
                self._jar[name] = value.split(';')[0]
            return json.loads(response.read() or b'{}')


def lane_pcm(path: Path, seconds: float, gain: float = 1.0) -> bytes:
    with wave.open(str(path)) as source:
        pcm = source.readframes(min(source.getnframes(), int(source.getframerate() * seconds)))
    if gain == 1.0:
        return pcm
    samples = array.array('h')
    samples.frombytes(pcm)
    for index in range(len(samples)):
        samples[index] = int(samples[index] * gain)
    return samples.tobytes()


def run(base: str, context: ssl.SSLContext | None, seconds: float, mic_gain: float) -> int:
    client = Client(base, context)
    client.call('POST', '/api/workspace/bootstrap')
    descriptor = client.call('GET', '/api/live/descriptor')['descriptor']
    frame_samples, sample_rate = descriptor['frame_samples'], descriptor['sample_rate']

    created = client.call('POST', '/api/live/sessions', {'source_revision': descriptor['source_revision']})
    session_id = created.get('id') or created.get('session_id')
    if not session_id:
        print('  FAIL: no session id in create response')
        return 1

    tab = lane_pcm(SHARED_TAB_VOICE, seconds)
    microphone = lane_pcm(MICROPHONE_VOICE, seconds, mic_gain)
    print(f'  microphone lane at {mic_gain:.0%} of full scale (built-in-microphone level)')

    frame_bytes = frame_samples * 2
    silence = b'\0' * frame_bytes
    total = min(len(tab), len(microphone)) // frame_bytes
    handover = total // 2
    epoch = int(time.time() * 1e9)
    started = time.monotonic()

    for sequence in range(total):
        offset = sequence * frame_bytes
        # First half: the shared tab speaks alone. Second half: the microphone does.
        if sequence < handover:
            lanes = (('system', tab[offset:offset + frame_bytes]), ('microphone', silence))
        else:
            lanes = (('system', silence), ('microphone', microphone[offset:offset + frame_bytes]))
        for lane, chunk in lanes:
            client.call('POST', f'/api/live/sessions/{session_id}/frames', {
                'lane': lane,
                'sequence': sequence,
                'capture_timestamp_ns': epoch + sequence * int(frame_samples / sample_rate * 1e9),
                'device_epoch': epoch,
                'pcm_base64': base64.b64encode(chunk).decode(),
                'sample_count': frame_samples,
                'sample_rate': sample_rate,
                'silent': chunk == silence,
                'discontinuity': False,
            })
        # Real time, because the runtime's span freeze is wall-clock driven.
        time.sleep(max(0.0, (sequence + 1) * (frame_samples / sample_rate) - (time.monotonic() - started)))

    client.call('POST', f'/api/live/sessions/{session_id}/stop', {'deadline': 30})
    time.sleep(12)
    snapshot = client.call('GET', f'/api/live/sessions/{session_id}/snapshot')['snapshot']
    session = snapshot.get('session') or {}
    segments = session.get('effective_transcript') or session.get('committed') or []
    if isinstance(segments, dict):
        segments = segments.get('segments') or []

    handover_sample = handover * frame_samples
    speakers = [s.get('canonical_speaker') for s in segments if s.get('canonical_speaker')]
    before = {s.get('canonical_speaker') for s in segments if s.get('end_sample', 0) <= handover_sample}
    after = {s.get('canonical_speaker') for s in segments if s.get('start_sample', 0) >= handover_sample}

    print(f'  finalization: {session.get("finalization_status")} | identity_counts: {snapshot.get("identity_counts")}')
    print(f'  === {len(segments)} segments, handover at sample {handover_sample} ===')
    for segment in segments:
        label = segment.get('canonical_speaker') or '(unlabeled)'
        print(f'    [{segment.get("start_sample", "?")}] {label}: {str(segment.get("text", ""))[:78]}')

    failures = []
    if session.get('finalization_status') != 'final':
        failures.append(f'session did not finalize: {session.get("finalization_status")}')
    if len(set(speakers)) < 2:
        failures.append(f'expected 2 distinct speakers, saw {sorted(set(speakers))}')
    if not after:
        failures.append('microphone half produced no transcript -- the presenter would not be transcribed')
    if before and after and before == after:
        failures.append(f'both halves carry the same speaker {before} -- the lanes did not separate')

    print()
    for failure in failures:
        print(f'  FAIL: {failure}')
    if failures:
        return 1
    print(f'  PASS: tab half {sorted(before)} then microphone half {sorted(after)}, separated at {handover_sample}')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='https://127.0.0.1:17861')
    parser.add_argument('--allow-local-self-signed', action='store_true',
                        help='Bypass TLS only for an isolated loopback test stack')
    parser.add_argument('--seconds', type=float, default=24.0, help='Audio per lane; half to each speaker')
    parser.add_argument('--mic-gain', type=float, default=DEFAULT_MIC_GAIN,
                        help='Microphone lane scale; 1.0 is full scale')
    args = parser.parse_args(argv)

    context = None
    if args.allow_local_self_signed:
        if urlsplit(args.base).hostname not in {'127.0.0.1', '::1', 'localhost'}:
            parser.error('--allow-local-self-signed is only permitted against a loopback base')
        context = ssl._create_unverified_context()
    for voice in (SHARED_TAB_VOICE, MICROPHONE_VOICE):
        if not voice.exists():
            print(f'  SKIP: corpus voice missing: {voice}')
            return 77
    return run(args.base, context, args.seconds, args.mic_gain)


if __name__ == '__main__':
    sys.exit(main())
