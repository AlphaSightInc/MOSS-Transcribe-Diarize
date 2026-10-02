"""Re-run frozen F1/A2 checks on the retained product; all writes stay in A3 evidence."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P73/a3/retained"
EV.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(HERE.parent / "a2"), str(HERE.parent / "f1")]
import product_check
import stress_metrics

product_check.EV = EV
product_check.degraded.EV = EV
stress_metrics.EV = EV
product_check.main()
stress_metrics.main()
result = subprocess.run([sys.executable, str(HERE.parent / "f1/final_check.py")], capture_output=True, text=True, check=True)
(EV / "f1-final-check.log").write_text(result.stdout)
print("F1", result.stdout.strip())
report = json.loads((EV / "product-check.json").read_text())
assert report["captured"]["total"] == 2749
print("RETAINED PRODUCT F1/A2 PASS")
