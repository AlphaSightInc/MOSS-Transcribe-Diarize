"""Restore original F4 defects temporarily; new behavior tests must fail; always restore."""
import os, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[3]
paths=[root/'frontend/src/capture/captureClient.ts',root/'frontend/src/components/ControlPanel.tsx']
saved={p:p.read_bytes() for p in paths}
try:
    for p in paths:p.write_bytes(subprocess.check_output(['git','show',f'b7695017:{p.relative_to(root)}'],cwd=root))
    env={**os.environ,'TMPDIR':str(root/'evidence/mvpfix/wp3/tmp')}
    run=subprocess.run(['npm','--prefix','frontend','test','--','--run','src/components/ControlPanel.captureFailure.test.tsx'],cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (root/'evidence/mvpfix/wp3/frontend-restored-defects.log').write_bytes(run.stdout)
    print('original defects restored, test exit:',run.returncode)
    assert run.returncode!=0,'tests did not detect original defects'
finally:
    for p,content in saved.items():p.write_bytes(content)
