#!/usr/bin/env bash
# One command for the policy reducer and the candidate-owned Linux SQLite runtime falsifier.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIRTY="$(git -C "${ROOT}" status --porcelain=v1 --untracked-files=all -- . ':(exclude)evidence/phase2/**')"
[ -z "${DIRTY}" ] || {
  echo '{"runtime_probe":"FAIL","reason":"scoped candidate source is dirty"}' >&2
  exit 1
}
PYTHONDONTWRITEBYTECODE=1 "${ROOT}/.venv/bin/python" \
  "${ROOT}/prototypes/phase2-wave1-qualification/probe.py"

command -v docker >/dev/null 2>&1 || {
  echo '{"runtime_probe":"FAIL","reason":"docker unavailable"}' >&2
  exit 1
}

ARTIFACT_ROOT="$(mktemp -d)"
trap 'rm -rf -- "${ARTIFACT_ROOT}"' EXIT
SOURCE_COPY="${ARTIFACT_ROOT}/source"
mkdir -p "${SOURCE_COPY}"
tar --exclude=.git --exclude=.venv --exclude=node_modules --exclude=build --exclude=dist \
  --exclude=evidence -C "${ROOT}" -cf - . | tar -C "${SOURCE_COPY}" -xf -
"${ROOT}/.venv/bin/python" - "${ROOT}" "${SOURCE_COPY}" <<'PY'
import hashlib
import json
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
source = pathlib.Path(sys.argv[2])
git = lambda *args: subprocess.check_output(("git", *args), cwd=root, text=True).strip()
payload = {
    "schema": "moss-phase2-acceptance.v1",
    "git_sha": git("rev-parse", "HEAD"),
    "git_tree": git("rev-parse", "HEAD^{tree}"),
    "uv_lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
    "fixtures": {
        "quality_corpus_manifest": hashlib.sha256(
            (root / "evidence/live-policy-sweep-20260825/corpus/corpus-manifest.json").read_bytes()
        ).hexdigest(),
        "concurrency_fixture": hashlib.sha256(
            (root / "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json").read_bytes()
        ).hexdigest(),
        "concurrency_preregistration": hashlib.sha256(
            (root / "prototypes/streaming-diarization/concurrency/preregistration.json").read_bytes()
        ).hexdigest(),
    },
}
(source / "moss_transcribe_diarize" / "build_candidate.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
uv build --wheel --out-dir "${ARTIFACT_ROOT}" "${SOURCE_COPY}" >/dev/null
WHEEL="$(find "${ARTIFACT_ROOT}" -maxdepth 1 -name '*.whl' -print -quit)"
[ -n "${WHEEL}" ] || { echo '{"runtime_probe":"FAIL","reason":"wheel absent"}' >&2; exit 1; }

docker run --rm \
  -v "${ARTIFACT_ROOT}:/candidate:ro" \
  ubuntu:24.04 bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3.12 python3.12-venv curl build-essential ca-certificates >/dev/null
work="$(mktemp -d)"
curl -fsSLo "${work}/sqlite.tar.gz" https://www.sqlite.org/2026/sqlite-autoconf-3530400.tar.gz
python3.12 - "${work}/sqlite.tar.gz" <<"PY"
import hashlib, pathlib, sys
expected = "454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338"
actual = hashlib.sha3_256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()
assert actual == expected, (actual, expected)
PY
tar -xzf "${work}/sqlite.tar.gz" -C "${work}"
cd "${work}/sqlite-autoconf-3530400"
./configure --prefix="${work}/runtime" --disable-static --enable-shared >/dev/null
make -j2 >/dev/null
make install >/dev/null

default_version="$(python3.12 -c "import sqlite3; print(sqlite3.sqlite_version)")"
test "${default_version}" != 3.53.4
python3.12 -m venv "${work}/venv"
"${work}/venv/bin/pip" install -q aiosqlite==0.22.1 starlette anyio typing_extensions /candidate/*.whl --no-deps

wrong_parent="${work}/wrong/parent"
set +e
"${work}/venv/bin/python" - "${wrong_parent}" <<"PY"
import asyncio, pathlib, sys
from moss_transcribe_diarize.app.phase2 import Phase2Store
asyncio.run(Phase2Store.open(pathlib.Path(sys.argv[1]) / "moss.sqlite3"))
PY
wrong_status=$?
set -e
test "${wrong_status}" -ne 0
test ! -e "${wrong_parent}"

export LD_LIBRARY_PATH="${work}/runtime/lib"
"${work}/venv/bin/python" - "${work}/exact/moss.sqlite3" <<"PY"
import asyncio, json, pathlib, sqlite3, sys
from moss_transcribe_diarize.app.phase2 import Phase2Store
import csv, io, zipfile
from moss_transcribe_diarize.installed_candidate import (
    installed_candidate_identity,
    installed_dependency_projection,
    installed_record_identity,
    record_projection_sha256,
)

path = pathlib.Path(sys.argv[1])
async def once():
    store = await Phase2Store.open(path)
    try:
        values = {
            "foreign_keys": (await (await store._connection.execute("PRAGMA foreign_keys")).fetchone())[0],
            "journal_mode": (await (await store._connection.execute("PRAGMA journal_mode")).fetchone())[0],
            "synchronous": (await (await store._connection.execute("PRAGMA synchronous")).fetchone())[0],
            "user_version": await store.user_version(),
        }
        return values
    finally:
        await store.close()

first = asyncio.run(once())
second = asyncio.run(once())
with zipfile.ZipFile(next(pathlib.Path("/candidate").glob("*.whl"))) as archive:
    record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
    wheel_record_projection = record_projection_sha256(
        csv.reader(io.StringIO(archive.read(record_name).decode()))
    )
state = {
    "sqlite_runtime": sqlite3.sqlite_version,
    "aiosqlite": __import__("aiosqlite").__version__,
    "installed_candidate": installed_candidate_identity(),
    "installed_record": installed_record_identity(),
    "dependency_projection_sha256": installed_dependency_projection()["sha256"],
    "first": first,
    "restart": second,
    "wheel_installed": True,
    "wrong_runtime_refused_without_parent": True,
}
print(json.dumps(state, sort_keys=True))
assert sqlite3.sqlite_version == "3.53.4"
assert state["installed_candidate"] and len(state["installed_candidate"]["git_sha"]) == 40
assert state["installed_record"]["record_projection_sha256"] == wheel_record_projection
assert first == second == {"foreign_keys": 1, "journal_mode": "wal", "synchronous": 2, "user_version": 1}
PY
echo "{\"runtime_probe\":\"PASS\",\"default_sqlite\":\"${default_version}\",\"exact_sqlite\":\"3.53.4\"}"
'
