"""Verification-only path relocation; restores every edited byte in finally.
Usage: supplied-python contained-run.py ROOT OUTPUT_PREFIX [pytest paths...]
Runs unchanged assertions/algorithms. Only hardcoded /tmp destinations move.
"""
import difflib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
paths = sys.argv[3:] or ['tests']
assert root == Path.cwd().resolve()
(root / '.wp9runtime/t').mkdir(parents=True, exist_ok=True)
(root / '.wp9runtime/tmp').mkdir(parents=True, exist_ok=True)
files = list((root / 'tests').rglob('*.py')) + [root / 'moss_transcribe_diarize/phase2_acceptance_external.py']
def relocate(source):
    updated = source.replace('Path("/tmp")', 'Path(".wp9runtime/t")').replace('dir="/tmp"', 'dir=".wp9runtime/t"')
    if 'dir="/tmp"' in source:
        updated = updated.replace('Path(directory)', 'Path(__import__("os").path.relpath(directory))')
    return updated

originals = {}
patch = []
for file in files:
    source = file.read_text()
    updated = relocate(source)
    if updated != source:
        originals[file] = file.read_bytes()
        patch.extend(difflib.unified_diff(source.splitlines(True), updated.splitlines(True), fromfile=str(file.relative_to(root)), tofile=str(file.relative_to(root))))
screenshots = {p: p.read_bytes() for p in (root / 'evidence/mvpfix/wp2').glob('production-*.png')}
output.with_suffix('.containment.json').write_text(json.dumps({'patch': ''.join(patch)}, indent=2) + '\n')
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH='.', TMPDIR=str(root / '.wp9runtime/tmp'), npm_config_cache=str(root / '.wp9runtime/npm-cache'))
env['PYTEST_ADDOPTS'] = f'--basetemp={root}/.wp9runtime/pytest-{output.name} --junitxml={output}.xml --tb=short'
command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *paths]
try:
    for file, source in originals.items():
        file.write_text(relocate(source.decode()))
    with output.with_suffix('.log').open('w') as log:
        log.write(f'cwd={root}\ncommand={command!r}\nPYTEST_ADDOPTS={env["PYTEST_ADDOPTS"]}\n')
        log.flush()
        result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
finally:
    for file, source in originals.items():
        file.write_bytes(source)
    for file, source in screenshots.items():
        file.write_bytes(source)
print(f'{output.name}: exit={result.returncode}; restored {len(originals)} path-relocated files and {len(screenshots)} screenshots')
sys.exit(result.returncode)
