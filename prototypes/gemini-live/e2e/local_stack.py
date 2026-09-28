"""Private local measurement stack; never a qualification or deployment launcher.

Only SQLite's exact version pin is bypassed, matching the supplied local-stack recipe.
Request accounting records time and lane only, never audio, words, prompts, or credentials.
"""
import argparse
import base64
import hashlib
import inspect
import json
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--cert', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--port', type=int, default=17862)
    parser.add_argument('--draft-lane-seconds', type=float)
    parser.add_argument('--vllm-base-url', default='http://127.0.0.1:18000/v1')
    parser.add_argument('--max-requests', type=int)
    model_snapshots = sorted(Path.home().glob(
        '.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/*'))
    parser.add_argument('--model', type=Path, default=model_snapshots[-1] if model_snapshots else None)
    parser.add_argument('--manifest', type=Path, default=Path.home() /
                        '.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
    args = parser.parse_args()
    if args.model is None:
        parser.error('local model metadata is required')
    args.state.mkdir(parents=True, exist_ok=True)
    args.state.chmod(0o700)
    from moss_transcribe_diarize.app import phase2, phase2_web_cli
    from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime
    from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
    from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer
    from moss_transcribe_diarize.app.live_identity_sweep import LiveIdentitySweeper
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version  # Local harness only.
    original = VllmRunner._post_multipart
    lock = threading.Lock()
    capacity = threading.BoundedSemaphore(2)
    request_count = 0

    def counted(self, *call_args, **kwargs):
        nonlocal request_count
        frame = inspect.currentframe().f_back
        callers = []
        lane = None
        span = None
        window = None
        for _ in range(30):
            if frame is None:
                break
            callers.append(frame.f_code.co_name)
            if lane is None and frame.f_locals.get('lane') in ('system', 'microphone'):
                lane = frame.f_locals['lane']
            if lane is None and frame.f_code.co_name == '_decode_draft':
                index = frame.f_locals.get('index')
                lanes = frame.f_locals.get('lane_pcm')
                if isinstance(index, int) and isinstance(lanes, tuple) and index < len(lanes):
                    lane = lanes[index][0]
            candidate = frame.f_locals.get('span')
            if span is None and hasattr(candidate, 'start_sample') and hasattr(candidate, 'end_sample'):
                span = candidate
            candidate_window = frame.f_locals.get('window')
            if window is None and hasattr(candidate_window, 'start') and hasattr(candidate_window, 'end'):
                window = candidate_window
            frame = frame.f_back
        names = set(callers)
        kind = ('terminal' if 'finish_lane' in names else
                'draft' if any('draft' in name for name in names) else
                'revision' if 'decode_refinement' in names else
                'canonical' if 'prepare_lanes' in names else 'unknown')
        context = {
            'id': uuid.uuid4().hex,
            'kind': kind,
            'lane': lane,
            'thread': threading.current_thread().name,
            'span_start_sample': getattr(span, 'start_sample', None),
            'span_end_sample': getattr(span, 'end_sample', None),
            'span_id': getattr(span, 'id', None),
            'window_start_s': getattr(window, 'start', None),
            'window_end_s': getattr(window, 'end', None),
            'window_index': getattr(window, 'index', None),
            'callers': callers,
            'client_monotonic_ns': time.monotonic_ns(),
        }
        encoded = base64.urlsafe_b64encode(json.dumps(context, separators=(',', ':')).encode()).decode().rstrip('=')
        call_args = (str(call_args[0]) + '?dx=' + encoded, *call_args[1:])
        with capacity:
            with lock:
                if args.max_requests is not None and request_count >= args.max_requests:
                    raise RuntimeError("Local measurement request budget exhausted")
                request_count += 1
                with (args.state / 'requests.jsonl').open('a') as stream:
                    stream.write(json.dumps({'time': time.monotonic(), 'request': request_count,
                        'draft': threading.current_thread().name == 'moss-draft'}) + '\n')
            return original(self, *call_args, **kwargs)

    VllmRunner._post_multipart = counted
    original_event = LiveServiceRuntime._record_event
    event_lock = threading.Lock()

    def recorded_event(self, state, kind, payload):
        original_event(self, state, kind, payload)
        event = state.events[-1]
        with event_lock:
            with (args.state / 'server-events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({
                    'server_monotonic_ns': time.monotonic_ns(),
                    'seq': event.seq, 'session_id': event.session_id,
                    'kind': event.kind, 'snapshot_version': event.snapshot_version,
                    'payload': event.payload,
                }, ensure_ascii=False, default=str) + '\n')

    LiveServiceRuntime._record_event = recorded_event
    identity_lock = threading.Lock()

    def identity_record(value):
        with identity_lock:
            with (args.state / 'identity-events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'server_monotonic_ns': time.monotonic_ns(), **value},
                                        ensure_ascii=False, default=str) + '\n')

    original_refinement = LiveCoordinator.decode_refinement

    def recorded_refinement(self, request):
        before = set(self._stopped_refinement_lanes)
        result = original_refinement(self, request)
        after = set(self._stopped_refinement_lanes)
        identity_record({'kind': 'refinement_lane_state',
                         'window_index': request.window_index,
                         'start_sample': request.start_sample,
                         'end_sample': request.end_sample,
                         'newly_stopped_lanes': sorted(after - before),
                         'stopped_lanes': sorted(after),
                         'failed_lanes': list(result.failed_lanes),
                         'failure': result.failure})
        return result

    LiveCoordinator.decode_refinement = recorded_refinement

    original_prepare = BoundedCausalIdentityPreparer.prepare

    def recorded_prepare(self, **kwargs):
        result = original_prepare(self, **kwargs)
        base = kwargs['base_snapshot']
        after = result.proposed_snapshot
        frame = inspect.currentframe().f_back
        lane = None
        while frame is not None:
            if frame.f_locals.get('lane') in ('system', 'microphone'):
                lane = frame.f_locals['lane']
                break
            frame = frame.f_back
        span = kwargs['span']
        identity_record({
            'kind': 'prepare', 'lane': lane, 'span_id': span.id,
            'start_sample': span.start_sample, 'end_sample': span.end_sample,
            'status': result.status, 'reason': result.reason,
            'before_speakers': list(base.canonical_speakers),
            'after_speakers': list(after.canonical_speakers),
            'births': sorted(set(after.canonical_speakers) - set(base.canonical_speakers)),
            'allowed_speakers': kwargs.get('allowed_speakers'),
            'diagnostics': dict(after.diagnostics),
        })
        return result

    BoundedCausalIdentityPreparer.prepare = recorded_prepare
    for method_name in ('maybe_sweep', 'sweep_now'):
        original_sweep = getattr(LiveIdentitySweeper, method_name)

        def recorded_sweep(self, *call_args, _original=original_sweep,
                           _name=method_name, **call_kwargs):
            revision = _original(self, *call_args, **call_kwargs)
            if revision is not None:
                frame = inspect.currentframe().f_back
                lane = None
                while frame is not None:
                    if frame.f_locals.get('lane') in ('system', 'microphone'):
                        lane = frame.f_locals['lane']
                        break
                    frame = frame.f_back
                identity_record({'kind': _name, 'lane': lane, 'revision': revision.to_dict()})
            return revision

        setattr(LiveIdentitySweeper, method_name, recorded_sweep)
    argv = [
        '--database', str(args.state / 'phase2.sqlite'),
        '--control-socket', str(args.state / 'control.sock'),
        '--tls-certfile', str(args.cert), '--tls-keyfile', str(args.key),
        '--backend', 'vllm', '--model', str(args.model),
        '--vllm-base-url', args.vllm_base_url,
        '--vllm-model', 'OpenMOSS-Team/MOSS-Transcribe-Diarize', '--vllm-timeout', '1800',
        '--file-work-root', str(args.state / 'file-work'),
        '--meeting-audio-root', str(args.state / 'meeting-audio'),
        '--live-provider-manifest', str(args.manifest), '--live-helper-lease-seconds', '30',
        '--host', '127.0.0.1', '--port', str(args.port),
        '--max-len', '16384', '--max-new-tokens', '12000',
    ]
    if args.draft_lane_seconds is not None:
        argv += ['--live-draft-lane-seconds', str(args.draft_lane_seconds)]
    phase2_web_cli.main(argv)


if __name__ == '__main__':
    main()
