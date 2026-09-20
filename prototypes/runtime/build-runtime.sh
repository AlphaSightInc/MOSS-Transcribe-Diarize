#!/bin/bash
# Throwaway R4-7 runtime: no shared installs, no pin/module overrides.
set -euxo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PREFIX=/private/tmp/moss-round4-20260920/runtime-prefix
mkdir -p "$PREFIX/sources" "$ROOT/evidence/round4/runtime"
exec > >(tee "$ROOT/evidence/round4/runtime/build-runtime.log") 2>&1
cd "$PREFIX/sources"
[ -f sqlite-autoconf-3530400.tar.gz ] || curl -fL https://www.sqlite.org/2026/sqlite-autoconf-3530400.tar.gz -o sqlite-autoconf-3530400.tar.gz
tar -xzf sqlite-autoconf-3530400.tar.gz
cd sqlite-autoconf-3530400
./configure --prefix="$PREFIX/sqlite" --disable-static --enable-shared
make -j4
make install
"$PREFIX/sqlite/bin/sqlite3" --version
cd "$PREFIX/sources"
curl -fL https://www.python.org/ftp/python/3.12.12/Python-3.12.12.tgz -o Python-3.12.12.tgz
tar -xzf Python-3.12.12.tgz
cd Python-3.12.12
CPPFLAGS="-I$PREFIX/sqlite/include" LDFLAGS="-L$PREFIX/sqlite/lib -Wl,-rpath,$PREFIX/sqlite/lib" PKG_CONFIG_PATH="$PREFIX/sqlite/lib/pkgconfig" ./configure --prefix="$PREFIX/python" --with-openssl=/opt/homebrew/opt/openssl@3 --with-ensurepip=install
make -j4
make install
"$PREFIX/python/bin/python3.12" -c 'import sys,sqlite3,_sqlite3; print(sys.version); print(sqlite3.sqlite_version,_sqlite3.__file__); assert sqlite3.sqlite_version == "3.53.4"'
otool -L "$("$PREFIX/python/bin/python3.12" -c 'import _sqlite3;print(_sqlite3.__file__)')"
"$PREFIX/python/bin/python3.12" -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/python" -m pip install -e "$ROOT[dev,acceptance]"
# setuptools leaves ignored distribution metadata in the source tree. With the
# mandated PYTHONPATH=., nested wheel-install tests would then mistake the source
# checkout for an installed wheel and skip the wheel they are meant to inspect.
if [ -d "$ROOT/moss_transcribe_diarize.egg-info" ]; then
  mv "$ROOT/moss_transcribe_diarize.egg-info" "$PREFIX/editable-source-metadata.egg-info"
fi
