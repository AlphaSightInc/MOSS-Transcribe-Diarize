# Revocation evidence verdict — 2026-09-10

Question and falsifiers are in `revocation_snapshot_probe.py`; run with:

```sh
PYTHONPATH=. .venv/bin/python prototypes/phase2-account-lifecycle/revocation_snapshot_probe.py
```

Measured on Python 3.12.12 / SQLite 3.50.4, temporary state only:

- The read-only connection sees committed WAL while the production store stays open.
- Exact acknowledged transcript/version and interrupted state survive revocation.
- Real production `MeetingHandle.publish_audio` MP3 decodes to nonempty PCM silently.
- A wrong owner cannot read the row through the test query.
- A write through the read-only connection is refused.
- Corrupt audio fails decode; restoring the temporary artifact yields identical state.
- The revoked browser credential stays invalid; no owner is restored.

Verdict: use this narrow read-only seam solely for attempt-owned disposable candidate
state, bound to the cutover restore plan and exact test-created IDs. Never use a
writable `Phase2Store`, perform recovery, add a product-content API, inspect unrelated
rows, or emit raw transcript/audio/credentials in qualification artifacts. Missing
or mismatched evidence fails the gate. This is not real-host or speech-quality proof.

Read-only adversarial review accepted this as an evidence-collection change within
the approved plan. No new user decision is required unless real user data, restored
authority, or a production control interface becomes necessary.
