#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
export TMPDIR="$PWD/.wp12/tmp" npm_config_cache="$PWD/.wp12/npm-cache"
npm --prefix frontend test -- --run --configLoader runner
npm --prefix frontend run typecheck
npm --prefix frontend run build -- --configLoader runner
