"""Durability regressions; real stores supplied as private copies, never committed.

WP31_COPIED_STORES points at a copied-store directory. Without these private inputs,
only fabricated refusal controls run. No source runtime/original is opened here.
"""
import os
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from moss_transcribe_diarize.app.phase2 import SchemaVersionError, create_phase2_app


@pytest.mark.parametrize('version', [1, 3, 999])
def test_incompatible_schema_refuses_without_mutation(tmp_path, version):
    path = tmp_path / 'phase2.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE preserved(value TEXT)')
        db.execute("INSERT INTO preserved VALUES ('public refusal control')")
        db.execute(f'PRAGMA user_version={version}')
    before = path.read_bytes()
    with pytest.raises(SchemaVersionError, match=f'user_version={version}; expected 2'):
        with TestClient(create_phase2_app(database_path=path, file_work_root=tmp_path / 'file-work',
                                         meeting_audio_root=tmp_path / 'meeting-audio')):
            pytest.fail('Incompatible store reached serving state')
    assert path.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} == {'phase2.sqlite'}


def test_corrupt_header_refuses_without_mutation(tmp_path):
    path = tmp_path / 'phase2.sqlite'
    path.write_bytes(b'not a SQLite database\0' * 100)
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError, match='file is not a database'):
        with TestClient(create_phase2_app(database_path=path, file_work_root=tmp_path / 'file-work',
                                         meeting_audio_root=tmp_path / 'meeting-audio')):
            pytest.fail('Incompatible store reached serving state')
    assert path.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} == {'phase2.sqlite'}


COPIED_ROOT = Path(os.environ.get('WP31_COPIED_STORES', '.wp31/idle-backups'))
COPIES = sorted(COPIED_ROOT.glob('*/phase2.sqlite'))


@pytest.mark.parametrize('source', COPIES or [None], ids=[p.parent.name for p in COPIES] or ['private-stores-unavailable'])
def test_real_copied_store_reopens_without_content_loss(source, tmp_path):
    if source is None:
        pytest.skip('Set WP31_COPIED_STORES to private copied real stores')
    destination = tmp_path / 'copy'
    shutil.copytree(source.parent, destination)
    database = destination / 'phase2.sqlite'
    def content():
        with sqlite3.connect(database) as db:
            return {table: db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()
                    for table in ('meeting_transcripts', 'meeting_speakers', 'voiceprints', 'voiceprint_samples')}
    before = content()
    app = create_phase2_app(database_path=database, file_work_root=destination / 'file-work',
                            meeting_audio_root=destination / 'meeting-audio')
    with TestClient(app, base_url='https://moss.test'):
        assert content() == before
        with sqlite3.connect(database) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            audio = db.execute("SELECT relative_path,byte_count FROM meeting_audio WHERE state IN ('available','partial')").fetchall()
        assert all((destination / 'meeting-audio' / path).stat().st_size == size for path, size in audio)
    assert content() == before
