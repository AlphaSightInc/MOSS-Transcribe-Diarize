"""Reuse WP32's real finalizer/compositor/publication witness; now require correction."""
from pathlib import Path
source = Path('evidence/mvpfix/wp32/spec_probe.py')
code = source.read_text().rsplit('\nassert rows[0]', 1)[0]
namespace = {'__file__': str(source.resolve())}
exec(compile(code, str(source), 'exec'), namespace)
rows = namespace['rows']
assert all(row['actual'] == row['expected'] and row['applied'] and row['finalization'] == 'final' for row in rows)
