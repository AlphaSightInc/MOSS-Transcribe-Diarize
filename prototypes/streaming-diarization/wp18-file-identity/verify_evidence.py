"""Reproduce the identity falsifier without GPU calls; do not certify a repair."""
import json
from pathlib import Path
import subprocess
import sys

root = Path('evidence/mvpfix/wp18')
fresh = Path('.wp18runtime/fresh-evidence')
completed = subprocess.run([sys.executable, str(Path(__file__).with_name('probe.py')), '--output', str(fresh)],
                           capture_output=True, text=True)
Path('.wp18runtime/fresh-probe.log').write_text(completed.stdout + completed.stderr)
assert completed.returncode == 0, 'offline replay failed; see fresh-probe.log'
for case in ('fake-1-False', 'fake-1-True', 'fake-2-False', 'fake-2-True', 'real-False', 'real-True'):
    expected = json.loads((root / (case + '.json')).read_text())
    observed = json.loads((fresh / (case + '.json')).read_text())
    expected.pop('elapsed', None)
    observed.pop('elapsed', None)
    assert observed == expected, case
    print(case, 'identities', observed['resolver_identities'], 'stitched', observed['stitched_identities'])
summary = json.loads((root / 'summary.json').read_text())
assert summary['decoder_requests'] == 3 and summary['identity_fix_shipped'] is False
assert summary['baseline_identities'] == summary['enabled_identities'] == 7
assert summary['reference_voices'] == 3
print('PASS: 6/6 exact resolver replay comparisons; identity repair remains FALSIFIED; GPU calls 0')
