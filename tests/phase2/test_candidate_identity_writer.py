import base64
import csv
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

from moss_transcribe_diarize import candidate_identity as writer
from moss_transcribe_diarize import phase2_acceptance as acceptance


def test_recipe_and_qualification_round_trip_identical_embedded_identity(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'moss_transcribe_diarize').mkdir()
    (repo / 'uv.lock').write_text('lock')
    for path in writer.FIXTURE_PATHS.values():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{}')
    for args in (('init', '-q'), ('add', '.'),
                 ('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'fixture')):
        subprocess.run(('git', *args), cwd=repo, check=True)
    staged = tmp_path / 'staged'
    (staged / 'moss_transcribe_diarize').mkdir(parents=True)
    # The exact helper invocation used by the documented shell recipe.
    subprocess.run((sys.executable, writer.__file__, str(repo), str(staged)), check=True)
    payload = (staged / 'moss_transcribe_diarize/build_candidate.json').read_bytes()
    identity = json.loads(payload)
    identity = dict(reversed(list(identity.items())))
    identity['fixtures'] = dict(reversed(list(identity['fixtures'].items())))
    identity['dirty'] = False
    embedded = []

    def uv_build(argv, *, cwd, **kwargs):
        assert argv[:3] == ('uv', 'build', '--wheel')
        data = (cwd / 'moss_transcribe_diarize/build_candidate.json').read_bytes()
        embedded.append(data)
        wheel_dir = Path(argv[-1]); wheel_dir.mkdir()
        name = 'moss_transcribe_diarize/build_candidate.json'
        record = 'moss_transcribe_diarize-0.1.0.dist-info/RECORD'
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
        rows = io.StringIO()
        csv.writer(rows).writerows(((name, 'sha256=' + digest, len(data)), (record, '', '')))
        with zipfile.ZipFile(wheel_dir / 'candidate.whl', 'w') as archive:
            archive.writestr(name, data)
            archive.writestr(record, rows.getvalue())
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')

    monkeypatch.setattr(acceptance.subprocess, 'run', uv_build)
    bundle = acceptance.AttemptBundle(tmp_path / 'qualification')
    wheel, errors = acceptance.build_candidate_wheel(repo=repo, bundle=bundle, source_identity=identity)
    assert errors == [] and wheel is not None
    with zipfile.ZipFile(bundle.path / 'raw/candidate.whl') as archive:
        assert archive.read('moss_transcribe_diarize/build_candidate.json') == payload == embedded[0]
    assert json.loads(payload) == {k: v for k, v in identity.items() if k != 'dirty'}
    recipe = Path(writer.__file__).parents[1] / 'prototypes/phase2-wave1-qualification/run.sh'
    assert '"${ROOT}/moss_transcribe_diarize/candidate_identity.py"' in recipe.read_text()
    assert 'json.dumps' not in recipe.read_text().split('uv build --wheel')[0]
