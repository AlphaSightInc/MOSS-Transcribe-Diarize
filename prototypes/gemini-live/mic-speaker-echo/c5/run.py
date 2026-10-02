"""C5 recorded attack/custody replay. Run from the worktree; no provider calls."""
import json
import os
from pathlib import Path
import subprocess
import sys

EV = Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX5B'
mode = sys.argv[1] if len(sys.argv) > 1 else 'product'
assert mode in ('baseline', 'prototype', 'product')
checks = [EV/'one_word_seam.py', EV/'weak_ambiguity.py'] + sorted((EV/'attacks').glob('*.py')) + sorted((EV/'copied').rglob('*.py'))
results = []
for probe in checks:
    log = EV/mode/(probe.parent.name+'-'+probe.stem+'.log')
    with log.open('w') as out:
        result = subprocess.run([sys.executable, str(EV/'launch.py'), mode, str(probe)],
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}, stdout=out, stderr=out)
    results.append({'probe':str(probe), 'returncode':result.returncode, 'log':str(log)})
    print(json.dumps(results[-1]), flush=True)
(EV/mode/'probes.json').write_text(json.dumps(results, indent=1)+'\n')
assert all(r['returncode'] == 0 for r in results), [r for r in results if r['returncode']]

if mode != 'baseline' and '--probes-only' not in sys.argv:
    subprocess.run([sys.executable, str(EV/mode/'frozen/product_verify_all.py')], check=True)
    subprocess.run([sys.executable, str(EV/mode/'compare_frozen.py')], check=True)
