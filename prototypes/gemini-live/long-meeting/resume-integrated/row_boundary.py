"""One-command real projector boundary probe, evidence only, no listener/provider."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EV = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume-merge")
entry = Path(__file__).with_name("row-boundary.ts")
config = {"configFile": False, "build": {"outDir": str(EV / "row-boundary-bundle"),
    "emptyOutDir": True, "lib": {"entry": str(entry), "formats": ["es"], "fileName": "row-boundary"}}}
js = "import {build} from './frontend/node_modules/vite/dist/node/index.js'; await build(" + json.dumps(config) + ");"
subprocess.run(["/opt/homebrew/bin/node", "--input-type=module", "-e", js], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
subprocess.run(["/opt/homebrew/bin/node", str(EV / "row-boundary-bundle/row-boundary.mjs")], cwd=ROOT, check=True)
