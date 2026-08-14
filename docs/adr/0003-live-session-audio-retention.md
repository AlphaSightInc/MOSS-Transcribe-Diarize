# ADR-0003: Live session audio retention — the tape is a working substrate, not an archive

- Status: **Accepted** (2026-07-29). The retention *posture change* was accepted by the product
  owner in ADR-0002 §Consequences and restated in `scripts/ralph-afk/prd.md` ("the server will
  retain meeting audio (~0.3 GB/hr, TTL configurable) … so the PRD's *no raw audio is persisted*
  clause must be re-read against ADR-0002 rather than enforced blindly"). What was **not** decided
  there, and is decided here, is the bound: how long, where, under what modes, and what happens
  when the disk says no.
- Deciders: the autonomous loop (`scripts/ralph-afk`, run `20260729-025318` iteration 18) under
  that instruction. Supersedes nothing; refines ADR-0002 §Consequences bullet 1 and answers
  `docs/design-streaming-diarization.md` §8's last open question ("Retention TTL / privacy posture
  for stored session audio").
- Required before: ADR-0002 implementation **step 2**, the tape recorder. This record is that
  step's stated precondition — a decision in writing, before any code.
- Addendum (2026-08-13): T-12 separately resolved persistence of the derived live-album
  centroid. The distinction and its still-open consent boundary are recorded below.

## Context

### What the clause protects today, measured rather than assumed

The PRD's acceptance bar carries one sentence about audio, inside the secret-hygiene clause:
*"no bearer token, device token, view token, or pairing payload appears in any CLI output, log,
URL, telemetry file, or browser storage; **no raw audio is persisted**."*

Read against the running service, that clause is not a prohibition on audio ever reaching a disk.
It is a statement about a **horizon**. Live audio touches disk on every span today:

- `live_adapters.py:298` writes the span's PCM into a `tempfile.TemporaryDirectory(prefix=
  "mtd-live-", dir=self.scratch_dir)` for the decoder, and the directory is removed when the
  context exits;
- `live_provider_bundle.py:561` does the same for the identity encoder's golden/evidence path.

So the horizon today is **one span**, ~2.5 s, and the loop's recorded hygiene evidence is exactly
that horizon holding: `live-runs/` **0 entries** and **no surviving `/tmp/mtd-live-*`** after every
certification run (F1, F2, F3). In memory the horizon is longer and also bounded — `LiveSession`
prunes committed frames against `max_retained_samples` 960000 (60 s), a domain-contract value.

### What ADR-0002 needs

Step 2 appends every acknowledged frame to durable per-lane + mixed session logs with a gap
manifest (~0.3 GB/hr), because retrospective sweeps and crash/resume have no substrate without it.
That moves the horizon from one span to **one meeting**. It does not, by itself, ask for anything
to outlive the meeting.

### The collision, stated precisely

Enforcing the clause blindly forbids step 2 and therefore forbids ADR-0002's acceptance bar
(≥ 90–95 % live accuracy **and** demonstrated live→file convergence), since convergence is what
the sweep buys and the sweep has nothing to sweep. Waiving the clause blindly hands the loop an
unbounded write path on a host that also serves the batch service, whose own "unharmed" clause is
in the same acceptance bar. Neither reading is available; the horizon is what has to be decided.

## Decision

**D1 — The clause is a horizon, and the horizon becomes the meeting.** Re-read *"no raw audio is
persisted"* as: **no live meeting audio outlives the artifact that justifies keeping it.** Today
that artifact is the span. With the tape it is the session. The word *persisted* keeps its force
against everything with a longer life than that.

**D2 — Retention is opt-in and off by default.** No tape is written unless the deployment declares
a tape root. With it undeclared the service behaves byte-for-byte as it does today and the existing
hygiene evidence stands unchanged. Two reasons, not one: every gate this loop has recorded was
measured against a no-tape service, and a default-on change would invalidate all of them in one
step; and a privacy posture must never arrive as a side effect of upgrading a binary.

**D3 — The default TTL after session end is zero: the tape is deleted when the meeting ends.**
ADR-0002 runs its final sweep at session end, so nothing in the design needs the audio afterwards —
the album is the compressed context that is handed forward, which is the ADR's own argument
("later processing never re-hears earlier audio"). At the default configuration the PRD clause
therefore still holds in its literal form at every boundary an operator can observe *after* a
meeting: nothing on disk. A deployment that wants post-hoc reprocessing may declare a positive TTL,
and **the deployment states it — the tool never defaults it**, the rule candidate 63 established
for the matcher thresholds: a free parameter with no derivation a tool could verify must be stated
by the thing that owns the consequence.

**D4 — One declared root, where modes are real, never sharing a filesystem with batch `runs/`.**
The root must satisfy all four:
1. files `0600` inside a `0700` directory, the posture `live.key` and `live-auth.json` already have;
2. **outside the repo checkout** — a rollback is `git checkout <sha>` (rehearsed in F4a) and must
   never move audio, and `git clean` must never be a reaper;
3. **not on the same filesystem as the batch runs directory**, because `server.py:447`
   `_admit_upload_request` answers **507 Insufficient storage** whenever
   `disk_usage(runs_dir).free` drops below `2 × content_length + 512 MB`: a runaway tape would
   break the PRD's *"batch service unharmed"* clause from the outside, without touching the batch
   service at all. At ~0.3 GB/hr that headroom is under two hours of one meeting;
4. a filesystem that **enforces modes**. This is not theoretical here: `/mnt/d` is a 9p `drvfs`
   mount without the `metadata` option, so every file under the server checkout reads `777` and
   `chmod` is a silent no-op — and that is exactly where `MOSS_RUNS_DIR` and the batch `runs/` tree
   live. The live secret state already sits on ext4 under
   `~/.local/share/moss-transcribe-diarize/live/`, which satisfies (1)–(4) today.

**D5 — The tape is bounded in bytes, and storage pressure degrades the tape, never the meeting.**
The third amendment's governing rule applied to a disk: reaching the declared cap, or any write
failure, stops taping, records a **typed degradation** naming the reason and the byte counts, and
the meeting continues on live labels alone (sweeps lose their substrate; quality falls back to the
album's step-1 behaviour). It never ends the session, never blocks a frame acknowledgement, and
never silently keeps writing. The cap, like the TTL, is declared by the deployment when retention
is enabled.

**D6 — The service is the reaper, and it reaps at startup too.** A TTL that only fires while the
process lives is not a retention policy. Deletion is driven by session state plus TTL, and the same
rule runs at service start over any tape left by a crashed process. A session that ends by
helper-lease expiry is already terminal, so the existing lease machinery reaps abandoned meetings
without new timers.

**D7 — What stays absolutely forbidden, unchanged by this record.** No audio on the capture Mac
beyond the outbox's in-memory frames. No audio in a log line, journal entry, telemetry file,
snapshot, event, or portal response. No audio in any evidence directory pulled off a host. No audio
under the batch `runs/` tree, ever. And the secret half of the PRD clause — tokens and pairing
payloads — is untouched by any of this and keeps its absolute reading.

### 2026-08-13 addendum — the vector journal is not raw-audio retention

T-12 resolves the previously open album-persistence question narrowly: on clean session end the
service writes each speaker's duration-weighted album centroid to a local, append-only,
session-keyed vector journal. Vector journaling defaults **on**; raw-audio retention remains
**off** unless ADR-0003's separate tape configuration is declared. The journal is not a voice
bank: it has no enrollment, naming, matching, CRUD, or UI.

A speaker embedding is biometric data. Enabling this journal for the guarded LAN/tailnet posture
is **not** a consent decision for meeting participants and supplies no deletion or
right-to-remove mechanism. Any rollout beyond that guarded deployment requires an explicit
consent decision and an explicit deletion/right-to-remove ruling **before the journal ships**.
Until then, the absence of journal CRUD must not be interpreted as a policy that removal is
unnecessary or unsupported by the eventual product.

### 2026-08-14 addendum — vector-journal reader contract

The append-only journal preserves a previous unterminated record as a forensic line: before a
later append it terminates that byte sequence with one newline rather than deleting or repairing
it. This recovery also runs for a refusal-only completed session when the journal already exists;
otherwise an invalid observation could leave the next real row glued to a torn predecessor.

Consumers use `LiveVectorJournal.read_rows()` (or reproduce its contract): return only complete
JSON-object lines; skip blank lines and lines that cannot be decoded as UTF-8 JSON; never mutate
or silently discard those forensic bytes. A reader may validate the returned row schema for its
own purpose, but malformed-line tolerance is mandatory so one crash artifact cannot hide later
valid sessions. Missing journal files read as no rows; filesystem access failures still surface.

## Consequences

- ADR-0002 step 2 is unblocked, with a shape it must implement rather than a permission it may
  interpret: a declared root, declared TTL, declared cap, typed degradation, startup reap.
- The PRD's audio clause stays **testable** instead of becoming a waiver. It gains a second form,
  selected by whether the deployment declared a root:
  - *retention undeclared* (today's server): unchanged — `live-runs/` 0 entries, no surviving
    `/tmp/mtd-live-*`, no audio artifact anywhere on either host;
  - *retention declared*: audio exists **only** under the declared root; every tape there maps to a
    session that is active or within TTL; modes are `0600`/`0700`; total bytes ≤ the declared cap;
    nothing under the checkout, nothing under batch `runs/`, nothing on the Mac.
- Every certification run recorded so far keeps its meaning, because they all ran with retention
  undeclared and that is still the default.
- Crash/resume (ADR-0002 §Decision 1) survives the zero-TTL default: a crash happens *during* a
  meeting, when the tape exists by construction.
- The 4070Ti host must gain a declared root on ext4 before step 2 can be enabled there; the Windows
  drive is disqualified by D4(3) and D4(4) together, which is a deployment change and not a code one.

## What this record does not decide

- **The tape's on-disk format and gap-manifest schema.** ADR-0002 §Decision 1 and
  `docs/design-streaming-diarization.md` §3.2 already fix raw PCM plus a JSON index with WAV
  rendered on demand, teed at the mixer's sealed-interval commit. Not re-opened here.
- **A cross-meeting voice bank or its consent/removal policy.** T-12 now permits only the derived,
  session-keyed journal described in the addendum. The in-memory album still dies with the
  session, and turning journal rows into enrollment, identity matching, naming, CRUD, or UI
  remains undecided Phase 2 work. Rollout beyond the guarded LAN/tailnet remains blocked on the
  explicit consent and deletion/right-to-remove ruling above.
- **The numeric TTL and cap for any deployment.** By D3 and D5 those are stated by the deployment,
  and a default would be a guess wearing a contract's clothes.
- **Re-ASR of the tape.** Forbidden by ADR-0002 (sweeps are diarization only); nothing here
  softens it.
