"""THROWAWAY: print H2-A host symptoms and local production-seam controls."""
import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RAW = Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/r6-h1-20260923T051306Z/20260923T051605Z-f7fe4ad/raw")


def raw(layer, gate, predicate):
    name = f"{layer}--{gate}--{predicate}.json"
    return json.loads((RAW / f"{layer}-collector" / name).read_text())["raw"]


def main():
    host = {}
    for layer in ("deployed", "pre_admission"):
        stderr = (RAW / f"measure-{layer}.stderr").read_text()
        host[layer] = {
            "artifact_collision_exceptions": stderr.count("FileExistsError:"),
            "overload": raw(layer, "G4", "excess_admission_overload"),
            "zero_work_end": raw(layer, "G0", "zero_work_end"),
            "browser_workspace_pass": raw(layer, "G2", "browser_workspace_identity").get("nonempty_saved_history"),
        }
    host["browser_prototype_returncode"] = json.loads((RAW / "prototype-browser-workspace.json").read_text())["returncode"]
    focused = subprocess.run([
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "tests/phase2/test_h2a_harness_artifacts.py", "tests/phase2/test_h2a_browser_workspace_probe.py",
    ], cwd=REPO, capture_output=True, text=True, check=False)
    print(json.dumps({"host": host, "local_test_returncode": focused.returncode,
                      "local_test_output": focused.stdout.strip()}, indent=2, sort_keys=True))
    raise SystemExit(focused.returncode)


if __name__ == "__main__":
    main()
