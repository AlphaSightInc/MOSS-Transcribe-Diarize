# Browser AI: configured tailnet relay

MOSS can relay the creating browser's final-summary requests to configured key-less
tailnet models. Browser settings default to the first listed model on a fresh browser;
saved external-provider settings are preserved. Select **Server relay (tailnet models)**
to use the model dropdown without a URL or API key. The existing **External HTTPS provider**
option continues to call the configured HTTPS service directly from the browser.

Set this in the host profile consumed by `ops/account-web-launcher.sh`:

```sh
MOSS_LLM_UPSTREAMS='[{"name":"macstudio","base_url":"http://macstudio.tailnet.aisight.us:1234/v1","models":["qwen/qwen3.6-35b-a3b"]},{"name":"rtx4090","base_url":"http://ga0-rtx4090.tailnet.aisight.us:1235/v1","models":["qwen38-27b-mtp"]}]'
```

The launcher forwards this as `--llm-upstreams`; direct CLI startup also reads the
environment variable. Configuration is validated before serving. No host profile,
certificate, proxy configuration, or running service was changed by this feature.

- **R1 — Requests:** both endpoints require the normal browser-workspace session.
  `GET /api/llm/models` returns configured `{id, upstream}` entries in config order.
  Empty/absent config returns `{"data":[]}`; completion requests return 404.
- **R2 — Routing:** `POST /api/llm/chat/completions` accepts only `model`, `messages`,
  optional `max_tokens`, and optional `temperature`. Unknown models return 404
  `unknown_model`. A request cannot supply a URL, key, streaming mode, or cookies
  to an upstream. The server adds `stream:false`; valid positive token budgets default/floor to 2048 and cap at 4096.
  The frontend explicitly requests 2048 for summaries. The relay sends
  `chat_template_kwargs: {"enable_thinking": false}`; configured upstreams must support
  this chat-template option (verified against both deployments in the example above).
- **R3 — Failure:** upstream transport/timeout errors return 502 `upstream_unreachable`;
  HTTP/invalid-JSON errors return 502 `upstream_error`; missing/blank answer content returns
  502 `empty_content`. A reasoning-only response gets exactly one fresh attempt with
  thinking disabled, within the original 180-second deadline. Both-empty responses
  fail immediately; reasoning is never substituted for the answer. Nonempty answer JSON is passed
  through, including reasoning fields. No prompt, response, or raw exception is journaled.
- **R4 — Fallback:** the browser retries once with the next listed model after those
  relay errors, within the same summary attempt. It does not cycle through the list or
  run four delivery rounds. Invalid final-summary JSON is still rejected without repair.
  The generation tab's status names the successful model. Model metadata is not stored
  with the final artifact; reloading history does not recreate that transient status.
- **R5 — Boundaries:** server requests time out at 180 seconds; fresh relay settings use
  a 200-second browser timeout so the server can report failure before browser cancellation.
  External HTTPS delivery retries remain 60/120/240 seconds. Clear settings disables new
  calls in that browser; opening history never starts inference.

Validation commands (local scratch state and fake upstreams only):

```sh
.venv/bin/python -m pytest tests -q
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/relay_browser_probe.py
PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/final_browser_probe.py
```

`tests/phase2/test_completion_qualification.py` preserves the `browser_final_summary`
predicate's rejection of missing timing/content-boundary evidence. The real CORS probe
exercises the direct external provider path. These local checks are not the deployed G9
capacity/TLS campaign; that campaign is not rerun by this no-host-operations task.
