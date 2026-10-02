"""Run requested A3/A5 retained checks; redirect only their writes into A4 evidence."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EV = Path.home() / 'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A4'

checker = HERE.parent / 'a3/verify_retained.py'
source = checker.read_text().replace(
    'EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P73/a3/retained"',
    'EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A4/a3-retained"')
exec(compile(source, str(checker), 'exec'), {'__file__': str(checker), '__name__': '__main__'})

checker = HERE.parent / 'a5/product_check.py'
sys.path.insert(0, str(checker.parent))
# Original prototype receipts remain read-only. Only the current-product receipts and
# rerun checker outputs move; all assertions and scoring rules remain unchanged.
source = checker.read_text().replace(
    '(EV / "product-transitions.json")', '(A4_EV / "product-transitions.json")').replace(
    'moss-gemini/evidence/R5B-FIX5A/product-retained',
    'moss-gemini/evidence/R5B-A4/a5-retained').replace(
    '(EV / "product-retained/product-check.json")',
    '(A4_EV / "a5-retained/product-check.json")').replace(
    '(EV / "product-retained/stress-metrics.json")',
    '(A4_EV / "a5-retained/stress-metrics.json")')
exec(compile(source, str(checker), 'exec'),
     {'__file__': str(checker), '__name__': '__main__', 'A4_EV': EV})
print('A4 retained A3/A5 checks PASS; amended T4 qualification is in core/pipeline receipts.')
