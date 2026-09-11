"""Private local measurement stack; never a qualification or deployment launcher.

Only SQLite's exact version pin is bypassed, matching the supplied local-stack recipe.
Request accounting records time and lane only, never audio, words, prompts, or credentials.
"""
import argparse
import json
import sqlite3
import sys
import threading
import time
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
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version  # Local harness only.
    original = VllmRunner._post_multipart
    lock = threading.Lock()

    def counted(self, *call_args, **kwargs):
        with lock, (args.state / 'requests.jsonl').open('a') as stream:
            stream.write(json.dumps({'time': time.monotonic(),
                'draft': threading.current_thread().name == 'moss-draft'}) + '\n')
        return original(self, *call_args, **kwargs)

    VllmRunner._post_multipart = counted
    argv = [
        '--database', str(args.state / 'phase2.sqlite'),
        '--control-socket', str(args.state / 'control.sock'),
        '--tls-certfile', str(args.cert), '--tls-keyfile', str(args.key),
        '--backend', 'vllm', '--model', str(args.model),
        '--vllm-base-url', 'http://127.0.0.1:18000/v1',
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
