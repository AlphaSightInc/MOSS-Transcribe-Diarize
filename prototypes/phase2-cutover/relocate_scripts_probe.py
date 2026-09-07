"""Installer prototype: relocate generated scripts without losing RECORD verification.

Run: .venv/bin/python prototypes/phase2-cutover/relocate_scripts_probe.py WHEEL
Question: can a moved venv preserve executable interpreter paths and installed
RECORD truth? Minimal change: rewrite installer-owned script prefixes and their
RECORD rows, not packaged modules. Falsifier: direct CLI or full RECORD fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from moss_transcribe_diarize.installed_candidate import relocate_installed_console_scripts


if __name__ == "__main__":
    if sys.argv[1] == "--rewrite":
        print("rewritten", relocate_installed_console_scripts(Path(sys.argv[2])))
        raise SystemExit(0)
    with tempfile.TemporaryDirectory(prefix="moss-script-relocation-") as directory:
        stage, final = Path(directory) / "stage", Path(directory) / "release"
        subprocess.run([sys.executable, "-m", "venv", str(stage)], check=True)
        subprocess.run(["uv", "pip", "install", "--python", str(stage / "bin/python"), "--no-deps", sys.argv[1]], check=True)
        stage.rename(final)
        broken = False
        try:
            subprocess.run([str(final / "bin/mtd-phase2-web"), "--help"], check=True, capture_output=True)
        except FileNotFoundError:
            broken = True
        final.rename(stage)
        subprocess.run([str(stage / "bin/python"), str(Path(__file__).resolve()), "--rewrite", str(final)], check=True)
        stage.rename(final)
        environment = {**os.environ, "PYTHONPATH": sysconfig.get_paths()["purelib"]}
        cli = subprocess.run([str(final / "bin/mtd-phase2-web"), "--help"], env=environment, capture_output=True)
        record = subprocess.run([str(final / "bin/python"), "-I", "-c", "from moss_transcribe_diarize.installed_candidate import installed_record_identity; print(installed_record_identity())"], capture_output=True)
        print(json.dumps({"before_move_back_cli_broken": broken, "after_cli_exit": cli.returncode, "after_full_record_exit": record.returncode}))
        if cli.returncode:
            print(cli.stderr.decode())
        if record.returncode:
            print(record.stderr.decode())
        assert broken and cli.returncode == record.returncode == 0
