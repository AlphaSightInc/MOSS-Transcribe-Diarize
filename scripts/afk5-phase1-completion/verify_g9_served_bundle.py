#!/usr/bin/env python3
"""Pin and inspect the bundle served by the Python application for G9."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_PATH = Path("ProjectResources/Frontend/app.js")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def check(text: str, label: str, needle: str, expected: bool) -> bool:
    actual = needle in text
    result = actual is expected
    print(
        "ASSERT"
        f" label={label}"
        f" expected={'present' if expected else 'absent'}"
        f" actual={'present' if actual else 'absent'}"
        f" result={'PASS' if result else 'FAIL'}"
        f" needle={needle!r}"
    )
    return result


def main() -> int:
    bundle = REPO_ROOT / BUNDLE_PATH
    bundle_text = bundle.read_text(encoding="utf-8")
    source_checks = (
        (
            "source_file_bearer_owner",
            Path("frontend/src/App.tsx"),
            'const [captureBearer, setCaptureBearer] = useState("");',
            True,
        ),
        (
            "source_file_bearer_panel_prop",
            Path("frontend/src/App.tsx"),
            "<FilePanel captureBearer={captureBearer} />",
            True,
        ),
        (
            "source_file_upload_passes_options",
            Path("frontend/src/components/FilePanel.tsx"),
            "submitJob(selectedFile, options)",
            True,
        ),
        (
            "source_file_request_sets_bearer",
            Path("frontend/src/api/jobs.ts"),
            'headers.set("Authorization", `Bearer ${bearerToken}`)',
            True,
        ),
        (
            "source_export_session_timestamp_filename",
            Path("frontend/src/lib/transcriptExport.ts"),
            "`transcript-${identity.sessionId}-${identity.exportedAt.toISOString()}.${format}`",
            True,
        ),
    )
    bundle_checks = (
        ("served_bundle_legacy_file_upload_without_options", "let t=await ur(e);", True),
        ("served_bundle_legacy_export_md_filename", "filename:`transcript.md`", True),
        ("served_bundle_legacy_export_txt_filename", "filename:`transcript.txt`", True),
        ("served_bundle_legacy_export_json_filename", "filename:`transcript.json`", True),
        ("served_bundle_new_file_bearer_options", "bearerToken", False),
        ("served_bundle_new_export_identity", "filename:`transcript-", False),
    )

    expected_blob = git("rev-parse", f"HEAD:{BUNDLE_PATH.as_posix()}")
    worktree_blob = git("hash-object", BUNDLE_PATH.as_posix())
    print("G9 served-bundle audit")
    print(f"repository_head={git('rev-parse', 'HEAD')}")
    print(f"bundle_path={BUNDLE_PATH.as_posix()}")
    print(f"bundle_byte_size={bundle.stat().st_size}")
    print(f"bundle_git_blob_at_head={expected_blob}")
    print(f"bundle_worktree_blob={worktree_blob}")
    pinned = expected_blob == worktree_blob
    print(f"ASSERT label=served_bundle_matches_HEAD expected=true actual={str(pinned).lower()} result={'PASS' if pinned else 'FAIL'}")

    passed = pinned
    for label, path, needle, expected in source_checks:
        source_text = (REPO_ROOT / path).read_text(encoding="utf-8")
        passed = check(source_text, label, needle, expected) and passed
    for label, needle, expected in bundle_checks:
        passed = check(bundle_text, label, needle, expected) and passed
    print(f"OVERALL={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
