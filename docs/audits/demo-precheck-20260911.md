# Presenter precheck — 2026-09-11

Run `scripts/demo-precheck.sh EXPECTED_FULL_SHA` on the MacBook. Require final `GO` and exit 0. Every failed or unavailable prerequisite produces `NO-GO` and exit 1. Runtime dependencies: bash, curl, python3 standard library.

The workspace request uses certificate verification, disables curl configuration files, and does not follow redirects. Candidate identity comes from `X-MOSS-Candidate-SHA`, set by the packaged-candidate middleware in `moss_transcribe_diarize/app/phase2.py`; compare the full 40-character SHA exactly. Editable installations without the header cannot pass identity verification.

Bootstrap uses a temporary private cookie jar and creates only its own empty workspace. The authenticated model list must contain both configured upstream/model pairs. Direct completion probes run sequentially, MacStudio then RTX4090, with 16 output tokens, thinking disabled, a 30-second request deadline and 5-second connection deadline. A successful status without answer content fails. Direct probing avoids the relay's 2,048-token floor.

## Verification

- `python -m pytest tests/test_demo_precheck.py -q`: **9 passed**. Simulated complete success, TLS failure, wrong SHA, missing models, bootstrap failure, empty answer, timeout, malformed JSON and invalid argument. Checks cookie reuse, trusted-TLS options, token/deadline bounds and upstream order.
- Real isolated local stack on port 17863, checkout `cf0dc39812dd699e40d2ac1ee718c0cfd47fc315`, relay configured: normal system trust correctly rejected its self-signed certificate. Both upstreams still answered: MacStudio **0.532 s**, RTX4090 **5.574 s**. Exit 1 with explicit failed prerequisites.
- Second local run supplied the existing test certificate through process-local `CURL_CA_BUNDLE`; no system trust changes. Host HTTP 200, bootstrap HTTP 200 and both relay models passed. Direct answers: MacStudio **0.433 s**, RTX4090 **0.361 s**. Exit 1 solely because the editable local stack has no candidate identity header.
- Retained output: [default trust](../../evidence/demo-precheck-20260911/local-untrusted.txt), [explicit local test certificate](../../evidence/demo-precheck-20260911/local-trusted.txt).

Production origin was not contacted. These checks establish script behavior and local API compatibility, not production admission or availability. The operator must run it with the admitted candidate SHA on the MacBook.
