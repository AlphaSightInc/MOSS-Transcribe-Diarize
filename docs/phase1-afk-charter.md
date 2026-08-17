# Phase 1 AFK charter — authority, specs, and acceptance gates

Binding for every ralph-afk agent working a Phase 1 ticket on the night of 2026-08-13.
Operator is asleep; the supervising agent acts on their behalf. Decisions here were ruled by
the operator or delegated explicitly to the supervisor. **Do not re-litigate them.**

Source of design decisions: `.wayfinder/map-001-phase1-chrome-client.md` (premises C1–C11 and
the closed decision tickets). Read your ticket's referenced wayfinder tickets before starting.

---

## 1. Authority and hard limits

| | Ruling |
|---|---|
| Remote host `ga0-alienware-rtx4070ti` | **READ-ONLY.** Probe `/api/live/descriptor` and health. **Never** restart, reconfigure, deploy to, or send a mutating request to `moss-live-web`, `moss-vllm`, or `moss-web`. |
| Verification target | A **locally-run** service instance you start yourself, per worktree, on a port you own. |
| Automated display capture | **FORBIDDEN.** The display chooser is irreducible — the standard requires a fresh user gesture per capture and permits no persistent grant. The 2026-08-03 CDP-flag attempt failed with `NotReadableError`. Do not retry it; do not use automation source-selection flags. |
| Push | Push **your own branch only** to remote `private` (`aiSight-us/MOSS-Transcribe-Diarize`). Never force-push. Never push `dev` or `main`. |
| Issue closing | **You may not close issues.** Comment evidence; the supervisor verifies and closes. |
| Secrets | Never commit tokens, `.pem`, `.p12`, pairing payloads, or `ops/moss-live.env`. `.gitignore` already covers these — do not weaken it. |
| Scope | Your ticket only. If you find a defect outside it, record it in `context.md` and comment on your issue. Do not fix it. |

## 2. Merge protocol — self-merge, but serialized

Agents integrate `dev` into their branch and fast-forward `dev` when green (operator ruling).
**Merges only — `prompt.md` forbids rebasing and that rule stands.** `dev` is deliberately not
checked out in any worktree, which is what makes `git push . HEAD:dev` work. Two guards are
mandatory:

**Acquire the merge lock before touching `dev`.** The lock is a single file in the shared git
directory, so all worktrees see it:

```bash
LOCK="$(git rev-parse --git-common-dir)/afk-merge.lock"
# acquire (atomic; fails if held)
if ! ( set -o noclobber; echo "$$ ticket-N $(date -u +%FT%TZ)" > "$LOCK" ) 2>/dev/null; then
  echo "merge lock held by: $(cat "$LOCK")"; exit 1   # wait and retry, do not steal
fi
# git merge --no-edit dev ; validate the MERGED result ; git push . HEAD:dev ; git push private HEAD:<branch>
rm -f "$LOCK"                                          # ALWAYS release
```

Rules:
- Never steal or delete a lock you did not create. If a lock looks stale (>30 min), comment on
  your issue and let the supervisor break it.
- **Validation must pass on the merged result, not just on your branch**, before you fast-forward `dev`.
- Do not check `dev` out in a worktree.
- If your merge breaks `dev`, revert your merge immediately — do not attempt a forward fix while
  holding the lock.
- `dev` at `pre-afk-20260813` is the safety tag. `dev-backup-20260812` also exists.

## 3. Definition of done

A ticket is done when **all** hold:

1. Every acceptance criterion on the GitHub issue is satisfied.
2. Validation passes on the branch **after merging current `dev` into it**.
3. Evidence exists as **raw artifacts** (command output, logs, measurement files), not prose
   claims — committed under `evidence/phase1/<ticket-n>/`.
4. A comment on the issue links the branch and states, criterion by criterion, what proves it.
5. The branch is pushed to `private`.
6. `context.md` and `progress.txt` reflect final state.

**A gate satisfiable by stub evidence is not satisfied.** This project has previously shipped a
rail that passed on stub evidence. State plainly what a test does *not* cover.

## 4. T-06 — capture page spec (RULED)

Mechanism is settled by measurement in `docs/research-chrome-capture-mvp-2026-08-03.md`
§"Recommended lane design". Treat as given: one `AudioContext({sampleRate:16000})`; `AudioWorklet`
aggregating 128-sample quanta into exactly `frame_samples`; **POST driven by worklet port
messages, never timers**; clock anchored once at the first delivered sample and advanced
arithmetically; descriptor-driven geometry; exactly the nine v2 keys; zero-gain node to
`ctx.destination`; display video track retained but never transmitted.

Newly ruled:

- **Preflight is a modal** over the app shell reusing `LlmSettingsModal` styling (T-05). Contents:
  (1) Start capture button; (2) microphone permission step; (3) surface-choice step, tab
  preferred; (4) explicit share-audio reminder; (5) **two live meters** that must both read
  non-zero before a server session is created; (6) headphones-vs-speakers echo choice.
- **Activation ordering: mic-first.** Verify `ctx.state === "running"` before enabling
  "Start display". Call `getDisplayMedia()` **synchronously inside the click handler** before it
  yields. Display-first / system-only bootstrap is **out of Phase 1** — unmeasured.
- **Echo policy.** Headphones → mic raw. Speakers → `echoCancellation` on the **mic lane only**;
  system lane raw either way. Record the chosen mode on the session (it rides the vector-journal
  row per T-12).
- **Errors.** 400 = malformed frame (client bug, do not retry). 409 = sequence conflict or
  terminal session (resync or recreate). 429 on the v2 lane path = **non-terminal backpressure,
  retry**. A frame whose previewed canonical work exceeds the queue's total capacity is not
  backpressure: it fails the session with non-retryable 409
  `frame_work_exceeds_queue_capacity`, and capture stops. Only ever send v2 lane frames — the
  legacy mono path's 429 is terminal. Never infer cause from Chrome's exception name;
  `NotAllowedError` covers both gestureless calls and user dismissal. Stop on error and offer a
  **user-driven** retry, never automatic.
- **Lane loss.** Bump `device_epoch` on track replacement/restart; mark `discontinuity`. A failed
  lane contributes exact zero while its sealed peer may still reach mono, so the session
  continues single-lane where the mixer permits.
- **Clipping.** Meter and warn on sustained full-scale; the measured loopback lane hit ±32767.
- **No audio track on the chosen surface → fail preflight.** Never call that a system lane.
- **Silent mic lane → the status line must name how to change Chrome's default input**, because
  T-05 dropped the picker and left no other in-app remedy.

## 5. T-10 — fidelity method (RULED)

A pixel gate nobody can run is worse than an honest one.

- **Oracle:** the reference at `/Users/gao/Desktop/AI_Projects/LiveTranscribe`. Prefer serving its
  built `ProjectResources/Frontend/` bundle statically — do **not** depend on the packaged Swift
  app launching.
- **Method:** headless-Chrome screenshot diff at fixed viewports (1440×900 and 1280×800) against a
  **stubbed transcript fixture**, so both sides render identical content.
- **Tolerance:** ≤ **2 %** differing pixels per viewport, and no single contiguous differing
  region larger than 1 % of viewport area. A 0-pixel bar is unachievable (antialiasing, subpixel
  text) and demanding it makes the gate meaningless. A pixel differs only when at least one RGB
  channel differs by more than 1 level; this removes imperceptible cross-context rasterization
  noise while retaining the fixed 2 % / 1 % acceptance bars.
- **Exempt regions**, declared in the diff config, not silently ignored: the right-column rail,
  the mode segmented control (two segments vs four), the preflight modal (no reference pixels
  exist), and the transcript pane's `.tr-legend-right` Transcript|Summary toggle.

  The last was added 2026-08-14 while porting the pane. It is the same class as the other two:
  `SummaryView` is a ruled Phase 2 deletion (C10), so the toggle is a control that cannot work,
  and C2 forbids shipping it disabled. Every other difference in the transcript panel is **not**
  exempt — adversarial review measured that panel at 48.8 % of all differing pixels, so the
  exemption is deliberately narrow: it covers the toggle's own box, nothing else in the pane.
- **Where reference pixels do not exist** (preflight, token entry): the standard is the
  reference's own CSS custom properties, type scale, spacing, and four bundled font families
  reused verbatim. Reviewed by the supervisor, not gated numerically.
- The reference's `vitest` component tests transfer with the components and must pass. They prove
  behaviour, not pixels; both are required.

## 6. T-11 — Phase 1 acceptance gates (RULED)

### Per-ticket
The GitHub issue's acceptance criteria are the gate. No additions, no substitutions.

### Overall MVP — what "functioning and stress tested" means

| Gate | Bar |
|---|---|
| **G1 mic lane e2e, real** | Chrome launched with `--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<two-speaker wav>` produces transcript text with ≥2 distinct speaker ids, rendered in the browser, against a locally-run service. Zero sequence gaps; every frame exactly `frame_samples`. |
| **G2 system lane** | Exercised with **synthetic frames** through the production live routes. Explicitly recorded as *not* proving real display capture. |
| **G3 two-lane display capture** | **DEFERRED to the attended checklist (§7).** No agent may claim it. |
| **G4 concurrency** | The measured bound from ticket #3 sustained for **≥10 minutes** at that concurrency, with p95 transcript lag under the stated gate, fair round-robin service, no OOM, and 429 backpressure appearing **per session** rather than globally. |
| **G5 cross-session integrity** | Under overload and across reconnect, no session ever receives another session's text. **Note:** the historical `403` cross-read result is *not* a criterion — T-01 accepted a single trust domain. The criterion is *text never crosses*, not *reads are forbidden*. |
| **G6 failure paths** | Each produces a correct server-authored status line and no crash: microphone permission denied; surface chosen without share-audio (preflight must fail, not produce an empty lane); one lane dying mid-session; 429 backpressure; terminal 409; reload mid-capture reattaching from `sessionStorage`. |
| **G7 background tab** | A backgrounded capture tab sustains frame cadence **and does not trip `live_helper_lease_seconds`**. This is the heartbeat-throttling trap: timers collapse to ~1/min in background, worklet port messages do not. |
| **G8 fidelity** | §5's diff passes at both viewports; reference component tests green. |
| **G9 modes** | Live mode and file mode both work through the one UI. |
| **G10 no regression** | The existing live/contract suites pass. The pre-existing baseline is ~418 passed / 2 skipped / 342 subtests — do not go backwards. |

### Explicitly NOT gated in Phase 1
Windows Chrome (Gate 4 of the research doc), Safari, trusted certificates, URL mode, batch mode,
the LLM layer, session history, speaker rename, and the voice bank itself (only the journal ships).

## 7. Attended checklist — left for the operator at wake

The one thing no agent can do. Should take ~10 minutes.

1. Open the app on the service origin **including `:7861`**, and accept the TLS interstitial once.
2. Click **Start capture**; allow the microphone.
3. Choose the **meeting tab** (preferred path) and explicitly enable **share tab audio**.
4. Confirm **both** meters move independently.
5. Speak a unique marker; let a two-speaker fixture play in the shared tab; run 60 s.
6. Confirm transcript text for both sources with distinct speaker ids.
7. Repeat once selecting **entire screen** with **System Audio**.
8. Stop cleanly. Preserve the page log and the session's evidence directory.

Expected: exact `frame_samples` frames, no sequence gaps, 0.5 s capture-timestamp deltas, zero
fetch errors, both lanes non-zero RMS. If a surface offers no audio, preflight must fail loudly.

---

## 8. Anti-drift rules for this fleet

- **Measure, don't assert.** `AGENTS.md` requires prototyping and measurement before production
  code for any new algorithm, threshold, or policy. Extend `prototypes/streaming-diarization/`
  rather than rebuilding measurement scaffolding.
- **Do not add Uvicorn workers** to solve concurrency. Device state, session ownership, runtime
  objects, mixers, event queues and view grants are process-local; two workers can disagree about
  a token or session and route unsafely.
- **Never hardcode frame geometry.** `frame_samples` / `sample_rate` are deploy-manifest values.
- **Provider manifest trap.** `source_revision` comes from the provider manifest and must be
  re-finalized per host. Do not let a frontend or route change silently invalidate the manifest
  hash.
- If blocked for 3 consecutive iterations, stop and comment on your issue asking the supervisor.
  Do not thrash.
