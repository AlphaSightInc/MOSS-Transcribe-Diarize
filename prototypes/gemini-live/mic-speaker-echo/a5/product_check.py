"""Absorbed A5 bench: product transitions vs the pre-implementation prototype receipt."""
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
measure = SimpleNamespace(**runpy.run_path(str(HERE / "measure.py")))
EV = measure.EV
frozen = json.loads((EV / "transitions.json").read_text())["prototype"]
current = [measure.attack(measure.PRODUCT, lane, empty)
           for lane in ("system", "microphone") for empty in (False, True)]
current.append(measure.attack(measure.PRODUCT, revision_lanes=()))
current = json.loads(json.dumps(current))
assert current == frozen
(EV / "product-transitions.json").write_text(json.dumps(current, indent=2))
print("A5 product/prototype exact transition parity 5/5; hidden fresh words 0; Stop cuts empty", flush=True)

# Run the unchanged A3/F1/A2 checks; change only their evidence destination.
checker = (HERE.parent / "a3/verify_retained.py").read_text()
checker = checker.replace('EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P73/a3/retained"',
                          'EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX5A/product-retained"')
exec(compile(checker, str(HERE.parent / "a3/verify_retained.py"), "exec"),
     {"__file__": str(HERE.parent / "a3/verify_retained.py"), "__name__": "__main__"})

prototype = json.loads((EV / "prototype-retained/product-check.json").read_text())
product = json.loads((EV / "product-retained/product-check.json").read_text())
assert product["degraded"] == prototype["degraded"]
assert product["streams"] == prototype["streams"]
for cell, result in prototype["captured"]["cells"].items():
    timing = ("us_mean", "us_p99", "us_max")
    actual = product["captured"]["cells"][cell]["metrics"]["product"]
    expected = result["metrics"]["product"]
    assert {k: v for k, v in actual.items() if k not in timing} == {
        k: v for k, v in expected.items() if k not in timing}
for cell, result in prototype["stress"].items():
    assert product["stress"][cell]["product"]["lanes"] == result["product"]["lanes"]
assert json.loads((EV / "prototype-retained/stress-metrics.json").read_text()) == json.loads(
    (EV / "product-retained/stress-metrics.json").read_text())
print("A5 product vs prototype: all recorded text/fresh/re-shown metrics identical", flush=True)
