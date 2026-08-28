# MOSS Transcribe Diarize

MOSS is one authenticated web product for live, uploaded-file, and URL transcription with
speaker identification. Google OpenID Connect establishes an Account; every Meeting,
transcript version, audio artifact, and speaker name is owner-bound to that Account.

## Product surface

- `mtd-phase2-web` runs the TLS Account application on port 7861.
- `mtd-admin` uses the mode-0600 host-local Unix socket for account allow/revoke and
  content-free operator status.
- `/` is the only HTML product surface. It presents File, Live, and History in that order.
- Browser capture uses two lanes (system audio and microphone) and the shared live runtime.
- File and URL Meetings use the same inference composition and durable Meeting archive.

There is no plaintext listener, shared bearer, pairing/device/view token, global job
namespace, native capture application, or separate subtitle web/CLI product.

## Development

```bash
uv sync --frozen --extra dev --extra torch-runtime
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/
cd frontend && npm ci && npm test -- --run && npm run typecheck && npm run build
```

The production command requires explicit Account, TLS, storage, provider-manifest, and
helper-lease configuration:

```bash
uv run mtd-phase2-web --help
uv run mtd-admin --help
```

Model inference is replaceable beneath the Account product. The default packaged deployment
uses the OpenAI-compatible vLLM endpoint; local Hugging Face inference remains available via
`--backend hf`. Shared model, windowing, subtitle, live diarization, and replay-measurement
modules are libraries, not alternate product authority.

## Deployment

See [LOCAL_DEPLOYMENT.md](LOCAL_DEPLOYMENT.md). The tracked deployment installs one TLS web
unit (`moss-web.service`) plus `moss-vllm.service`; trusted certificate provisioning and
attended host cutover are separate release steps.

Architecture and historical evidence remain under `docs/`. Historical Phase-1 plans and
evidence are records, not executable deployment instructions.
