#!/usr/bin/env bash
# Strong-construct one inert Account candidate beside the live service. Issue #23 activates it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
. "${SCRIPT_DIR}/moss-ops-lib.sh"

[ -f "${MOSS_CANDIDATE_WHEEL:-}" ] || die "MOSS_CANDIDATE_WHEEL must name a clean candidate wheel"
require_cmd /usr/bin/python3.12 cmp git getent uv

LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
RUNTIME_ROOT="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize"
SQLITE_PREFIX="${RUNTIME_ROOT}/sqlite-3.53.4"
RELEASES_DIR="${RUNTIME_ROOT}/account-runtimes"
CHECKOUTS_DIR="${RUNTIME_ROOT}/candidate-checkouts"
MANIFESTS_DIR="${RUNTIME_ROOT}/candidate-manifests"
CHECKOUT_STAGE=""
RELEASE_STAGE=""
MANIFEST_STAGE=""

cleanup_stages() {
  local status=$?
  [ -z "${CHECKOUT_STAGE}" ] || rm -rf -- "${CHECKOUT_STAGE}"
  [ -z "${RELEASE_STAGE}" ] || rm -rf -- "${RELEASE_STAGE}"
  [ -z "${MANIFEST_STAGE}" ] || rm -f -- "${MANIFEST_STAGE}"
  exit "${status}"
}
trap cleanup_stages EXIT

readarray -t CANDIDATE_IDENTITY < <(/usr/bin/python3.12 -I - "${MOSS_CANDIDATE_WHEEL}" <<'PY'
import json
import csv
import hashlib
import io
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    value = json.loads(archive.read("moss_transcribe_diarize/build_candidate.json"))
    records = [name for name in archive.namelist() if name.endswith(".dist-info/RECORD")]
    if len(records) != 1:
        raise SystemExit("candidate wheel RECORD is missing")
    rows = list(csv.reader(io.StringIO(archive.read(records[0]).decode())))
for key in ("git_sha", "git_tree", "uv_lock_sha256"):
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise SystemExit(f"candidate wheel {key} is missing")
    print(item)
fixtures = value.get("fixtures")
if not isinstance(fixtures, dict):
    raise SystemExit("candidate wheel fixtures are missing")
print(json.dumps(fixtures, sort_keys=True, separators=(",", ":")))
installer_owned = {"INSTALLER", "REQUESTED", "direct_url.json", "uv_cache.json"}
projected = sorted(
    row
    for row in rows
    if len(row) == 3
    and row[1]
    and not row[0].startswith(("bin/", "../../../bin/"))
    and not row[0].endswith(".pyc")
    and row[0].rsplit("/", 1)[-1] not in installer_owned
)
projection = json.dumps(projected, separators=(",", ":")).encode()
print(hashlib.sha256(projection).hexdigest())
PY
)
CANDIDATE_SHA="${CANDIDATE_IDENTITY[0]}"
CANDIDATE_TREE="${CANDIDATE_IDENTITY[1]}"
CANDIDATE_LOCK="${CANDIDATE_IDENTITY[2]}"
CANDIDATE_FIXTURES="${CANDIDATE_IDENTITY[3]}"
CANDIDATE_RECORD="${CANDIDATE_IDENTITY[4]}"
[ "$(git -C "${PROJECT_DIR}" rev-parse "${CANDIDATE_SHA}^{tree}")" = "${CANDIDATE_TREE}" ] || \
  die "candidate wheel tree is not present in this repository"

RELEASE="${RELEASES_DIR}/${CANDIDATE_SHA}"
CHECKOUT="${CHECKOUTS_DIR}/${CANDIDATE_SHA}"
MANIFEST="${MANIFESTS_DIR}/${CANDIDATE_SHA}.json"
mkdir -p "${RELEASES_DIR}" "${CHECKOUTS_DIR}" "${MANIFESTS_DIR}"
chmod 0700 "${RELEASES_DIR}" "${CHECKOUTS_DIR}" "${MANIFESTS_DIR}"

if [ ! -d "${CHECKOUT}/.git" ]; then
  CHECKOUT_STAGE="$(mktemp -d "${CHECKOUTS_DIR}/.${CANDIDATE_SHA}.stage.XXXXXX")"
  rmdir "${CHECKOUT_STAGE}"
  git clone --quiet --no-local "${PROJECT_DIR}" "${CHECKOUT_STAGE}"
  git -C "${CHECKOUT_STAGE}" checkout --quiet --detach "${CANDIDATE_SHA}"
  [ -z "$(git -C "${CHECKOUT_STAGE}" status --porcelain=v1 --untracked-files=all)" ] || \
    die "candidate checkout construction became dirty"
  mv "${CHECKOUT_STAGE}" "${CHECKOUT}"
  CHECKOUT_STAGE=""
fi
[ "$(git -C "${CHECKOUT}" rev-parse HEAD)" = "${CANDIDATE_SHA}" ] || die "candidate checkout SHA mismatch"
[ -z "$(git -C "${CHECKOUT}" status --porcelain=v1 --untracked-files=all)" ] || \
  die "reused candidate checkout is dirty"

# The exact candidate owns the runtime builder too.  Never execute deployment
# machinery from the invoking checkout after candidate identity is known.
"${CHECKOUT}/ops/build-account-sqlite.sh"

if [ ! -d "${RELEASE}" ]; then
  RELEASE_STAGE="$(mktemp -d "${RELEASES_DIR}/.${CANDIDATE_SHA}.stage.XXXXXX")"
  /usr/bin/python3.12 -m venv "${RELEASE_STAGE}"
  uv export --directory "${CHECKOUT}" --frozen --extra acceptance --no-emit-project \
    --format requirements-txt --output-file "${RELEASE_STAGE}/locked-requirements.txt"
  "${RELEASE_STAGE}/bin/pip" install --require-hashes \
    -r "${RELEASE_STAGE}/locked-requirements.txt"
  "${RELEASE_STAGE}/bin/pip" install --no-deps "${MOSS_CANDIDATE_WHEEL}"
  rm "${RELEASE_STAGE}/locked-requirements.txt"
  # Verify the complete pip installation before the candidate-owned shell
  # launchers take ownership of two generated console-script paths.
  LD_LIBRARY_PATH="${SQLITE_PREFIX}/lib" \
    "${RELEASE_STAGE}/bin/python" -I - "${CANDIDATE_SHA}" "${CANDIDATE_TREE}" "${CANDIDATE_LOCK}" "${CANDIDATE_FIXTURES}" "${CANDIDATE_RECORD}" <<'PY'
import json
import sqlite3
import sys
from moss_transcribe_diarize.installed_candidate import installed_candidate_identity, installed_record_identity

identity = installed_candidate_identity()
assert sqlite3.sqlite_version == "3.53.4"
assert identity == {
    "git_sha": sys.argv[1],
    "git_tree": sys.argv[2],
    "uv_lock_sha256": sys.argv[3],
    "fixtures": json.loads(sys.argv[4]),
}
record = installed_record_identity()
assert record["record_entries_verified"] > 0
assert record["record_projection_sha256"] == sys.argv[5]
PY
  install -m 0555 "${CHECKOUT}/ops/account-web-launcher.sh" "${RELEASE_STAGE}/bin/mtd-account-web"
  install -m 0555 "${CHECKOUT}/ops/account-admin-launcher.sh" "${RELEASE_STAGE}/bin/mtd-admin"
  install -m 0555 "${CHECKOUT}/ops/account-cutover-launcher.sh" "${RELEASE_STAGE}/bin/mtd-phase2-cutover"
  install -m 0555 "${CHECKOUT}/ops/vllm-launcher.sh" "${RELEASE_STAGE}/bin/mtd-vllm"
  LD_LIBRARY_PATH="${SQLITE_PREFIX}/lib" \
    "${RELEASE_STAGE}/bin/python" -I - "${CANDIDATE_RECORD}" <<'PY'
import sys
from moss_transcribe_diarize.installed_candidate import installed_project_record_identity

record = installed_project_record_identity()
assert record["record_projection_verified"] is True
assert record["record_projection_sha256"] == sys.argv[1]
PY
  chmod -R a-w "${RELEASE_STAGE}"
  mv "${RELEASE_STAGE}" "${RELEASE}"
  RELEASE_STAGE=""
fi
cmp -s "${CHECKOUT}/ops/account-web-launcher.sh" "${RELEASE}/bin/mtd-account-web" || \
  die "Account web launcher differs from the detached candidate checkout"
cmp -s "${CHECKOUT}/ops/account-admin-launcher.sh" "${RELEASE}/bin/mtd-admin" || \
  die "Account admin launcher differs from the detached candidate checkout"
cmp -s "${CHECKOUT}/ops/account-cutover-launcher.sh" "${RELEASE}/bin/mtd-phase2-cutover" || \
  die "Account cutover launcher differs from the detached candidate checkout"
cmp -s "${CHECKOUT}/ops/vllm-launcher.sh" "${RELEASE}/bin/mtd-vllm" || \
  die "vLLM launcher differs from the detached candidate checkout"
PYTHONDONTWRITEBYTECODE=1 LD_LIBRARY_PATH="${SQLITE_PREFIX}/lib" \
  "${RELEASE}/bin/python" -I - "${CANDIDATE_SHA}" <<'PY'
import sqlite3
import sys
from moss_transcribe_diarize.installed_candidate import (
    installed_candidate_identity,
    installed_project_record_identity,
)

assert sqlite3.sqlite_version == "3.53.4"
assert installed_candidate_identity()["git_sha"] == sys.argv[1]
assert installed_project_record_identity()["record_entries_verified"] > 0
PY

if [ ! -L "${CHECKOUT}/.venv" ]; then
  ln -s "${RELEASE}" "${CHECKOUT}/.venv"
fi
[ "$(readlink "${CHECKOUT}/.venv")" = "${RELEASE}" ] || die "candidate checkout runtime mismatch"

if [ ! -e "${MANIFEST}" ]; then
  MANIFEST_STAGE="$(mktemp "${MANIFESTS_DIR}/.${CANDIDATE_SHA}.manifest.XXXXXX")"
  LD_LIBRARY_PATH="${SQLITE_PREFIX}/lib" "${RELEASE}/bin/python" -I - \
    "${MANIFEST_STAGE}" "${MANIFEST}" "${MOSS_CANDIDATE_WHEEL}" "${CANDIDATE_SHA}" "${CANDIDATE_TREE}" \
    "${CANDIDATE_LOCK}" "${CANDIDATE_FIXTURES}" "${CANDIDATE_RECORD}" "${RELEASE}" "${CHECKOUT}" "${SQLITE_PREFIX}" <<'PY'
import hashlib
import json
import pathlib
import sqlite3
import sys
from moss_transcribe_diarize.installed_candidate import (
    installed_dependency_projection,
    installed_project_record_identity,
    publish_candidate_manifest,
)

manifest_stage, manifest, wheel, sha, tree, lock, fixtures, record, release, checkout, sqlite_prefix = sys.argv[1:]
payload = {
    "schema": "moss-account-candidate.v1",
    "git_sha": sha,
    "git_tree": tree,
    "uv_lock_sha256": lock,
    "fixtures": json.loads(fixtures),
    "wheel_sha256": hashlib.sha256(pathlib.Path(wheel).read_bytes()).hexdigest(),
    "wheel_record_projection_sha256": record,
    "installed_record": installed_project_record_identity(),
    "dependency_projection": installed_dependency_projection(),
    "sqlite_runtime": sqlite3.sqlite_version,
    "sqlite_prefix": sqlite_prefix,
    "release": release,
    "release_launcher": f"{release}/bin/mtd-account-web",
    "release_launcher_sha256": hashlib.sha256(
        pathlib.Path(release, "bin/mtd-account-web").read_bytes()
    ).hexdigest(),
    "release_admin_launcher": f"{release}/bin/mtd-admin",
    "release_admin_launcher_sha256": hashlib.sha256(
        pathlib.Path(release, "bin/mtd-admin").read_bytes()
    ).hexdigest(),
    "release_cutover_launcher": f"{release}/bin/mtd-phase2-cutover",
    "release_cutover_launcher_sha256": hashlib.sha256(
        pathlib.Path(release, "bin/mtd-phase2-cutover").read_bytes()
    ).hexdigest(),
    "release_vllm_launcher": f"{release}/bin/mtd-vllm",
    "release_vllm_launcher_sha256": hashlib.sha256(
        pathlib.Path(release, "bin/mtd-vllm").read_bytes()
    ).hexdigest(),
    "qualification_checkout": checkout,
    "qualification_command": f"cd {checkout} && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/phase2-acceptance/run.py",
    "web_unit_path": f"{checkout}/ops/systemd/moss-web.service",
    "web_unit_sha256": hashlib.sha256(
        pathlib.Path(checkout, "ops/systemd/moss-web.service").read_bytes()
    ).hexdigest(),
    "vllm_unit_path": f"{checkout}/ops/systemd/moss-vllm.service",
    "vllm_unit_sha256": hashlib.sha256(
        pathlib.Path(checkout, "ops/systemd/moss-vllm.service").read_bytes()
    ).hexdigest(),
    "vllm_activation_rule": "unit_bytes_and_profile_only; preserve pid, argv, and ActiveEnterTimestamp",
    "activation_state": "staged_inert",
}
publish_candidate_manifest(pathlib.Path(manifest_stage), pathlib.Path(manifest), payload)
PY
  MANIFEST_STAGE=""
fi

LD_LIBRARY_PATH="${SQLITE_PREFIX}/lib" "${RELEASE}/bin/python" -I - \
  "${MANIFEST}" "${CANDIDATE_SHA}" "${RELEASE}" "${CHECKOUT}" <<'PY'
import json
import pathlib
import stat
import sys

from moss_transcribe_diarize.installed_candidate import validated_candidate_artifacts

path = pathlib.Path(sys.argv[1])
payload = json.loads(path.read_text())
assert payload["git_sha"] == sys.argv[2]
assert payload["release"] == sys.argv[3]
assert payload["qualification_checkout"] == sys.argv[4]
assert payload["activation_state"] == "staged_inert"
assert stat.S_IMODE(path.stat().st_mode) == 0o600
artifacts = validated_candidate_artifacts(payload)
assert artifacts.release == pathlib.Path(sys.argv[3]).resolve()
PY

evidence candidate_sha "${CANDIDATE_SHA}"
evidence candidate_manifest "${MANIFEST}"
evidence candidate_state staged_inert
unchanged "live service, live checkout, active runtime pointer, and GPU venv"
