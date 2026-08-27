#!/usr/bin/env python3
"""One-command fresh execution of the preregistered MOSS and two-peer sweep."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CASES = (
    "mono_javier_intro_50s",
    "interview_bill_ackman_60s",
    "interview_keyu_jin_60s",
    "interview_adam_frank_180s",
    "discussion_jamie_dimon_180s",
    "discussion_rtfl_90s",
)
REMOTE_HOST = "ga0@m4mbp"
LT_REPO = "/Users/ga0/Desktop/AI_Projects/LiveTranscribe"


def run(command: list[str], *, accepted: tuple[int, ...] = (0,), input_text: str | None = None) -> int:
    print("+ " + " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=REPO, text=True, input=input_text)
    if completed.returncode not in accepted:
        raise RuntimeError(f"command exited {completed.returncode}: {command}")
    return completed.returncode


def remote_script(script: str) -> None:
    run(["ssh", REMOTE_HOST, "zsh", "-s"], input_text=script)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit(f"output must be absent: {out}")
    out.mkdir(parents=True)
    corpus = out / "corpus"
    run([sys.executable, str(HERE / "prepare_corpus.py"), "--output", str(corpus)])
    moss_rc = run(
        [sys.executable, str(HERE / "moss_sweep.py"), "--corpus", str(corpus), "--output", str(out / "moss"), "--passes", "2"],
        accepted=(0, 2),
    )

    remote_root = f"/tmp/moss-live-policy-sweep-{int(time.time())}-{os.getpid()}"
    remote_script(f"set -e\ntest ! -e {remote_root}\nmkdir -p {remote_root}/livetranscribe {remote_root}/projectclerk\n")
    run(["rsync", "-a", f"{corpus}/", f"{REMOTE_HOST}:{remote_root}/corpus/"])
    helpers = ("projectclerk_ax.swift", "watch_projectclerk_sessions.py", "run_projectclerk_case.sh")
    run(["rsync", "-a", *(str(HERE / name) for name in helpers), f"{REMOTE_HOST}:{remote_root}/"])
    manifest = {
        "fixtures": [
            {"fixture_id": case_id, "audio_path": f"{remote_root}/corpus/{case_id}/audio.wav"}
            for case_id in CASES
        ]
    }
    local_lt_manifest = out / "livetranscribe-manifest.json"
    local_lt_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    run(["rsync", "-a", str(local_lt_manifest), f"{REMOTE_HOST}:{remote_root}/livetranscribe-manifest.json"])

    cases = " ".join(CASES)
    remote_script(
        f"""set -e
cd {LT_REPO}
for case_id in {cases}; do
  run_dir={remote_root}/livetranscribe/${{case_id}}
  LIVE_CAPTURE_MANIFEST_PATH={remote_root}/livetranscribe-manifest.json \
  LIVE_CAPTURE_MODE=speaker LIVE_CAPTURE_BROWSER_ENABLED=0 \
  LIVE_CAPTURE_SNAPSHOT_INTERVAL_SEC=1 LIVE_CAPTURE_DRAIN_TIMEOUT_SEC=180 \
  LIVE_CAPTURE_TERMINAL_TIMEOUT_SEC=300 \
  scripts/agent_driven_live_capture.sh "$case_id" "$run_dir" \
    >"${{run_dir}}.stdout.log" 2>"${{run_dir}}.stderr.log"
done
"""
    )
    remote_script(
        f"""set -e
swiftc {remote_root}/projectclerk_ax.swift -o {remote_root}/projectclerk_ax
chmod +x {remote_root}/run_projectclerk_case.sh {remote_root}/watch_projectclerk_sessions.py
for case_id in {cases}; do
  {remote_root}/run_projectclerk_case.sh \
    {remote_root}/corpus/${{case_id}}/audio.wav \
    {remote_root}/projectclerk/${{case_id}} \
    {remote_root} \
    >{remote_root}/projectclerk/${{case_id}}.stdout.log \
    2>{remote_root}/projectclerk/${{case_id}}.stderr.log
done
"""
    )
    peers = out / "peers"
    peers.mkdir()
    run(["rsync", "-a", f"{REMOTE_HOST}:{remote_root}/livetranscribe/", str(peers / "livetranscribe") + "/"])
    run(["rsync", "-a", f"{REMOTE_HOST}:{remote_root}/projectclerk/", str(peers / "projectclerk") + "/"])
    peer_rc = run(
        [sys.executable, str(HERE / "score_peers.py"), "--corpus", str(corpus), "--peer-root", str(peers), "--output", str(out / "peer-scores")],
        accepted=(0, 2),
    )
    reconcile_rc = run(
        [sys.executable, str(HERE / "reconcile_existing_shadows.py"), "--corpus", str(corpus), "--moss-root", str(out / "moss"), "--output", str(out / "moss-reconciled")],
        accepted=(0, 2),
    )
    summary = {
        "schema": "moss-live-policy-one-command.v1",
        "output": str(out),
        "remote_root": remote_root,
        "moss_exit": moss_rc,
        "peer_exit": peer_rc,
        "reconciliation_exit": reconcile_rc,
        "meaning": "exit 2 is a retained measurement gate failure, not an omitted run",
    }
    (out / "one-command-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if (peer_rc == 0 and moss_rc == 0 and reconcile_rc == 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
