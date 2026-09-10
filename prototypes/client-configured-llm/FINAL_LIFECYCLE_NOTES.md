# Final-only lifecycle — measured 2026-09-10

Question: can a cancelled worker overwrite a new attempt without server-side provider
configuration? Minimum primitives: finalized source version, opaque attempt ID, state.
The existing owner-bound handle and SQLite mutation boundary serialize admission and
publication. No lease, new authentication or external inference process on MOSS.

The scratch SQLite probe printed every state and measured old-attempt publication 0,
wrong-version publication 0, current publication 1. Absorbed into `phase2_summary.py`
and production HTTP/storage tests; throwaway shell deleted. A closed tab leaves visible
active state: any same-workspace tab can explicitly Cancel, then Retry. Server restart
marks outstanding attempts failed; late workers cannot publish.

Browser implementation: finalized transcript projection excludes meeting/canonical IDs,
history and audio; direct HTTPS request omits ambient cookies/referrer, rejects redirects.
One serial browser queue; four byte-identical deliveries maximum, waits 60/120/240 s.
Only network/timeout/408/429/5xx retry. Exactly five-field raw JSON; no extraction/repair.
Only result, attempt/source/artifact versions, state and fixed failure code reach MOSS.
User settings remain local. The packaged public default prompt exactly mirrors V15.

Adversarial review found cancellation during an awaited generating response still sent
the transcript externally. Production regression measured one forbidden post-cancel
request (red); checking cancellation after the awaited state response measured zero
(green). Held provider response and scheduled-retry cancellation also pass. 32 concurrent
server admissions yield exactly one worker and 31 conflicts. Invalid output has no repair.

Muted Chrome UI check: local save produced zero server writes; private bank displayed two
same-name opaque entries and incompatibility guidance. Synthetic fixture/mock response,
not provider CORS or deployed qualification. Screenshot `/tmp/moss-final-ui-20260910.png`.
No microphone, shared-screen capture, speaker playback or volume change.

Commands:

```sh
.venv/bin/python -m pytest -q tests/phase2/test_final_summary.py --tb=short
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Full G9 still requires real cross-origin browser transport and delayed-provider overlap
with the deployed four-session capacity campaign. Semantic model quality is not proved
by structural validation, and each user's provider compatibility remains their setting.

Follow-up: `final_browser_probe.py` measures real cross-origin OPTIONS/POST through the
shipped UI and production owner-bound store: **8/8** pass, two actual Chrome profiles,
zero browser request interception. Its generated provider certificate is ignored only
by those disposable contexts; no trusted production TLS or deployed load claim. Synthetic
transcript seeding is limited to scratch state. Deployed G9 remains required.
