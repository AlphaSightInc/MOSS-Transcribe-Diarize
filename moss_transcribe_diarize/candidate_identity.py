"""Canonical embedded identity for staging and qualification wheel builds.

Run from a clean source checkout before building its source copy:
    python moss_transcribe_diarize/candidate_identity.py REPO SOURCE_COPY
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Mapping

FIXTURE_PATHS = {
    "quality_corpus_manifest": "evidence/live-policy-sweep-20260825/corpus/corpus-manifest.json",
    "concurrency_fixture": "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json",
    "concurrency_preregistration": "prototypes/streaming-diarization/concurrency/preregistration.json",
}


def write_build_candidate(source_copy: Path, identity: Mapping[str, object]) -> Path:
    """Select identity fields and serialize exactly once, including nested key order."""
    embedded = {"schema": "moss-phase2-acceptance.v1", **{
        key: identity[key] for key in ("git_sha", "git_tree", "uv_lock_sha256", "fixtures")
    }}
    path = source_copy / "moss_transcribe_diarize/build_candidate.json"
    path.write_bytes((json.dumps(embedded, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


def write_source_identity(repo: Path, source_copy: Path) -> Path:
    def git(*args):
        return subprocess.check_output(("git", *args), cwd=repo, text=True).strip()
    return write_build_candidate(source_copy, {
        "git_sha": git("rev-parse", "HEAD"),
        "git_tree": git("rev-parse", "HEAD^{tree}"),
        "uv_lock_sha256": hashlib.sha256((repo / "uv.lock").read_bytes()).hexdigest(),
        "fixtures": {key: hashlib.sha256((repo / value).read_bytes()).hexdigest()
                     for key, value in FIXTURE_PATHS.items()},
    })


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("source_copy", type=Path)
    args = parser.parse_args()
    write_source_identity(args.repo, args.source_copy)
