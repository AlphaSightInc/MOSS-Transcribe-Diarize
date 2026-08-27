# T-18 — MOSS multi-user-relevant current state (branch `dev`)

Researched 2026-08-26 against branch `dev` via `git show dev:<path>` (never checked out).
`dev:<path>:<line>` cites the dev blob. Current worktree (`ralph/live-convergence-0824`) drifts
from dev by +4128 lines in live internals (`live_transcript_convergence.py` is worktree-only, not
on dev; `live_service_runtime.py` +578, `live_session.py` +401, etc. — `git diff dev --stat`), but
**every file cited below for auth/transport/journal/frontend/ops is byte-identical between dev and
the worktree** (`git diff dev -- app/live_auth.py app/live_transport.py app/live_vector_journal.py
app/live_portal.py frontend/ ops/` shows changes only in `jobs.py` and `live_portal.py`, both
worktree-side). Product truth used throughout: dev.

## 0. TL;DR

- **One trust domain.** Auth is a per-request bearer resolved against an in-memory
  `LiveAccessRegistry`; the deployed path is a single shared token whose every holder is the *same*
  synthetic device (`"shared-token"`), so every shared-token client owns every live session and
  sees every batch job. There are no accounts, no per-user anything, no job ownership.
- **Sessions are memory-only.** Live session ids are `uuid.uuid4().hex`; all session state
  (runtime, v2 lanes, mixer, presence, view grants) lives in ~9 in-memory dicts keyed by
  session_id and dies on restart. Only 4 durable stores exist: `runs/<job>/`, `live-auth.json`
  (devices only, digests), the speaker-vector JSONL journal, and the (deployed-OFF) tape root.
- **The jobs API is the soft underbelly**: 7 of 11 `/api/jobs*` routes have **no auth at all** even
  in live mode, and the whole jobs surface is unauthenticated on the plaintext batch service —
  which binds `0.0.0.0`.

---

## 1. Auth today

### 1.1 The shared bearer token — configuration chain

| Step | Evidence |
|---|---|
| Operator writes one-line token file, mode 0600 enforced | `dev:moss_transcribe_diarize/app/web_cli.py:216-244` (`_live_shared_token`: exactly one non-empty line, stripped; refuses group/world-readable file) |
| Env key names only the path, never the bearer | `dev:ops/moss-live.env.example` — `MOSS_LIVE_SHARED_TOKEN_FILE=...` with comment: *"Any holder of this token can read any live session in the single trust domain; remove this key to keep the pairing flow"* |
| `ops/start-web.sh` passes `--live-shared-token-file` | `dev:ops/start-web.sh:99-105` |
| `create_app(live_shared_token=...)` builds `LiveAccessRegistry(shared_token=...)` | `dev:moss_transcribe_diarize/app/server.py:54,119-128` |
| Registry canonicalizes (strip) then stores **sha256 digest only**, as a synthetic device `_SHARED_TOKEN_DEVICE_ID = "shared-token"` | `dev:moss_transcribe_diarize/app/live_auth.py:18,180-207` |
| Presented bearers stripped + digested the same way; compared with `hmac.compare_digest` | `dev:moss_transcribe_diarize/app/live_auth.py:298-305,457-465` |

The shared principal is configuration-only while active (never persisted); once revoked, a
digest-bound revocation marker is persisted so re-configuring the *same* token stays dead across
restarts while rotating to a new token recovers service (`dev:.../live_auth.py:421-455,497-514`).

### 1.2 Authorization model — `LiveAccessRegistry.authorize()`

`dev:moss_transcribe_diarize/app/live_auth.py:283-338`. Every live request resolves
(peer, bearer, action, session_id) to one of three principals:

- **CapturePrincipal(device_id)** — bearer digest matches an unrevoked device (shared-token or a
  paired device). Allowed actions `CAPTURE_ACTIONS = {create, frame, heartbeat, snapshot, events,
  stop, abort}` (`:20`). When a `session_id` is present, the session **must be owned by this
  device** (`_sessions[sid].owner_device_id == device_id`, `:309-314`) — the ownership check.
- **ViewPrincipal(session_id)** — bearer digest matches a session's view token
  (`_view_for_digest`, `:467-474`; revocation + absolute expiry checked). Allowed actions depend
  on the session's **live status pulled from the runtime** via `SessionStatusResolver`
  (`:159,209-217,320-332`): `active`/`closing` → `VIEW_ACTIONS = {snapshot, events, stop, abort}`
  (`:21`); terminal `closed/failed/aborted` → `TERMINAL_VIEW_ACTIONS = {snapshot, events}` only
  (`:26-28`); **unknown status → fail closed 401** (`:327-328`). Scoped: `session_id` in the URL
  must equal the token's session (`:331-332`).
- **DescriptorPrincipal** — `action == "descriptor"` needs **no bearer** (`:292-297`); peer
  admission only.

**Peer admission** (`_admit_peer`, `:397-405`): peer IP must be inside
`127.0.0.0/8, ::1/128, 10/8, 172.16/12, 192.168/16, 100.64/10 (CGNAT/Tailscale), fc00::/7,
fe80::/10` (`:30-42`), and any non-loopback peer must arrive over TLS. `request.client.host` is
trusted directly; uvicorn runs `proxy_headers=False` (`dev:.../web_cli.py:356`), so no
X-Forwarded-For spoofing.

Errors are typed: 401 `LiveAccessUnauthorized`, 403 `LiveAccessForbidden`, 409
`LiveAccessConflict` (`:45-58`).

### 1.3 The pairing / device flow (Live access registry) — present and WIRED, dormant in the Chrome flow

- `POST /api/live/pairing-codes` — **loopback-only** mint of a single-use, 300 s payload
  `mtd1.<secret>.<cert-sha256>` bound to the server certificate
  (`dev:.../live_auth.py:14-16,219-234`; route `dev:.../live_transport.py:200-206`). Operator tool:
  `dev:ops/live-pair.sh` (prints payload exactly once; verifies cert digest; refuses non-loopback URL).
- `POST /api/live/pairings` — exchange from a **non-loopback TLS** peer with a caller-chosen
  `device_id`; mints a per-device capture token; `device_id == "shared-token"` and empty ids
  refused (`dev:.../live_auth.py:236-281`; route `dev:.../live_transport.py:208-228`). Devices
  (id + token digest + paired_at + revoked) are the only thing persisted to
  `live-auth.json` (`_persist`, `dev:.../live_auth.py:497-529`, atomic 0600 write).
- `DELETE /api/live/devices/{device_id}` — loopback-only, **no bearer**; revokes the device and
  aborts + releases every session it owns (`dev:.../live_transport.py:571-592`).
- `DELETE /api/live/sessions/{sid}/view` — loopback-only, **no bearer**; kills one session's view
  token, capture survives (`dev:.../live_transport.py:561-569`; `dev:.../live_auth.py:379-392`).
- Consumer of the pairing flow: the **macOS capture app**
  (`dev:macos/MOSSCapture/Sources/MOSSCaptureCore/CaptureSecurity.swift:12-18,64-69` — Keychain
  accounts `capture-bearer`, `capture-certificate-pin`, `capture-view-token`).
- The **Chrome client never pairs**: it sends the shared token typed by the user
  (`dev:frontend/src/capture/captureClient.ts:527-531` posts `/api/live/sessions` with
  `Authorization: Bearer <captureBearer>` and **no body — no device_id, no echo_mode**).

### 1.4 What a "client" is today

- **No accounts, no client identity.** A "client" is *whoever presents a valid bearer from an
  admitted peer*. `device_id` exists only in the pairing subsystem; **zero occurrences in the
  frontend** (`git grep device_id dev -- frontend/src` → none).
- Chrome client identity fragments: the capture bearer lives in a React `useState` only
  (`dev:frontend/src/App.tsx:12`), deliberately never persisted; the per-tab reattach record
  `{sessionId, viewToken}` lives in `sessionStorage["lt:session:reattach"]`
  (`dev:frontend/src/lib/persistence.ts:16-27,100-121`); `localStorage` holds only UI-collapse
  booleans + a session-id key (`storageKeys`, `persistence.ts:16-22`).
- All shared-token clients are one principal: same device id → mutual ownership of all
  shared-token sessions (see §6).

### 1.5 Jobs-API auth

`_authorize_job_request` (`dev:moss_transcribe_diarize/app/server.py:503-522`) builds a `LivePeer`
and calls `access.authorize(peer, bearer, "create", None)` — i.e. any capture-scope bearer
passes; and **if `live_access_registry is None` (live disabled, the batch service) it is a no-op**
(`:504-505`). It is applied to only 4 of 11 job routes (see table §5.2).

---

## 2. Session identity and grants

- **Minting**: `session_id = uuid.uuid4().hex` (`dev:moss_transcribe_diarize/app/live_service_runtime.py:453,847-853`),
  created under the runtime lock with duplicate refusal. Batch job ids: `uuid.uuid4().hex[:12]`
  (`dev:moss_transcribe_diarize/app/jobs.py:236,282`).
- **Grant binding at create**: `POST /api/live/sessions` authorizes action `create`, requires a
  `CapturePrincipal`, calls `runtime.create()`, then `access.bind_session(principal, sid)` which
  mints a **session-scoped view token** (32-byte urlsafe secret, digest stored) with absolute
  expiry `now + 12h` (`VIEW_ABSOLUTE_CAP_SECONDS`, `dev:.../live_auth.py:15,340-357`), and creates
  the v2 session, mixer, and tape entries; on any failure the grant is released
  (`dev:.../live_transport.py:230-264`). Response: `{id, owner_device_id, view_token,
  view_expires_at, descriptor, snapshot}` (`:257-264`).
- **Who may read `/snapshot` and `/events`**: the owning capture device (shared token included)
  or the session's view token; view authority is **derived per-request from the runtime's live
  session status** (`access.bind_session_lifecycle(_session_status)`,
  `dev:.../live_transport.py:154-171`), so whatever ends the session — stop, abort, helper-lease
  expiry, failed stop — demotes the view token to terminal read-only (snapshot/events) on the very
  next request, and a session the runtime has forgotten (e.g. after restart) → 401.
- **Chrome reattach** (ADR-0004, `dev:docs/adr/0004-browser-session-reattach.md`): store only
  `{sessionId, viewToken}` in tab-scoped sessionStorage; on reload, restart the read-only poller
  with the saved view token and do NOT resume capture (`dev:frontend/src/components/ControlPanel.tsx:137-139`
  save at create; `:197-215` reattach effect; UI says "Transcript reattached. Browser capture
  stopped on reload."). Clean terminal / reset / failure clears the record (`:147,176,204`).
- **Owner terminal fallback**: if the viewer poll 401s at terminal, the poller re-reads the
  snapshot once with the capture bearer (`terminalAccessToken`) to render the terminal transcript
  (`dev:frontend/src/api/mossPoller.ts:69,141-186`; wired `ControlPanel.tsx:144`).

---

## 3. Vector journal (T-12 output — the voice bank's raw material)

**Writer**: on every clean `stop`, after accepted==accounted verification, the runtime calls
`_append_vector_journal` (`dev:moss_transcribe_diarize/app/live_service_runtime.py:726,734-766`),
which appends one batch from `coordinator.journal_observations()`
(`dev:moss_transcribe_diarize/app/live_coordinator.py:488-490`) → identity preparer →
album projection (`dev:moss_transcribe_diarize/app/live_provider_bundle.py:710-734`: per speaker
label, duration-weighted centroid over album reference support, `embedder_id =
f"{spec.provider}:{spec.revision}"`, `embedder_state_sha = spec.state_sha256` from the offline
provider manifest). The **abort path writes nothing** (journal append only inside `stop`,
`live_service_runtime.py:664-732`; `abort` at `:768-794` never calls it). Outcome is journaled
into the session event stream as `vector_journal_appended` / `vector_journal_failed` (`:753,761`).

**Row schema, verbatim** (`dev:moss_transcribe_diarize/app/live_vector_journal.py:81-92`):

```python
row = {
    "session_id": session_id,
    "speaker_label": values["speaker_label"],
    "centroid": list(values["centroid"]),
    "sample_seconds": values["sample_seconds"],
    "exemplar_count": values["exemplar_count"],
    "provisional": values["provisional"],
    "embedder_id": values["embedder_id"],
    "embedder_state_sha": values["embedder_state_sha"],
    "created_at": created_at,
    "echo_mode": echo_mode,
}
```

One JSON object per line (compact separators, sorted keys, `allow_nan=False`), fsynced append; a
torn tail from a crash is newline-terminated before the next append and preserved forensically
(`:118-135,241-256`). Per-row refusals (never batch-fatal) with typed reasons:
`speaker_label_invalid, centroid_empty, centroid_not_numeric, centroid_non_finite,
sample_seconds_invalid, exemplar_count_invalid, provisional_invalid, embedder_id_missing,
embedder_state_sha_invalid` (64-hex enforced) (`:193-229`). `echo_mode` is `"unspecified"` for
every shipping client (`dev:.../live_service_runtime.py:465-476` — no client sends it).

**Path & posture**: `LiveVectorJournal.declared(path, checkout_root)` requires an absolute path
**outside the repo checkout**, 0700 dir / 0600 file with mode readback verification and
peer-writable-ancestor repair/refusal (`dev:.../live_vector_journal.py:47-65,259-341`).
**Default-ON whenever `--live` is on**: default path
`~/.local/share/moss-transcribe-diarize/live/speaker-vectors.jsonl`
(`dev:moss_transcribe_diarize/app/web_cli.py:156-179`; env `MOSS_LIVE_VECTOR_JOURNAL_PATH`,
`dev:ops/start-web.sh:70,81-92,110`). One file for **all sessions** — rows carry `session_id`, but
nothing else partitions speakers by client/user. No route reads it (`read_rows` at
`dev:.../live_vector_journal.py:138-155` has no HTTP caller).

---

## 4. Audio retention (ADR-0003 as implemented)

Decision record: `dev:docs/adr/0003-live-session-audio-retention.md` (D1 horizon=meeting,
D2 opt-in, D3 TTL default 0, D4 root admission rules, D5 degrade-never-fail, D6 reap).

**Implementation** — `dev:moss_transcribe_diarize/app/live_tape.py`:

- Per-session layout: `<root>/<session_id>/{system.pcm, microphone.pcm, mixed.pcm, index.json}` —
  raw PCM16 mono @16 kHz, track names from lane wire values + `mixed` (`:55-60,304-307`);
  `index.json` manifest: `{version, session_id, sample_rate, max_bytes, created_at, updated_at,
  ended_at, total_bytes, degradation, tracks{...coverage+gap manifest}}` (`:326-338`), rewritten
  atomically on every append (`:505-525`). Modes 0700/0600 (`:62-64`).
- **Fed from the frames/stop routes**: every acknowledged v2 lane frame is teed
  (`tapes.append_lane_frame`, `dev:.../live_transport.py:294`), every sealed mixer commit teed
  (`_tape_mixed`, `:302,441,609-629`). Storage pressure/cap/write failure → typed degradation
  (`tape_capacity_exhausted|tape_write_failed|tape_frame_not_admissible`, `live_tape.py:66-71`),
  taping stops, **meeting continues** (D5).
- **Root admission** (`LiveSessionTapeStore.declared`, `:589-670`): absolute, outside checkout,
  mode-enforcing filesystem (chmod readback), NOT inside or sharing a filesystem with any runs
  dir (st_dev compare) — refusal stops startup.
- **What survives Stop**: `release()` ends the tape but **deletes nothing**; deletion is `reap()`'s
  job, driven by `ended_at + TTL` (`:698-711,715-759`). TTL defaults to **0** → deleted at the next
  reap after the meeting; reap also runs **at startup** (`dev:.../live_transport.py:149-152`), which
  is what makes crashed-process tapes mortal. Stop/abort/device-revoke all release the tape
  (`live_transport.py:462,474,524,552,588`).
- **Export routes: none.** `read_track`/`track_path` have no HTTP caller on dev (grep). WAV is
  "rendered on demand elsewhere; nothing here transcodes" (`live_tape.py:7-8`).
- **Deployed posture: OFF.** `dev:ops/moss-live.env.example` ships
  `MOSS_LIVE_RETENTION_ROOT/MAX_BYTES/TTL_SECONDS` **commented out** ("OFF, and commented out on
  purpose"); `create_app(live_tape_store=None)` is the measured service
  (`dev:moss_transcribe_diarize/app/server.py:57-61`). A cap/TTL without a root refuses startup
  (`dev:.../web_cli.py:262-276`; `dev:ops/start-web.sh:129-132`).
- Without a tape root, live audio still touches disk for ~one span (~2.5 s) in
  `tempfile.TemporaryDirectory(prefix="mtd-live-")` scratches for the decoder and identity encoder
  (`dev:moss_transcribe_diarize/app/live_adapters.py:298-300`,
  `dev:moss_transcribe_diarize/app/live_provider_bundle.py:603-604`), deleted with the context
  (ADR-0003 "horizon today is one span").

---

## 5. Route inventory and isolation choke points

### 5.1 Live routes (all in `dev:moss_transcribe_diarize/app/live_transport.py`)

| Route | State selected by the id in the request | Current guard |
|---|---|---|
| `GET /api/live/descriptor` (`:173`) | none (service descriptor + protocol negotiation) | peer admission only; **no bearer** (`live_auth.py:292-297`) |
| `POST /api/live/pairing-codes` (`:200`) | mints pairing secret into `_pairings` | **loopback peer only**, no bearer |
| `POST /api/live/pairings` (`:208`) | `_devices[device_id]` (creates/overwrites) | non-loopback TLS private peer + valid unexpired single-use payload; reserved/empty id refused |
| `POST /api/live/sessions` (`:230`) | creates: runtime `_sessions[sid]`, `access._sessions[sid]` (view grant), v2 session, mixer, tape | capture bearer, action `create` |
| `POST /api/live/sessions/{sid}/frames` (`:266`) | runtime session (mono path) or v2 session + capture observations + tape + mixer + runtime, all keyed `sid` | capture bearer **+ device-ownership of sid** (`live_auth.py:309-314`) |
| `POST /api/live/sessions/{sid}/heartbeat` (`:354`) | `helper_presence[sid]`, `helper_failures[sid]` | capture bearer + ownership |
| `GET /api/live/sessions/{sid}/snapshot` (`:364`) | runtime snapshot + v2 snapshot + presence + capture-status projection for `sid` | capture ownership OR view token scoped to `sid` (status-gated) |
| `GET /api/live/sessions/{sid}/events` (`:387`) | runtime event deque for `sid` (bounded `max_events`) | same as snapshot |
| `POST /api/live/sessions/{sid}/stop` (`:412`) | drains v2+mixer, stops runtime, **appends vector journal**, releases v2/mixer/tape/helper state for `sid` | capture ownership OR view token while `active/closing` |
| `POST /api/live/sessions/{sid}/abort` (`:528`) | aborts runtime + v2; releases registries for `sid` | capture ownership OR view token while `active/closing` |
| `DELETE /api/live/sessions/{sid}/view` (`:561`) | `access._sessions[sid].view_revoked` | **loopback peer only, no bearer** |
| `DELETE /api/live/devices/{device_id}` (`:571`) | `_devices[did]` + abort/release of every owned session | **loopback peer only, no bearer** |

### 5.2 Jobs/file-mode routes (all in `dev:moss_transcribe_diarize/app/server.py`)

| Route | State selected | Current guard |
|---|---|---|
| `GET /api/jobs` (`:195`) | **all** jobs (`manager.list_jobs()`) | `_authorize_job_request` — bearer w/ capture scope **iff live registry present; no-op otherwise** |
| `POST /api/jobs` (`:200`) | new `runs/<job>/` dir | same + Content-Length/disk admission (`:490-500`) + 30 s receive-idle timeout |
| `GET /api/jobs/{job_id}` (`:276`) | `_jobs[job_id]` record | `_authorize_job_request` |
| `DELETE /api/jobs/{job_id}` (`:284`) | deletes job + dir | `_authorize_job_request` |
| `POST /api/jobs/{job_id}/rerun` (`:295`) | re-decodes job | **NONE** |
| `POST /api/jobs/{job_id}/resume` (`:319`) | resumes checkpoint | **NONE** |
| `GET /api/jobs/{job_id}/media` (`:332`) | **raw uploaded media bytes** (FileResponse) | **NONE** |
| `GET /api/jobs/{job_id}/segments` (`:345`) | transcript segments | **NONE** |
| `PUT /api/jobs/{job_id}/segments` (`:354`) | **rewrites** segments + style | **NONE** |
| `POST /api/jobs/{job_id}/render` (`:370`) | renders subtitle mp4 | **NONE** |
| `GET /api/jobs/{job_id}/download?kind=` (`:386`) | srt/ass/mp4/raw transcript files | **NONE** |
| `GET /api/runtime` (`:170`) | model/ffmpeg/live descriptor info | **NONE** |
| `GET /`, `/studio`, `/favicon.svg`, `/static/*` (`:144,162,166,80`) | frontend bundle from `ProjectResources/Frontend` | none (static) |
| `GET /live` (`dev:moss_transcribe_diarize/app/live_portal.py:7-9`) | serves the operator portal HTML (no data) | none (static page; its fetches use the routes above) |

**Choke-point count**: 12 routes where a session_id/job_id in the request selects server state
under some auth (5.1 minus descriptor/pairing-codes), plus **8 job routes where the id selects
state with no auth at all** (rerun/resume/media/segments GET+PUT/render/download on any service;
all 11 on the batch service).

### 5.3 The in-memory keyed stores behind those routes (the future isolation seams)

| Store | Key | Where |
|---|---|---|
| `LiveServiceRuntime._sessions` | session_id → coordinator/session/arbiter/events | `dev:.../live_service_runtime.py:458,501` |
| `LiveAccessRegistry._sessions` | session_id → owner_device_id + view-token digest + expiry | `dev:.../live_auth.py:145-152,178,346-351` |
| `LiveAccessRegistry._devices` | device_id → token digest, revoked | `dev:.../live_auth.py:177` |
| `LiveV2SessionRegistry._sessions` | session_id → lane buffers | `dev:moss_transcribe_diarize/app/live_v2_session.py:357,361` |
| `LiveCompatibilityMixerRegistry` | session_id → mixer | `dev:moss_transcribe_diarize/app/live_mixer.py:418` |
| `LiveSessionTapeStore._tapes` (+ disk `<root>/<sid>/`) | session_id → tape | `dev:.../live_tape.py:586,674-691` |
| `HelperPresenceRegistry._sessions` | session_id → heartbeat snapshot | `dev:moss_transcribe_diarize/app/live_helper_presence.py:181,186` |
| `LiveCaptureObservationRegistry` | session_id → ingress observations | `dev:moss_transcribe_diarize/app/live_capture_status.py:133` |
| `LiveHelperFailureCoordinator` | session_id → lease state | `dev:moss_transcribe_diarize/app/live_transport.py:96-108` |
| `JobManager._jobs` (+ disk `runs/<job_id>/`) | job_id → JobRecord | `dev:moss_transcribe_diarize/app/jobs.py:199-241` |

---

## 6. Cross-session read surfaces

1. **Shared token = one device.** Every shared-token client is `CapturePrincipal("shared-token")`,
   and session ownership is checked against the *device* (`live_auth.py:309-314`) — so **any
   shared-token holder can frame-inject into, read, stop, or abort any live session created by any
   other shared-token holder**, by design ("single trust domain",
   `dev:ops/moss-live.env.example`). There is no session-listing route, so cross-reading requires
   knowing the sid (128-bit uuid hex) — but sids appear in URLs, portal inputs, and reattach records.
2. **Jobs are unowned.** `JobRecord` has no owner/client field
   (`dev:moss_transcribe_diarize/app/jobs.py:56-84`); `GET /api/jobs` lists everyone's jobs to any
   bearer holder, and media/segments/downloads need no bearer at all (§5.2).
3. **Operator `/live` portal** (`dev:moss_transcribe_diarize/app/live_portal.py`): a static
   diagnostic page. Start path uses a pasted shared token (and then polls with it,
   `:420-423,441-479`); Connect path uses pasted `{session id, view token}` (`:124-128,892`). It
   exposes nothing beyond what those tokens already grant; it stores nothing (no
   local/sessionStorage in the portal script).
4. **Logs**: session_ids (never tokens) reach the journald stream via journal warnings
   (`dev:.../live_service_runtime.py:748-760`) and tape lines (`dev:.../live_tape.py:751-753`);
   uvicorn access logs record live URLs (which contain session ids, never tokens — bearers ride
   the Authorization header; view tokens never appear in URLs).
5. **The vector journal** is one file spanning all sessions (§3) — any future reader of the voice
   bank sees every session's speakers.

---

## 7. Persistence inventory — every durable store the server writes

| Store | Layout | Writer / owner | Notes |
|---|---|---|---|
| `runs/<job_id>/` (batch: `<checkout>/runs`; live host file-mode: `/mnt/d/Coding/MOSS-Transcribe-Diarize/live-runs`, `dev:ops/moss-live.env.example`) | `input.<ext>`, `job.json`, `raw_transcript.txt`, `segments.json`, `subtitle.srt`, `subtitle.ass`, `output.mp4`, `identity-resolution.json`, checkpoint dir | `JobManager` (`dev:.../jobs.py:88-113,199-303`) | job_id = uuid4 hex[:12]; jobs reloaded + resumable at startup (`:215-217`); no owner field |
| `live-auth.json` (`MOSS_LIVE_AUTH_STATE`) | `{"schema_version":1,"devices":{<device_id>:{token_digest,paired_at,revoked,revoked_at}}}` | `LiveAccessRegistry._persist` (`dev:.../live_auth.py:497-529`), atomic, 0600 | **devices only — sessions/view grants are never persisted**; active shared principal filtered out |
| `speaker-vectors.jsonl` (`MOSS_LIVE_VECTOR_JOURNAL_PATH`, default `~/.local/share/moss-transcribe-diarize/live/speaker-vectors.jsonl`) | JSONL, schema §3 | `LiveVectorJournal` via runtime stop | default-ON with `--live`; 0600/0700; outside checkout enforced |
| Tape root (`MOSS_LIVE_RETENTION_ROOT`) | `<root>/<sid>/{system,microphone,mixed}.pcm + index.json` | `LiveSessionTapeStore/Recorder` | **opt-in; deployed OFF**; TTL-0 reap; §4 |
| Span scratch | `/tmp/mtd-live-*/span-*.wav`, `live-evidence.wav` | live adapters / identity encoder | per-span temp, deleted with context (`dev:.../live_adapters.py:298-300`, `dev:.../live_provider_bundle.py:603-604`) |
| **No SQLite anywhere** | — | — | `git grep sqlite dev -- moss_transcribe_diarize ops frontend` → 0 hits |

Operator-written (server reads only): shared-token file, `live.crt`/`live.key`
(`dev:ops/generate-live-tls.sh`; cert DER sha256 becomes the pairing pin,
`dev:.../web_cli.py:302-310`), provider manifest (`ops/finalize-live-provider-manifest.py`),
WeSpeaker state file (Tier B / live encoder — read-only weights,
`dev:moss_transcribe_diarize/app/speaker_identity.py:1183`).

Deployment shape (`dev:ops/systemd/moss-web.service`, `moss-live-web.service`,
`dev:ops/start-web.sh:139-160`): two instances of the same app — batch plaintext :7860
(`MOSS_LIVE_ENABLED=0`, `dev:ops/moss.env`) and live TLS :7861 — both `--host 0.0.0.0`,
`--backend vllm` against a shared vLLM at `127.0.0.1:8000`.

---

## 8. Frontend seams (where an account would ride)

- **Poller headers**: `createMossSessionPoller` fetches
  `/api/live/sessions/{sid}/snapshot?since_version=` and `/events?since_seq=` in parallel with
  `Authorization: Bearer <accessToken>` (`dev:frontend/src/api/mossPoller.ts:113-117,203-205,
  593-607`); `terminalAccessToken` (the capture bearer) is the owner-side terminal fallback
  (`:141-186`). This options object is the single place a per-user credential would replace the
  view/shared token.
- **`dispatchWsEvent()` seam** (`dev:frontend/src/api/ws.ts:12-33`): the transport-agnostic event
  dispatch. The Phase-1 `WsEvent` union (`dev:frontend/src/api/types.ts:42-82`) carries exactly the
  5 reachable events: `session_state`, `transcript_update`, `transcript_relabeled`,
  `refinement_complete`, `stop_progress` (with `llm_state: null`).
- **`speaker_renamed`**: **declared UNREACHABLE in Phase 1 — "no rename endpoint exists; Phase 2"**
  (`dev:.wayfinder/tickets/T-02-poll-contract-event-model.md:110`); it is deliberately **absent
  from the shipped union** (types.ts) rather than dangling — the future rename hook means adding a
  server endpoint + a union member + a `dispatchWsEvent` case.
- **`TranscriptStreamParser`** is server-side Python
  (`dev:moss_transcribe_diarize/transcript_parser.py:19` — parses `[start][Sxx]text[end]` model
  output); the browser-side equivalent is the poller's snapshot/event rendering into
  `TranscriptItem`s (`types.ts:5-20`, with `speaker_entity_id` + `display_name` already in the
  shape — the natural attachment points for durable identity).
- **Capture path**: `CaptureClient` (`dev:frontend/src/capture/captureClient.ts`) drives
  descriptor preflight (`:629`), `createSession` (`:515-548`), frames (`:794`), heartbeats
  (`:926-940`), stop (`:550-`); all with `captureBearer`. Frames/heartbeats are AudioWorklet-driven,
  nothing polled.
- **File mode**: `FilePanel` passes the same typed bearer to the jobs API
  (`dev:frontend/src/components/FilePanel.tsx:6-27`;
  `dev:frontend/src/api/jobs.ts:262-263,298-299` set the header only when a token is present).

---

## 9. Concurrency / backpressure (G4) as implemented

- **Per-session bounded queue**: each session gets its own
  `InferenceArbiter(max_live_canonical_items=descriptor.bounds.max_queue_depth)`
  (`dev:.../live_service_runtime.py:482`; bounds are manifest-declared,
  `dev:.../live_provider_bundle.py:1278-1282`). Weighted admission; overflow raises
  `InferenceArbiterBackpressure` (`dev:moss_transcribe_diarize/app/live_arbiter.py:36-80`).
- **Global dispatcher**: ONE coalesced daemon worker thread `moss-live-canonical-pump`
  (`_TransientCanonicalPumpScheduler`, `dev:.../live_service_runtime.py:312-341`) drains a FIFO
  `_ready_session_ids` queue with an in-flight-per-session gate
  (`:460-463,934-998`) — i.e. **canonical inference is globally serialized across all sessions**,
  round-robin by readiness; per-item timing events `canonical_queued/started/processed` carry
  queue-wait and decode ms (`:985-993,1028-1060`).
- **429 semantics (per-session, all retryable-typed)**:
  - v2 lane retention full → 429 `v2_lane_retention_capacity_reached`
    (`dev:.../live_transport.py:968-976`);
  - canonical queue full → `LiveServiceTransportPacingFailure(code="canonical_queue_full",
    retryable=True)` → 429 via `_failure_status` (`dev:.../live_service_runtime.py:541-574`;
    `dev:.../live_transport.py:925-930`); v2 path keeps it **non-terminal** (frame retained for an
    identical retry), legacy mono path terminalizes;
  - frames route also maps raw `InferenceArbiterBackpressure|LiveSessionBackpressure` → 429 with
    a snapshot body (`dev:.../live_transport.py:335-339`);
  - stop under backpressure → 429 `v2_stop_backpressure` (`:491-500`).
- **No global cross-session admission limit** exists (no cap on session count; the shared pump +
  per-session queues are the only pacing). Gate status: G4 "concurrency ≥10 min" was **BLOCKED**
  at the 2026-08-18 reconciliation for lack of a real-decode host, not for missing code
  (`dev:docs/phase1-gate-status.md`, gate rollup table).
- Batch/file mode: `JobManager` runs jobs off a queue with checkpoint/resume
  (`dev:.../jobs.py:215-217,305-330`); upload admission = Content-Length required (411),
  2×length+512 MiB free disk (507), 30 s receive-idle timeout (408)
  (`dev:.../server.py:464-500`).

---

## 10. Absent / dormant / unknown

**Absent (does not exist on dev):**
- Accounts, users, orgs, or any per-user namespace; any notion of job ownership
  (`JobRecord` has no owner field, `dev:.../jobs.py:56-84`).
- Auth on 7 of 11 job routes (rerun/resume/media/segments GET+PUT/render/download), and on
  `/api/runtime` (§5.2). On the batch service (live disabled): auth on **anything**.
- A live-session listing route (session ids are unenumerable remotely).
- Speaker rename endpoint / `speaker_renamed` event (declared unreachable,
  `dev:.wayfinder/tickets/T-02-poll-contract-event-model.md:110`); all `llm_*` events.
- WebSockets (ADR-0001 keeps JSON-over-HTTP; `ws.ts` is a naming artifact only).
- SQLite or any database (grep: none).
- HTTP export/read routes for tapes and for the vector journal (writers only).
- Persistence of sessions/view grants (memory-only; restart orphans every session and view token).
- `device_id` anywhere in the Chrome client (grep: none).
- Multi-worker serving (single uvicorn process; all registries are process-local).

**Dormant (present + wired, but idle in the shipped Chrome flow):**
- The pairing/capture-authority flow: `POST /api/live/pairing-codes`, `POST /api/live/pairings`,
  `ops/live-pair.sh`, cert-pin payloads — fully wired; consumed only by the macOS capture app
  (Keychain: `dev:macos/.../CaptureSecurity.swift:12-18`), while the Chrome client uses the shared
  token. Registry supports both simultaneously.
- Operator revocation surface: `DELETE /api/live/devices/{id}`, `DELETE
  /api/live/sessions/{sid}/view` (loopback-only, no CLI wrapper for the latter).
- `echo_mode` on session create (accepted, journaled; no shipping client sends it,
  `dev:.../live_service_runtime.py:465-476`).
- The digest-bound shared-token revocation marker (recovery-by-rotation path,
  `dev:.../live_auth.py:421-455`).
- Tier-B file-mode speaker identity (`--speaker-identity-tier-b`, default off;
  `dev:ops/moss.env` sets 0).

**Unknown (not decidable read-only from this checkout):**
- Whether the deployed host's `ops/moss-live.env` (untracked) actually sets
  `MOSS_LIVE_SHARED_TOKEN_FILE` (template marks it optional-but-present) or a retention root
  (template ships it commented out).
- Contents of the deployed `live-auth.json` (how many paired devices exist; whether the macOS app
  is actively paired).
- Whether any real `speaker-vectors.jsonl` rows exist on the host, and journald retention for
  access logs.
- Firewall posture in front of the `0.0.0.0` binds (WSL port-proxying per
  `dev:ops/configure-windows-network.ps1` — not inspected in depth).

---

## 11. Biggest surprises (ranked)

1. **`--host 0.0.0.0` + unauthenticated jobs surface.** Both services bind all interfaces
   (`dev:ops/start-web.sh:147`). The plaintext batch service has zero auth (registry is None →
   `_authorize_job_request` no-ops, `dev:.../server.py:504-505`); even the live service leaves
   media download, segments read/WRITE, rerun, resume, render, download unauthenticated. Any LAN
   peer with a 12-hex job id reads the uploaded audio and can rewrite the transcript.
2. **The shared token is a single device, not a credential-per-client.** Isolation between two
   Chrome users today is *zero by construction* — same principal, mutual capture/stop/abort
   authority over each other's sessions (`dev:.../live_auth.py:18,309-314`).
3. **View authority is computed from live runtime status per-request** (not stored grants) —
   elegant, but it means restart kills all view tokens (sessions are memory-only) and Phase-2
   durable grants have no persistence to inherit: `live-auth.json` stores devices only.
4. **The vector journal is default-ON and cross-session** the moment `--live` is enabled, while
   audio retention is opt-in-OFF — the durable biometric derivative outlives the meeting even in
   the "no audio persisted" posture (ADR-0003 addendum flags the consent boundary as still open).
5. **Loopback = root.** Pairing mint, device revocation, and view revocation take no credential at
   all beyond being loopback — any local process on the host is the operator.
6. **Canonical inference is globally single-threaded** across sessions (one pump thread) — G4
   concurrency is fairness + bounded queues + 429s, not parallel decode.
