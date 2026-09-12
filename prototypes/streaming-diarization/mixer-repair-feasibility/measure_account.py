"""Fresh-workspace account replay; start your own local stack with the existing recipe.
Retains each completed case immediately. Never resets a database. Raw captures stay
in --out; commit only content-free scores/observations. Uses the established scorer.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import httpx
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness, _quality_surface_observations
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService, SESSION_COOKIE
from moss_transcribe_diarize.live_service_replay import run_service_replay, ServiceReplayRtfFailure

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--origin', default='https://127.0.0.1:17862')
parser.add_argument('--cert', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
os.environ['SSL_CERT_FILE'] = str(args.cert)
corpus = ROOT / 'evidence/live-policy-sweep-20260825/corpus'
cases = ['mono_javier_intro_50s', 'interview_bill_ackman_60s', 'interview_keyu_jin_60s',
         'interview_adam_frank_180s', 'discussion_jamie_dimon_180s', 'discussion_rtfl_90s']
surface = _load_surface_harness(ROOT)
with httpx.Client(verify=str(args.cert), base_url=args.origin) as client:
    client.post('/api/workspace/bootstrap').raise_for_status()
    cookie = args.out / 'measurement.cookie'
    cookie.touch(mode=0o600)
    cookie.write_text(client.cookies.get(SESSION_COOKIE))
account = AccountCookieLiveReplayService(base_url=args.origin, cookie_file=cookie, timeout_seconds=300)
result = {'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'rows': []}
try:
    for case in cases:
        started = time.monotonic()
        out = args.out / case
        out.mkdir()
        captured = surface.SurfaceCaptureService(account, settle_timeout=30, poll_seconds=.25)
        desc = account.descriptor()
        record = {'case_id': case, 'mode': 'account', 'performance_failure': None}
        try:
            try:
                run_service_replay(service=captured, audio_path=corpus/case/'audio.wav', out_dir=out,
                    pace=1, max_pacing_lag=3, runs=1, expect_revision=desc.source_revision,
                    expect_provider_hash=desc.provider_manifest_hash,
                    expect_config_hash=desc.config_hashes.combined_config_hash)
            except ServiceReplayRtfFailure as error:
                record['performance_failure'] = type(error).__name__
                assert all(key in captured.captures for key in ('pre_stop_immediate', 'pre_stop_settled', 'post_stop_final'))
            ref = corpus/case/'reference.jsonl'
            with wave.open(str(corpus/case/'audio.wav')) as audio:
                duration = audio.getnframes()/audio.getframerate()
            record['scores'] = {name: surface.score_surface(surface.Case(case, corpus/case, ref),
                surface.transcript_rows(cap['snapshot'], duration)) for name, cap in captured.captures.items()}
            record['surface_observations'] = _quality_surface_observations(captured.captures,
                reference_speaker_count=len({json.loads(line)['speaker'] for line in ref.read_text().splitlines()}))
        except Exception as error:
            record['error'] = type(error).__name__
        finally:
            (out/'captures.json').write_text(json.dumps(captured.captures))
            record['elapsed_seconds'] = time.monotonic()-started
            result['rows'].append(record)
            (args.out/'results.json').write_text(json.dumps(result, indent=2)+'\n')
            print(case, record.get('error', 'measured'), flush=True)
finally:
    account.close()
