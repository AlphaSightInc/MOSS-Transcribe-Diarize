# R4-10 re-freeze checklist

This is a command recipe, not evidence that re-freeze or network validation ran.
The lead owns the lease, tunnel, tag, push, and integration fast-forward.

## 1. Pin one accepted product SHA

```sh
export CANDIDATE=/Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate
export FROZEN_SHA=<full-accepted-round4-closure-SHA>
export FREEZE_DATE=<YYYYMMDD>
export FREEZE_TAG="round4-closure-frozen-${FREEZE_DATE}"
export FROZEN_SHORT="$(printf '%s' "$FROZEN_SHA" | cut -c1-8)"
test "$(git -C "$CANDIDATE" rev-parse "$FROZEN_SHA^{commit}")" = "$FROZEN_SHA"
test "$(git -C "$CANDIDATE" rev-parse round4/closure^{commit})" = "$FROZEN_SHA"
test -z "$(git -C "$CANDIDATE" status --porcelain=v1)"
```

## 2. Row-0 local preflight: zero requests

```sh
for MERGE in db0e4567 99bbfb8a 85aec978; do
  git -C "$CANDIDATE" merge-base --is-ancestor "$MERGE" "$FROZEN_SHA"
done

RUN_ROOT=/private/tmp/moss-r4-10-$(date -u +%Y%m%dT%H%M%SZ)
git clone --no-local --single-branch --branch round4/closure "$CANDIDATE" "$RUN_ROOT/frozen-preflight"
git -C "$RUN_ROOT/frozen-preflight" checkout --detach "$FROZEN_SHA"
cd "$RUN_ROOT/frozen-preflight"
npm ci --offline --prefix frontend

export PY=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
export MODEL=/Users/gao/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8
export MANIFEST=/Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json
test -d "$MODEL"
test -f "$MANIFEST"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" - <<'PY'
import pathlib, sqlite3
import moss_transcribe_diarize as moss
from moss_transcribe_diarize.app.phase2 import REQUIRED_SQLITE_RUNTIME
assert pathlib.Path(moss.__file__).resolve().is_relative_to(pathlib.Path.cwd())
assert sqlite3.sqlite_version == REQUIRED_SQLITE_RUNTIME == "3.53.4"
print(sqlite3.sqlite_version, REQUIRED_SQLITE_RUNTIME)
PY
! git grep -n -E 'sqlite3\.sqlite_version[[:space:]]*=' -- '*.py'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" -m moss_transcribe_diarize.live_provider_preflight --manifest "$MANIFEST" --json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  "$PY" -m pytest -q -p no:cacheprovider tests 2>&1 | \
  tee "$RUN_ROOT/backend-suite.log"
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
test "$(git ls-files moss_transcribe_diarize/app/frontend_assets | wc -l | tr -d ' ')" = 17
test -z "$(git status --porcelain=v1)"
```

Expected minimums: backend `2,199 passed / 0 failed / 5 skipped / 2 xfailed`,
frontend `312/312`, TypeScript clean, assets unchanged. Any failure is row-0
`INCOMPLETE`; spend zero requests.

## 3. Pin inventory and receipt custody

```sh
git grep -n -E 'frozen_sha|product_changes_since_frozen_sha|round4-frozen-|0de56e1a|71f23c0c' -- \
  docs/handoffs prototypes tools evidence/round4
```

- Re-pin only the live `Pins (lead)` line in `docs/handoffs/r4-10-runbook.md` to
  `$FROZEN_SHORT` and `$FREEZE_TAG`. Preserve F1's historical `0de56e1a` row.
- Append the new F0 product/harness pair to external
  `status/R4-10-LEDGER.md`; preserve its historical F0 and F1 evidence.
- Never rewrite `evidence/round4/features/**`: those are historical receipts for
  `71f23c0c`. New row receipts must record `frozen_sha=$FROZEN_SHA`,
  `head=$FROZEN_SHA`, and `product_changes_since_frozen_sha=[]`.
- Every execution clone is detached at `$FROZEN_SHA`; only its named harness path
  may be overlaid from `$HARNESS_SHA`:

```sh
export HARNESS_SHA=<accepted-measurement-harness-SHA>
export NAME=<f2-s17-or-f3-bundle-or-f3s-summaries>
export HARNESS_PATH=<one-named-harness-path>
git clone --no-local --single-branch --branch round4/closure "$CANDIDATE" "$RUN_ROOT/$NAME"
git -C "$RUN_ROOT/$NAME" checkout --detach "$FROZEN_SHA"
git -C "$RUN_ROOT/$NAME" checkout "$HARNESS_SHA" -- "$HARNESS_PATH"
git -C "$RUN_ROOT/$NAME" diff --quiet "$FROZEN_SHA" -- moss_transcribe_diarize frontend
test "$(git -C "$RUN_ROOT/$NAME" rev-parse HEAD)" = "$FROZEN_SHA"
jq -n --arg frozen_sha "$FROZEN_SHA" --arg head "$(git -C "$RUN_ROOT/$NAME" rev-parse HEAD)" \
  '{frozen_sha:$frozen_sha,head:$head,product_changes_since_frozen_sha:[]}' \
  >"$RUN_ROOT/$NAME/freeze-custody.json"
```

## 4. Lead-only decoder-path validation: zero requests

Do not execute without the lead holding `GPU-LEASE.md`. This validates transport
only; it does not authorize a measurement row.

```sh
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18400:127.0.0.1:8000 \
  gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
curl -fsS http://127.0.0.1:18400/metrics | \
  grep -E '^vllm:num_requests_(running|waiting)' | \
  tee "$RUN_ROOT/decoder-idle.txt"
grep -q 'num_requests_running.* 0' "$RUN_ROOT/decoder-idle.txt"
grep -q 'num_requests_waiting.* 0' "$RUN_ROOT/decoder-idle.txt"
```

Close the tunnel, prove port 18400 has no listener, then return the lease to `FREE`.

## 5. Measurement rows after re-freeze

F3r is gated on pane 3.3's F1 fix being merged into `$FROZEN_SHA`. It runs after
F3s and keeps `capacity_2x1800: REQUIRED-NOT-RUN`.

| Order | Row | Exact planned decoder | Provider | Required receipts | Running decoder total |
|---|---|---:|---:|---|---:|
| F3s | Summaries only | 3 | 6 | summary receipt; proxy delta `3/3/0` | 2,470 |
| **F3r** | Retained File SIGKILL/resume | **6** (`n=3`, `k=1`: reference 3 + pre-crash 1 + post-restart 2) | 0 | `receipt.json`; `decoder-requests.jsonl`; private initial/restart logs | **2,476 / 5,000** |

The brief's `2n-k=5` omits the real request that creates the one-window
checkpoint. F3r accounts for all six requests and remains below its cap of 12.
Missing evidence or an upstream error is `INCOMPLETE`.

```sh
cd "$RUN_ROOT/f3r-resume"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" prototypes/resume-row/run.py \
  --run --frozen-sha "$FROZEN_SHA" \
  --decoder-upstream-port "$DECODER_UPSTREAM_PORT" \
  --budget 6 --port 17835 --proxy-port 19135 \
  --model "$MODEL" --manifest "$MANIFEST" \
  --out "$RUN_ROOT/f3r-resume-result"
```

Required PASS predicates: restart descriptor served while the retained Meeting is
reserved; background checkpoint validation accepted; post-restart proxy delta
exactly `2/2/0`; total proxy accepted/completed exactly `6/6`, peak at most two;
Meeting `completed`; transcript exactly equals the uninterrupted reference in
memory; retained owner directory reclaimed.

## 6. Tag, private push, and integration fast-forward

Run only after row 0 and adversarial review accept exactly `$FROZEN_SHA`.

```sh
test "$(git -C "$CANDIDATE" remote get-url private)" != \
  "$(git -C "$CANDIDATE" remote get-url origin 2>/dev/null || true)"
git -C "$CANDIDATE" tag -a "$FREEZE_TAG" "$FROZEN_SHA" -m "Round 4 closure frozen $FREEZE_DATE"
git -C "$CANDIDATE" switch round4/integration
git -C "$CANDIDATE" merge --ff-only "$FROZEN_SHA"
git -C "$CANDIDATE" push private round4/integration
git -C "$CANDIDATE" push private "refs/tags/$FREEZE_TAG"
test "$(git -C "$CANDIDATE" rev-parse round4/integration^{commit})" = "$FROZEN_SHA"
```

Never push this freeze or tag to `origin`.
