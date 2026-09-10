# Service journal source verdict — 2026-09-10

Structural question: can error/content absence mean a real service stream was read,
not that somebody created an empty file?

Minimum primitives: fixed user-service unit (source), its real journal cursor
(start boundary), successful subsequent read (observed interval). A filename alone
proves none of these. Invariant: never emit message content; unavailable/mismatched
source fails. An empty *tail after a proven cursor* is valid observed inactivity.
Unknown: service log retention outside this attempt; not claimed as an audit archive.
Falsifier: absent baseline, failed command, wrong-unit record or malformed message
qualifies as a clean log. Tool decision: query the actual host, no writes/restarts,
and inspect only source flags/counts before absorbing the reader.

Read-only remote prototype, each of moss-web/moss-live-web/moss-vllm:

```sh
journalctl --user --unit UNIT --no-pager --quiet --output=json -n 1
journalctl --user --unit UNIT --no-pager --quiet --output=json --after-cursor CURSOR
```

Measured: all three exit 0, one baseline record, nonempty cursor and matching
`_SYSTEMD_USER_UNIT`; message byte counts 55/70/264. Each immediate tail exits 0
with zero records. No message content printed, no audio or host mutation.

Verdict: absorb this reader as `phase2_acceptance_journal.py`, fixed candidate web
and vLLM units only. Read windows around each sentinel/operator/load experiment.
The vLLM journal is the inference log; no invented server-side external-AI prompt
log exists under the browser-direct AI decision.
