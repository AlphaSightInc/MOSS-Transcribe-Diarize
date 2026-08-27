---
id: T-29
map: map-002-phase2-multiuser
title: Operator observability — metadata-only multi-user health and capacity
type: grilling
status: closed
assignee: codex-20260827
blocked_by: [T-19, T-20, T-21, T-23, T-24, T-25]
---

## Question

What operational metadata may the operator see across Accounts, and which health/capacity
actions are needed, without creating a content-access backdoor?

Decide, with the operator, after the account, persistence, Voice-profile, audio, and LLM shapes
are closed:

- **Visible metadata** — active Meeting counts, Account identity/display fields, capture health,
  inference queue depth/backpressure, disk use by artifact family, and last-error facts.
- **Forbidden content** — transcript text, retained audio, Voice-profile vectors/names, prompts,
  and LLM outputs remain absent per *Identity and isolation architecture*.
- **Actions** — which metadata-only operations exist (for example, revoke a Sign-in session,
  disable an Account, or stop a failing Meeting) and which would cross into content access.
- **Surface** — authenticated operator page vs logs/metrics, retention of operational facts,
  and the smallest interface needed for the known-team deployment.

Resolution records the exact visible fields, actions, retention, and UI/metrics surface. It does
not reopen content sharing or add enterprise administration scaffolding.

## Resolution

Resolved 2026-08-27 with the operator through D1-D12; the operator explicitly delegated the
remaining bounded choices recorded below.

### Surface and authority

- Operator observability is **host-local only**. The human surface is `mtd-admin status`; the
  same snapshot is available as `mtd-admin status --json` for exact inspection and tests.
  There is no operator web page, product administrator role, remote metrics endpoint,
  Prometheus/OpenTelemetry surface, or periodic dashboard collector.
- One deep **Operator Control module** owns cross-Account status and the one Meeting-control
  action below. Its interface exposes `snapshot()` and `interrupt(meeting_id)`; it returns only
  Operational metadata. It cannot open an Account workspace or a Meeting artifact.
- `mtd-admin` reaches that module through one Unix-domain socket in the service user's runtime
  directory. The socket is owned by the MOSS service user and mode `0600`. The CLI never opens
  live SQLite directly. There is no TCP admin port, bearer credential, second daemon, or
  compatibility path. If MOSS is down, `status` reports service unavailable and mutations fail
  without changing files.
- Account admission remains the already-settled host-local CLI interface: `mtd-admin accounts
  allow EMAIL`, `mtd-admin accounts list`, and `mtd-admin accounts revoke EMAIL`. Those commands
  also run in the service process through the same socket while MOSS is live, so database and
  active-Meeting effects remain one operation.

### Exact visible snapshot

Every snapshot carries `observed_at_utc` and contains these facts only:

1. **Service and capacity:** readiness (`ready`, `degraded`, or `unavailable`); active Live
   Meeting count against the settled four-session bound; active File Meeting count; inference
   worker `idle`/`busy`; queue depth by `live_canonical`, `live_refinement`,
   `live_provisional`, and `batch`; and the count of Meetings currently experiencing
   backpressure. No GPU/VRAM dashboard or newly invented latency percentile ships.
2. **Account rows:** current verified email, current Google display name, enabled/disabled
   state, current Sign-in-session count, and active Live/File Meeting counts. Google `sub`,
   avatar URL, historical emails, session identifiers, device labels, and activity tracking are
   absent. Structured logs use the opaque Account ID, not email, for correlation.
3. **Active Meeting rows:** current Account email, opaque Meeting ID, Live/File mode, lifecycle
   state, UTC start time, elapsed time, and the safe last-error projection below. Live rows also
   show capture phase; Microphone and System Lane health; seconds since each Lane's last accepted
   frame; pending canonical work versus its configured limit; and current backpressure state.
   Meeting title, user-facing status text, raw sample counters, audio levels, and transcript
   revision data are absent.
4. **Storage:** free bytes for each distinct filesystem holding SQLite or Meeting audio;
   host-wide physical bytes for SQLite and its WAL; and retained-audio count/bytes by
   `available`, `partial`, and `unavailable`, both host-wide and per Account. Per-Account logical
   counts cover Meetings, transcripts, Voiceprints, and Final summaries. SQLite families do not
   receive fabricated physical-byte estimates. Quotas, expiry, deletion controls, paths, and
   filenames remain absent.
5. **Safe last error:** UTC occurrence time, subsystem, stable error code, severity,
   terminal/retryable state, occurrence count, and only allowlisted numeric or enumerated
   context such as Lane, HTTP status, queue depth, and queue limit. Arbitrary exception text,
   stack locals, request/response bodies, and artifact data are never projected.

The status command is an on-demand observation, not a capacity promise or historical report.
Derived capture health reuses the measured Phase-1 capture-health projection; this decision adds
no threshold.

### Operator actions

- There is **no individual Sign-in-session operator action**. Sessions deliberately have no
  device identity or last-seen tracking, so selecting one would be guesswork. A user signs out
  the current browser. A lost device is handled by the settled Account revoke, followed by
  re-allow and fresh Google sign-in; ownership never changes.
- `mtd-admin meetings interrupt MEETING_ID` is the sole new Meeting mutation. It accepts only an
  active Meeting and is idempotent. It immediately fences new capture and future result commits,
  removes queued inference for that Meeting, and allows an already-running inference call to
  return only so its late result can be discarded. It persists the last accepted transcript.
  A Live Meeting publishes the maximal recoverable mixed-audio prefix as `partial`; a File
  Meeting removes working source after in-flight use ends. The command returns after the
  terminal state is durable and records `interrupted`, never `completed`.
- The interface exposes no transcript/audio/summary/Voiceprint read, download, delete, rename,
  rerun, ownership transfer, impersonation, quota, service restart, or drain operation.

### Logging and retention

- `status` is live and unpersisted. A Meeting's terminal outcome and safe latest-error fields
  remain with that Meeting for its lifetime; the MVP has no Meeting-delete action.
- MOSS emits structured events only for service-readiness changes, Account admission/revocation,
  Meeting lifecycle changes, capture-health transitions, backpressure enter/clear, artifact-state
  changes, safe errors, and operator mutations. It emits no per-frame or periodic status log.
- Structured events go to the existing host service journal and follow its operator-managed
  retention. MOSS adds no audit-log table, log time-to-live, archive, cleanup UI, or second
  bookkeeping system.
- Logs obey the same content boundary as `status`: no Meeting title, transcript text, audio or
  waveform data, source filename/URL, Voiceprint label/vector/sample, prompt, language-model
  output, client endpoint/model, cookie/session secret, raw exception payload, or request body.

### Acceptance facts handed forward

*Phase-2 acceptance gates — adversarial isolation, revocation, voice, audio, LLM privacy* must
prove: the socket is local and `0600`; no TCP/browser admin surface exists; table and JSON output
contain exactly the allowlisted fields; two Accounts' content never appears in status or logs;
storage counts reconcile with authoritative metadata; Account revoke retains its settled
all-session/active-Meeting effect; and Meeting interruption fences a deliberately late inference
result while preserving the durable transcript and partial-audio prefix.

`CONTEXT.md` now defines Operational metadata and Interrupted Meeting. No ADR is warranted: this
is a small, reversible operating surface whose rationale and exact contract live here. No new
ticket or fog surfaced.
